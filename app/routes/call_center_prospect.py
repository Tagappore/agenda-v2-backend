from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import JSONResponse
from bson import ObjectId
from typing import List, Dict, Any, Optional
from datetime import datetime
from app.routes.auth import get_current_user, verify_admin_or_call_center
from pydantic import BaseModel
from enum import Enum

router = APIRouter()

# Définir l'énumération de statut de traitement pour s'aligner sur le modèle principal
class ProcessingStatus(str, Enum):
    CREATED = "created"      # Nouveau
    CONFIRMED = "confirmed"  # Placé
    NEW_PLAN = "new_plan"    # Replanifier
    COMPLETED = "completed"  # Terminé
    CANCELLED = "cancelled"  # Annulé

# Modèle Pydantic pour les prospects avec statut mis à jour
class ProspectBase(BaseModel):
    first_name: str
    last_name: str
    address: str
    city: str
    postal_code: str
    housing_type: str
    status: str
    age: Optional[int] = None
    annual_income: str
    email: str
    phone_home: Optional[str] = None
    phone_mobile: str
    comments: Optional[str] = None
    call_center_id: Optional[str] = None
    processing_status: ProcessingStatus = ProcessingStatus.CREATED

# Modèle pour les statistiques - mis à jour pour utiliser les statuts corrects
class CallCenterStats(BaseModel):
    totalProspects: int
    newProspects: int  # Prospects avec status "created"
    placedProspects: int  # Prospects avec status "confirmed"
    pendingAppointments: int

# Convertir ObjectId en str pour la sérialisation JSON
def serialize_prospect(prospect: Dict[str, Any]) -> Dict[str, Any]:
    if prospect:
        prospect["id"] = str(prospect.pop("_id"))
        
        # Convertir les dates en strings
        if "created_at" in prospect and isinstance(prospect["created_at"], datetime):
            prospect["created_at"] = prospect["created_at"].isoformat()
        if "updated_at" in prospect and isinstance(prospect["updated_at"], datetime):
            prospect["updated_at"] = prospect["updated_at"].isoformat()
            
    return prospect

# Route pour récupérer les statistiques d'un call center
@router.get("/call-center/stats/{company_id}", response_model=CallCenterStats)
async def get_call_center_stats(company_id: str, current_user: dict = Depends(get_current_user)):
    # Vérifie que l'utilisateur appartient à la société ou est un admin
    if not (current_user.get("company_id") == company_id or current_user.get("role") in ["admin", "super_admin"]):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Accès non autorisé"
        )
        
    # Récupérer la connexion à la base de données
    db = current_user["request"].app.mongodb
    
    # Récupérer tous les prospects associés au call center
    prospects = await db["prospects"].find({"call_center_id": company_id}).to_list(length=None)
    
    # Préparer les statistiques avec les statuts corrects
    total_prospects = len(prospects)
    new_prospects = len([p for p in prospects if p.get("processing_status") == ProcessingStatus.CREATED.value])
    placed_prospects = len([p for p in prospects if p.get("processing_status") == ProcessingStatus.CONFIRMED.value])
    
    # Récupérer les rendez-vous en attente
    appointments = await db["appointments"].find({
        "company_id": company_id,
        "status": {"$in": [ProcessingStatus.CONFIRMED.value, ProcessingStatus.NEW_PLAN.value]}
    }).to_list(length=None)
    
    pending_appointments = len(appointments)
    
    # Créer l'objet de statistiques
    stats = {
        "totalProspects": total_prospects,
        "newProspects": new_prospects,
        "placedProspects": placed_prospects,
        "pendingAppointments": pending_appointments
    }
    
    return stats

# Route pour récupérer tous les prospects d'un call center
@router.get("/prospect/call-center/{call_center_id}")
async def get_prospects_by_call_center(call_center_id: str, current_user: dict = Depends(get_current_user)):
    # Vérifie que l'utilisateur est autorisé (soit le call center lui-même, soit un admin)
    if not (str(current_user.get("id")) == call_center_id or current_user.get("role") in ["admin", "super_admin"]):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Accès non autorisé"
        )
        
    # Récupérer la connexion à la base de données
    db = current_user["request"].app.mongodb
    
    # Récupérer tous les prospects associés au call center
    prospects = await db["prospects"].find({"call_center_id": call_center_id}).to_list(length=None)
    
    # Convertir les ObjectId en strings
    serialized_prospects = [serialize_prospect(prospect) for prospect in prospects]
    
    return serialized_prospects

# Route pour créer un nouveau prospect pour un call center
@router.post("/prospect", status_code=status.HTTP_201_CREATED)
async def create_prospect(prospect: ProspectBase, current_user: dict = Depends(get_current_user)):
    # Vérifie que l'utilisateur est un call center
    if current_user.get("role") != "call_center":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Seuls les call centers peuvent créer des prospects"
        )
        
    # Récupérer la connexion à la base de données
    db = current_user["request"].app.mongodb
    
    # Logs de débogage
    print(f"Création de prospect par {current_user['email']} (rôle: {current_user['role']})")
    
    # Préparer les données du prospect
    prospect_data = prospect.dict()
    
    # Vérifier que processing_status est une valeur valide
    if prospect_data['processing_status'] not in [status.value for status in ProcessingStatus]:
        prospect_data['processing_status'] = ProcessingStatus.CREATED.value
    
    # Ajouter l'ID du call center
    prospect_data["call_center_id"] = current_user.get("id")
    
    # Ajouter le company_id du call center
    prospect_data["company_id"] = current_user.get("company_id")
    
    # CRUCIAL: Récupérer le call center pour obtenir son nom
    try:
        call_center = await db["users"].find_one({"_id": ObjectId(current_user.get("id"))})
        if call_center:
            # Définir le nom du call center
            prospect_data["call_center_name"] = call_center.get("name", "")
            print(f"Nom du call center défini: {prospect_data['call_center_name']}")
            
            # Fallbacks si name est vide
            if not prospect_data["call_center_name"]:
                if call_center.get("username"):
                    prospect_data["call_center_name"] = call_center["username"]
                elif call_center.get("email"):
                    prospect_data["call_center_name"] = call_center["email"]
                else:
                    prospect_data["call_center_name"] = "Call Center"
                print(f"Fallback - Nom du call center: {prospect_data['call_center_name']}")
    except Exception as e:
        print(f"Erreur lors de la récupération du call center: {str(e)}")
        prospect_data["call_center_name"] = "Call Center"
    
    # Ajouter les dates
    prospect_data["created_at"] = datetime.utcnow()
    prospect_data["updated_at"] = datetime.utcnow()
    
    print(f"Données du prospect à insérer: {prospect_data}")
    
    # Insérer le prospect dans la base de données
    result = await db["prospects"].insert_one(prospect_data)
    
    # Récupérer le prospect créé
    created_prospect = await db["prospects"].find_one({"_id": result.inserted_id})
    
    return serialize_prospect(created_prospect)

# Route pour mettre à jour un prospect
@router.put("/prospect/{prospect_id}")
async def update_prospect(prospect_id: str, prospect_data: Dict[str, Any], current_user: dict = Depends(get_current_user)):
    # Récupérer la connexion à la base de données
    db = current_user["request"].app.mongodb
    
    # Récupérer le prospect
    try:
        prospect = await db["prospects"].find_one({"_id": ObjectId(prospect_id)})
    except:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="ID de prospect invalide"
        )
    
    if not prospect:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Prospect non trouvé"
        )
        
    # Vérifier que l'utilisateur est autorisé (soit le call center associé, soit un admin)
    if not (str(current_user.get("id")) == prospect.get("call_center_id") or current_user.get("role") in ["admin", "super_admin"]):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Accès non autorisé"
        )
        
    # Empêcher la modification de certains champs
    protected_fields = ["call_center_id", "company_id", "created_at"]
    for field in protected_fields:
        if field in prospect_data:
            del prospect_data[field]
    
    # Valider le statut de traitement si présent
    if "processing_status" in prospect_data and prospect_data["processing_status"] not in [status.value for status in ProcessingStatus]:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Statut de traitement invalide. Valeurs possibles: {[s.value for s in ProcessingStatus]}"
        )
        
    # Ajouter la date de mise à jour
    prospect_data["updated_at"] = datetime.utcnow()
    
    # Mettre à jour le prospect
    await db["prospects"].update_one(
        {"_id": ObjectId(prospect_id)},
        {"$set": prospect_data}
    )
    
    # Récupérer le prospect mis à jour
    updated_prospect = await db["prospects"].find_one({"_id": ObjectId(prospect_id)})
    
    return serialize_prospect(updated_prospect)

# Route pour supprimer un prospect
@router.delete("/prospect/{prospect_id}", status_code=status.HTTP_200_OK)
async def delete_prospect(prospect_id: str, current_user: dict = Depends(get_current_user)):
    # Récupérer la connexion à la base de données
    db = current_user["request"].app.mongodb
    
    # Récupérer le prospect
    try:
        prospect = await db["prospects"].find_one({"_id": ObjectId(prospect_id)})
    except:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="ID de prospect invalide"
        )
    
    if not prospect:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Prospect non trouvé"
        )
        
    # Vérifier que l'utilisateur est autorisé (soit le call center associé, soit un admin)
    if not (str(current_user.get("id")) == prospect.get("call_center_id") or current_user.get("role") in ["admin", "super_admin"]):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Accès non autorisé"
        )
        
    # Supprimer le prospect
    await db["prospects"].delete_one({"_id": ObjectId(prospect_id)})
    
    return {"message": "Prospect supprimé avec succès"}

# Route pour récupérer un prospect spécifique
@router.get("/prospect/{prospect_id}")
async def get_prospect(prospect_id: str, current_user: dict = Depends(get_current_user)):
    # Récupérer la connexion à la base de données
    db = current_user["request"].app.mongodb
    
    # Récupérer le prospect
    try:
        prospect = await db["prospects"].find_one({"_id": ObjectId(prospect_id)})
    except:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="ID de prospect invalide"
        )
    
    if not prospect:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Prospect non trouvé"
        )
        
    # Vérifier que l'utilisateur est autorisé (soit le call center associé, soit un admin)
    if not (str(current_user.get("id")) == prospect.get("call_center_id") or current_user.get("role") in ["admin", "super_admin"]):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Accès non autorisé"
        )
        
    return serialize_prospect(prospect)

# Route pour corriger les prospects existants
@router.post("/fix-prospects")
async def fix_prospects(current_user: dict = Depends(verify_admin_or_call_center)):
    # Vérifier que l'utilisateur est un admin
    if current_user.get("role") not in ["admin", "super_admin"]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Seuls les administrateurs peuvent utiliser cette fonction"
        )
    
    # Récupérer la connexion à la base de données
    db = current_user["request"].app.mongodb
    
    # Récupérer tous les prospects sans call_center_name ou avec call_center_name vide
    prospects = await db["prospects"].find({
        "call_center_id": {"$exists": True},
        "$or": [
            {"call_center_name": {"$exists": False}},
            {"call_center_name": ""}
        ]
    }).to_list(length=None)
    
    print(f"Nombre de prospects à corriger: {len(prospects)}")
    
    updated_count = 0
    for prospect in prospects:
        try:
            # Récupérer le call center
            call_center = await db["users"].find_one({"_id": ObjectId(prospect["call_center_id"])})
            
            call_center_name = None
            if call_center:
                # Essayer différents champs pour trouver un nom
                for field in ["name", "username", "email"]:
                    if field in call_center and call_center[field]:
                        call_center_name = call_center[field]
                        break
            
            # Si aucun nom n'est trouvé, utiliser une valeur par défaut
            if not call_center_name:
                call_center_name = "Call Center #" + prospect["call_center_id"]
            
            # Mettre à jour le prospect
            update_result = await db["prospects"].update_one(
                {"_id": prospect["_id"]},
                {"$set": {
                    "call_center_name": call_center_name,
                    "updated_at": datetime.utcnow()
                }}
            )
            
            if update_result.modified_count > 0:
                updated_count += 1
                print(f"Prospect {prospect['_id']} mis à jour avec call_center_name: {call_center_name}")
        
        except Exception as e:
            print(f"Erreur lors de la mise à jour du prospect {prospect['_id']}: {str(e)}")
    
    return {"message": f"{updated_count} prospects mis à jour sur {len(prospects)} à corriger"}