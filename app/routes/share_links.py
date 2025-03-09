from fastapi import APIRouter, Body, Depends, HTTPException, Request, status
from fastapi.responses import JSONResponse
from typing import List, Optional, Dict, Any
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
    technician_id = share_link.technician_id
    technician = None
    
    if ObjectId.is_valid(technician_id):
        technician = await db.technicians.find_one({"_id": ObjectId(technician_id)})
    
    if not technician:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Technicien avec l'ID {technician_id} non trouvé"
        )
    
    # Calculer la date d'expiration
    expires_at = share_link.calculate_expiry()
    
    # Créer le lien de partage dans la base de données
    new_share_link = ShareLinkDB(
        technician_id=ObjectId(technician_id),
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

@router.post("/query", response_model=List[ShareLinkResponse])
async def query_share_links(
    request: Request,
    query_data: Dict[str, Any] = Body(...),
    current_user = Depends(get_current_active_user)
):
    """Récupérer les liens de partage via POST pour éviter les problèmes d'URL"""
    db = request.app.state.db
    
    query = {}
    
    # Extraire les paramètres du corps de la requête
    technician_id = query_data.get("technician_id")
    active_only = query_data.get("active_only", True)
    
    print(f"POST /query - Paramètres : {query_data}")
    
    if technician_id:
        if ObjectId.is_valid(technician_id):
            query["technician_id"] = ObjectId(technician_id)
            print(f"Recherche avec ObjectId: {query['technician_id']}")
        else:
            query["technician_id"] = technician_id
            print(f"Recherche avec ID en chaîne: {technician_id}")
    
    if active_only:
        query["is_active"] = True
        query["expires_at"] = {"$gt": datetime.utcnow()}
    
    print(f"Query MongoDB: {query}")
    
    share_links = await db[collection_name].find(query).to_list(1000)
    print(f"Nombre de liens trouvés: {len(share_links)}")
    
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

@router.get("/", response_model=List[ShareLinkResponse])
async def get_share_links(
    request: Request,
    technician_id: Optional[str] = None,
    technician_id_full: Optional[str] = None,
    active_only: bool = True,
    current_user = Depends(get_current_active_user)
):
    """Récupérer tous les liens de partage, optionnellement filtrés par technicien"""
    print(f"GET / - Paramètres : technician_id={technician_id}, technician_id_full={technician_id_full}, active_only={active_only}")
    
    db = request.app.state.db
    
    query = {}
    
    # Traiter les différents formats d'ID
    if technician_id_full or technician_id:
        tech_id = technician_id_full or technician_id
        
        try:
            if ObjectId.is_valid(tech_id):
                obj_id = ObjectId(tech_id)
                print(f"Recherche avec ObjectId: {obj_id}")
                # Essayer à la fois le format ObjectId et chaîne
                query["$or"] = [
                    {"technician_id": obj_id},      # Format ObjectId
                    {"technician_id": str(tech_id)} # Format chaîne
                ]
            else:
                print(f"ID non valide pour ObjectId: {tech_id}")
                query["technician_id"] = tech_id
        except Exception as e:
            print(f"Erreur lors de la conversion de l'ID: {str(e)}")
    
    if active_only:
        query["is_active"] = True
        query["expires_at"] = {"$gt": datetime.utcnow()}
    
    print(f"Query MongoDB: {query}")
    
    # Vérifier si la collection existe et afficher des informations
    collections = await db.list_collection_names()
    print(f"Collections disponibles: {collections}")
    
    if collection_name in collections:
        count = await db[collection_name].count_documents({})
        print(f"Nombre total de documents dans {collection_name}: {count}")
        
        # Récupérer un échantillon pour voir la structure
        if count > 0:
            sample = await db[collection_name].find_one({})
            print(f"Structure d'un document de la collection: {sample}")
    
    share_links = await db[collection_name].find(query).to_list(1000)
    print(f"Nombre de liens trouvés: {len(share_links)}")
    
    # Si aucun lien n'est trouvé, afficher un message plus détaillé
    if len(share_links) == 0:
        print(f"Aucun lien trouvé pour la requête: {query}")
        # Vérifier si le technicien existe
        if technician_id_full or technician_id:
            tech_id = technician_id_full or technician_id
            if ObjectId.is_valid(tech_id):
                technician = await db.technicians.find_one({"_id": ObjectId(tech_id)})
                if technician:
                    print(f"Le technicien existe: {technician.get('first_name')} {technician.get('last_name')}")
                else:
                    print(f"Aucun technicien trouvé avec l'ID: {tech_id}")
    
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
    
    share_link = None
    
    if ObjectId.is_valid(id):
        share_link = await db[collection_name].find_one({"_id": ObjectId(id)})
    
    if not share_link:
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
    share_link = None
    
    if ObjectId.is_valid(id):
        share_link = await db[collection_name].find_one({"_id": ObjectId(id)})
    
    if not share_link:
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
    
    if ObjectId.is_valid(id):
        await db[collection_name].update_one({"_id": ObjectId(id)}, update_data)
        updated_share_link = await db[collection_name].find_one({"_id": ObjectId(id)})
    else:
        await db[collection_name].update_one({"_id": id}, update_data)
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
    technician = None
    
    if isinstance(technician_id, ObjectId):
        technician = await db.technicians.find_one({"_id": technician_id})
    else:
        # Si l'ID est une chaîne, essayer de le convertir en ObjectId
        if ObjectId.is_valid(technician_id):
            technician = await db.technicians.find_one({"_id": ObjectId(technician_id)})
        # Sinon, essayer de chercher directement avec la chaîne
        if not technician:
            technician = await db.technicians.find_one({"_id": technician_id})
    
    if not technician:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Technicien non trouvé"
        )
    
    # Récupérer les rendez-vous du technicien
    appointments = []
    
    if isinstance(technician_id, ObjectId):
        appointments = await db.appointments.find({"technician_id": technician_id}).to_list(1000)
    else:
        # Si l'ID du technicien est une chaîne, essayer de récupérer les rendez-vous
        # avec l'ID au format chaîne et aussi au format ObjectId si possible
        if ObjectId.is_valid(technician_id):
            appointments = await db.appointments.find({"technician_id": {
                "$in": [technician_id, ObjectId(technician_id)]
            }}).to_list(1000)
        else:
            appointments = await db.appointments.find({"technician_id": technician_id}).to_list(1000)
    
    # Renvoyer les données nécessaires pour afficher le calendrier partagé
    return {
        "technician": {
            "id": str(technician["_id"]),
            "name": f"{technician.get('first_name', '')} {technician.get('last_name', '')}".strip(),
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