from fastapi import APIRouter, Body, Depends, HTTPException, Request, status
from fastapi.responses import JSONResponse
from typing import List, Optional
from datetime import datetime, timedelta
import secrets
from bson import ObjectId
from ..models.share_link import ShareLinkCreate, ShareLinkResponse, ShareLinkDB, ShareLinkRevoke
from ..config.database import get_database
from ..services.auth import get_current_user, get_current_active_user

router = APIRouter()
collection_name = "share_links"

@router.post("/", response_model=ShareLinkResponse, status_code=status.HTTP_201_CREATED)
async def create_share_link(
    request: Request,
    share_link: ShareLinkCreate = Body(...),
    current_user = Depends(get_current_active_user)
):
    """Créer un nouveau lien de partage pour un technicien"""
    db = request.app.state.db
    
    # Vérifier si le technicien existe
    technician = await db.technicians.find_one({"_id": share_link.technician_id})
    if not technician:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Technicien avec l'ID {share_link.technician_id} non trouvé"
        )
    
    # Calculer la date d'expiration
    expires_at = share_link.calculate_expiry()
    
    # Créer le lien de partage dans la base de données
    new_share_link = ShareLinkDB(
        technician_id=share_link.technician_id,
        expires_at=expires_at,
        can_add_appointments=share_link.can_add_appointments,
        token=secrets.token_urlsafe(32),
        created_by=current_user["_id"],
        ip_whitelist=share_link.ip_whitelist
    )
    
    result = await db[collection_name].insert_one(new_share_link.dict(by_alias=True))
    created_share_link = await db[collection_name].find_one({"_id": result.inserted_id})
    
    # Construire l'URL de partage
    base_url = request.url_for("get_shared_calendar", token=created_share_link["token"])
    share_url = str(base_url)
    
    # Calculer le temps restant
    now = datetime.utcnow()
    remaining_delta = created_share_link["expires_at"] - now
    remaining_time = format_remaining_time(remaining_delta)
    
    # Créer la réponse
    response = {
        **created_share_link,
        "share_url": share_url,
        "remaining_time": remaining_time
    }
    
    return response

@router.get("/", response_model=List[ShareLinkResponse])
async def get_share_links(
    request: Request,
    technician_id: Optional[str] = None,
    technician_id_full: Optional[str] = None,  # Nouveau paramètre pour l'ID complet
    active_only: bool = True,
    current_user = Depends(get_current_active_user)
):
    """Récupérer tous les liens de partage, optionnellement filtrés par technicien"""
    db = request.app.state.db
    
    query = {}
    
    # Priorité à l'ID complet s'il est fourni
    if technician_id_full and ObjectId.is_valid(technician_id_full):
        query["technician_id"] = ObjectId(technician_id_full)
    elif technician_id and ObjectId.is_valid(technician_id):
        query["technician_id"] = ObjectId(technician_id)
    elif technician_id or technician_id_full:
        # Log pour le débogage
        print(f"ID de technicien non valide reçu : {technician_id or technician_id_full}")
        # On pourrait retourner une erreur ou continuer sans appliquer le filtre
    
    if active_only:
        query["is_active"] = True
        query["expires_at"] = {"$gt": datetime.utcnow()}
    
    share_links = await db[collection_name].find(query).to_list(1000)
    
    # Ajouter les URLs de partage et temps restant
    result = []
    now = datetime.utcnow()
    
    for link in share_links:
        remaining_delta = link["expires_at"] - now
        remaining_time = format_remaining_time(remaining_delta)
        
        base_url = request.url_for("get_shared_calendar", token=link["token"])
        share_url = str(base_url)
        
        result.append({
            **link,
            "share_url": share_url,
            "remaining_time": remaining_time
        })
    
    return result

@router.get("/{id}", response_model=ShareLinkResponse)
async def get_share_link(
    id: str,
    request: Request,
    current_user = Depends(get_current_active_user)
):
    """Récupérer un lien de partage par son ID"""
    db = request.app.state.db
    
    share_link = await db[collection_name].find_one({"_id": id})
    if not share_link:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Lien de partage avec l'ID {id} non trouvé"
        )
    
    # Ajouter l'URL de partage et temps restant
    now = datetime.utcnow()
    remaining_delta = share_link["expires_at"] - now
    remaining_time = format_remaining_time(remaining_delta)
    
    base_url = request.url_for("get_shared_calendar", token=share_link["token"])
    share_url = str(base_url)
    
    return {
        **share_link,
        "share_url": share_url,
        "remaining_time": remaining_time
    }

@router.put("/{id}/revoke", response_model=ShareLinkResponse)
async def revoke_share_link(
    id: str,
    request: Request,
    revoke_data: ShareLinkRevoke = Body(...),
    current_user = Depends(get_current_active_user)
):
    """Révoquer un lien de partage avant sa date d'expiration"""
    db = request.app.state.db
    
    # Vérifier si le lien existe
    share_link = await db[collection_name].find_one({"_id": id})
    if not share_link:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Lien de partage avec l'ID {id} non trouvé"
        )
    
    # Mettre à jour le lien pour le désactiver
    update_data = {
        "$set": {
            "is_active": False,
            "revoked_by": current_user["_id"],
            "revoked_at": datetime.utcnow(),
            "revocation_reason": revoke_data.reason
        }
    }
    
    await db[collection_name].update_one({"_id": id}, update_data)
    
    # Récupérer le lien mis à jour
    updated_share_link = await db[collection_name].find_one({"_id": id})
    
    # Pas de temps restant pour un lien révoqué
    remaining_time = "Révoqué"
    
    base_url = request.url_for("get_shared_calendar", token=updated_share_link["token"])
    share_url = str(base_url)
    
    return {
        **updated_share_link,
        "share_url": share_url,
        "remaining_time": remaining_time
    }

@router.get("/access/{token}")
async def get_shared_calendar(
    token: str,
    request: Request
):
    """Accéder au calendrier partagé via un token (utilisé publiquement)"""
    db = request.app.state.db
    
    # Vérifier si le lien existe et est actif
    now = datetime.utcnow()
    share_link = await db[collection_name].find_one({
        "token": token,
        "is_active": True,
        "expires_at": {"$gt": now}
    })
    
    if not share_link:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Lien de partage invalide, expiré ou révoqué"
        )
    
    # Vérifier la liste blanche d'IP si elle existe
    client_ip = request.client.host
    if share_link.get("ip_whitelist") and client_ip not in share_link["ip_whitelist"]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Accès non autorisé depuis cette adresse IP"
        )
    
    # Incrémenter le compteur d'accès
    await db[collection_name].update_one(
        {"_id": share_link["_id"]},
        {
            "$inc": {"access_count": 1},
            "$set": {"last_accessed_at": now}
        }
    )
    
    # Récupérer les informations du technicien
    technician_id = share_link["technician_id"]
    technician = await db.technicians.find_one({"_id": technician_id})
    
    if not technician:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Technicien non trouvé"
        )
    
    # Récupérer les rendez-vous du technicien
    appointments = await db.appointments.find({"technician_id": technician_id}).to_list(1000)
    
    # Renvoyer les données nécessaires pour afficher le calendrier partagé
    return {
        "technician": {
            "id": str(technician["_id"]),
            "name": technician.get("name", ""),
            "department": technician.get("department", ""),
            # Autres informations publiques du technicien
        },
        "can_add_appointments": share_link["can_add_appointments"],
        "expires_at": share_link["expires_at"],
        "appointments": appointments,
        "is_shared_view": True
    }

def format_remaining_time(delta: timedelta) -> str:
    """Formater un timedelta en format lisible"""
    if delta.total_seconds() <= 0:
        return "Expiré"
    
    days = delta.days
    hours, remainder = divmod(delta.seconds, 3600)
    minutes, _ = divmod(remainder, 60)
    
    parts = []
    if days > 0:
        parts.append(f"{days} jour{'s' if days > 1 else ''}")
    if hours > 0:
        parts.append(f"{hours} heure{'s' if hours > 1 else ''}")
    if minutes > 0 and days == 0:  # Afficher les minutes seulement si moins d'un jour
        parts.append(f"{minutes} minute{'s' if minutes > 1 else ''}")
    
    return " et ".join(parts) if parts else "Moins d'une minute"