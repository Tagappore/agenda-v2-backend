from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import JSONResponse
from bson import ObjectId
from typing import List, Dict, Any, Optional
from datetime import datetime
from app.routes.auth import get_current_user, verify_admin_or_call_center
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
    print(f"Company ID: {current_user.get('company_id')}")
    
    # Préparer les données du prospect
    prospect_data = prospect.dict()
    
    # Ajouter l'ID du call center créateur
    prospect_data["call_center_id"] = current_user.get("id")
    
    # Ajouter le company_id du call center
    if current_user.get("company_id"):
        prospect_data["company_id"] = current_user["company_id"]
    else:
        # Si le call center n'a pas de company_id dans son token,
        # essayer de le récupérer dans la base de données
        user_in_db = await db["users"].find_one({"_id": ObjectId(current_user.get("id"))})
        if user_in_db and user_in_db.get("company_id"):
            prospect_data["company_id"] = user_in_db["company_id"]
            print(f"Récupération du company_id depuis la BD: {prospect_data['company_id']}")
        else:
            print(f"ERREUR: Call center {current_user.get('id')} sans company_id!")
    
    # Ajouter le nom du call center
    if "name" in current_user:
        prospect_data["call_center_name"] = current_user["name"]
    else:
        # Essayer de récupérer le nom depuis la base de données
        user_in_db = await db["users"].find_one({"_id": ObjectId(current_user.get("id"))})
        if user_in_db and user_in_db.get("name"):
            prospect_data["call_center_name"] = user_in_db["name"]
    
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
    
    # Récupérer tous les prospects sans company_id
    prospects = await db["prospects"].find({"company_id": None}).to_list(length=None)
    
    updated_count = 0
    for prospect in prospects:
        if "call_center_id" in prospect:
            # Récupérer le call center
            call_center = await db["users"].find_one({"_id": ObjectId(prospect["call_center_id"])})
            if call_center and call_center.get("company_id"):
                # Mettre à jour le prospect avec le company_id du call center
                await db["prospects"].update_one(
                    {"_id": prospect["_id"]},
                    {"$set": {
                        "company_id": call_center["company_id"],
                        "updated_at": datetime.utcnow()
                    }}
                )
                updated_count += 1
    
    # Maintenant, corriger les prospects sans call_center_name
    prospects_without_name = await db["prospects"].find({
        "call_center_id": {"$exists": True},
        "$or": [
            {"call_center_name": {"$exists": False}},
            {"call_center_name": ""}
        ]
    }).to_list(length=None)
    
    name_count = 0
    for prospect in prospects_without_name:
        call_center = await db["users"].find_one({"_id": ObjectId(prospect["call_center_id"])})
        if call_center and call_center.get("name"):
            await db["prospects"].update_one(
                {"_id": prospect["_id"]},
                {"$set": {
                    "call_center_name": call_center["name"],
                    "updated_at": datetime.utcnow()
                }}
            )
            name_count += 1
    
    return {
        "message": f"{updated_count} prospects mis à jour avec company_id, {name_count} prospects mis à jour avec call_center_name"
    }