from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import JSONResponse
from bson import ObjectId
from typing import Dict, Any, Optional
from datetime import datetime
from app.routes.auth import get_current_user
from pydantic import BaseModel

router = APIRouter()

# Modèle Pydantic pour les prospects
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
    processing_status: str = "new"

# Modèle pour les statistiques
class CallCenterStats(BaseModel):
    totalProspects: int
    newProspects: int
    convertedProspects: int
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
    
    # Préparer les statistiques
    total_prospects = len(prospects)
    new_prospects = len([p for p in prospects if p.get("status") == "new" or p.get("processing_status") == "new"])
    converted_prospects = len([p for p in prospects if p.get("status") == "converted" or p.get("processing_status") == "converted"])
    
    # Récupérer les rendez-vous en attente
    appointments = await db["appointments"].find({
        "company_id": company_id,
        "status": {"$in": ["confirmed", "new_plan"]}
    }).to_list(length=None)
    
    pending_appointments = len(appointments)
    
    # Créer l'objet de statistiques
    stats = {
        "totalProspects": total_prospects,
        "newProspects": new_prospects,
        "convertedProspects": converted_prospects,
        "pendingAppointments": pending_appointments
    }
    
    return stats

# Route pour récupérer tous les prospects d'un call center
@router.get("/prospect/call-center/{call_center_id}")
async def get_prospects_by_call_center(call_center_id: str, current_user: dict = Depends(get_current_user)):
    # Vérifie que l'utilisateur est autorisé (soit le call center lui-même, soit un admin)
    if not (str(current_user.get("_id")) == call_center_id or current_user.get("role") in ["admin", "super_admin"]):
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
    
    # Préparer les données du prospect
    prospect_data = prospect.dict()
    
    # Ajouter l'ID du call center créateur si non présent
    if not prospect_data.get("call_center_id"):
        prospect_data["call_center_id"] = str(current_user.get("_id"))
        
    # Ajouter la date de création
    prospect_data["created_at"] = datetime.utcnow()
    
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
    if not (str(current_user.get("_id")) == prospect.get("call_center_id") or current_user.get("role") in ["admin", "super_admin"]):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Accès non autorisé"
        )
        
    # Empêcher la modification de l'ID du call center ou de la date de création
    if "call_center_id" in prospect_data:
        del prospect_data["call_center_id"]
    if "created_at" in prospect_data:
        del prospect_data["created_at"]
        
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
    if not (str(current_user.get("_id")) == prospect.get("call_center_id") or current_user.get("role") in ["admin", "super_admin"]):
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
    if not (str(current_user.get("_id")) == prospect.get("call_center_id") or current_user.get("role") in ["admin", "super_admin"]):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Accès non autorisé"
        )
        
    return serialize_prospect(prospect)