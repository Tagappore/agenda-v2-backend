from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import JSONResponse
from typing import List, Dict, Any, Optional
from motor.motor_asyncio import AsyncIOMotorDatabase
from pydantic import BaseModel, EmailStr, constr
from enum import Enum
from .auth import verify_admin
from app.config.database import get_database
from bson import ObjectId
from datetime import datetime

router = APIRouter(tags=["prospects"])

class ProcessingStatus(str, Enum):
    CREATED = "created"      # Nouveau
    CONFIRMED = "confirmed"  # Placé
    NEW_PLAN = "new_plan"    # Replanifier
    COMPLETED = "completed"  # Terminé
    CANCELLED = "cancelled"  # Annulé

class HousingType(str, Enum):
    HOUSE = "house"
    APARTMENT = "apartment"

class OccupancyStatus(str, Enum):
    OWNER = "owner"
    TENANT = "tenant"
    HOSTED = "hosted"

class ProspectBase(BaseModel):
    first_name: str
    last_name: str
    phone_home: Optional[str] = None
    phone_mobile: Optional[str] = None
    email: EmailStr
    address: str
    city: str
    postal_code: str
    housing_type: HousingType
    status: OccupancyStatus
    age: Optional[int] = None
    annual_income: int
    comments: Optional[str] = None
    call_center_name: Optional[str] = None
    processing_status: ProcessingStatus = ProcessingStatus.CREATED

def format_prospect_response(prospect: Dict[str, Any]) -> Dict[str, Any]:
    """Formate la réponse du prospect de manière cohérente"""
    return {
        "id": str(prospect.get("_id", "")),
        "first_name": prospect.get("first_name", ""),
        "last_name": prospect.get("last_name", ""),
        "phone_home": prospect.get("phone_home", ""),
        "phone_mobile": prospect.get("phone_mobile", ""),
        "email": prospect.get("email", ""),
        "address": prospect.get("address", ""),
        "city": prospect.get("city", ""),
        "postal_code": prospect.get("postal_code", ""),
        "housing_type": prospect.get("housing_type", ""),
        "status": prospect.get("status", ""),
        "age": prospect.get("age"),
        "annual_income": prospect.get("annual_income", 0),
        "comments": prospect.get("comments", ""),
        "company_id": prospect.get("company_id", ""),
        "call_center_name": prospect.get("call_center_name", ""),
        "processing_status": prospect.get("processing_status", "new"),
        "created_at": prospect.get("created_at", datetime.utcnow()),
        "updated_at": prospect.get("updated_at", datetime.utcnow())
    }

@router.get("/prospects/search", response_model=List[Dict[str, Any]])
async def search_prospects(
    query: str,
    current_user: dict = Depends(verify_admin),
    db: AsyncIOMotorDatabase = Depends(get_database)
):
    try:
        # Logs détaillés pour le débogage
        print("=== Début de la recherche de prospects ===")
        print(f"Query reçue: '{query}'")
        print(f"Company ID de l'utilisateur: {current_user.get('company_id')}")

        # Nettoyage de la requête
        query = query.strip()
        search_regex = {"$regex": f".*{query}.*", "$options": "i"}
        
        # Construire la requête MongoDB
        search_query = {
            "company_id": current_user["company_id"],
            "$or": [
                {"first_name": search_regex},
                {"last_name": search_regex}
            ]
        }
        
        print("Requête MongoDB:", search_query)

        # Exécuter la recherche
        prospects = await db.prospects.find(search_query).limit(10).to_list(10)
        
        print(f"Nombre de résultats trouvés: {len(prospects)}")
        if len(prospects) > 0:
            print("Premier résultat:", prospects[0])
        else:
            # Vérifier s'il y a des prospects pour cette company_id
            total_prospects = await db.prospects.count_documents({"company_id": current_user["company_id"]})
            print(f"Nombre total de prospects pour cette company: {total_prospects}")
            
            # Rechercher sans le filtre company_id pour déboguer
            all_matches = await db.prospects.find({
                "$or": [
                    {"first_name": search_regex},
                    {"last_name": search_regex}
                ]
            }).to_list(10)
            print(f"Résultats sans filtre company_id: {len(all_matches)}")
            if len(all_matches) > 0:
                print("Company IDs trouvées:", [p.get("company_id") for p in all_matches])

        print("=== Fin de la recherche ===")
        
        # Formater la réponse
        formatted_prospects = [{
            "id": str(prospect["_id"]),
            "first_name": prospect.get("first_name", ""),
            "last_name": prospect.get("last_name", ""),
            "email": prospect.get("email", ""),
            "address": prospect.get("address", ""),
            "city": prospect.get("city", ""),
            "postal_code": prospect.get("postal_code", ""),
            "phone": prospect.get("phone", "")
        } for prospect in prospects]
        
        return JSONResponse(
            content=formatted_prospects,
            headers={
                "Access-Control-Allow-Origin": "*",
                "Content-Type": "application/json",
                "Cache-Control": "no-cache"
            }
        )
        
    except Exception as e:
        print(f"Erreur lors de la recherche: {str(e)}")
        print(f"Type d'erreur: {type(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/prospects", response_model=List[Dict[str, Any]])
async def get_prospects(
    current_user: dict = Depends(verify_admin),
    db: AsyncIOMotorDatabase = Depends(get_database)
):
    try:
        prospects = await db.prospects.find(
            {"company_id": current_user["company_id"]}
        ).to_list(1000)
        
        return [format_prospect_response(prospect) for prospect in prospects]
        
    except Exception as e:
        print(f"Erreur lors de la récupération des prospects: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/prospects", response_model=Dict[str, Any])
async def create_prospect(
    prospect_data: Dict[str, Any],
    current_user: dict = Depends(verify_admin),
    db: AsyncIOMotorDatabase = Depends(get_database)
):
    try:
        # Vérifier si l'email existe déjà
        if await db.prospects.find_one({"email": prospect_data["email"]}):
            raise HTTPException(status_code=409, detail="Email déjà utilisé")

        # Valider et définir le statut de traitement par défaut
        prospect_data["processing_status"] = "created"  
        
        # Créer le prospect
        prospect_data["company_id"] = current_user["company_id"]
        prospect_data["created_at"] = datetime.utcnow()
        prospect_data["updated_at"] = datetime.utcnow()

        result = await db.prospects.insert_one(prospect_data)
        prospect_data["_id"] = result.inserted_id
        
        return format_prospect_response(prospect_data)

    except Exception as e:
        print(f"Erreur lors de la création du prospect: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/prospects/{prospect_id}", response_model=Dict[str, Any])
async def get_prospect(
    prospect_id: str,
    current_user: dict = Depends(verify_admin),
    db: AsyncIOMotorDatabase = Depends(get_database)
):
    try:
        prospect = await db.prospects.find_one({
            "_id": ObjectId(prospect_id),
            "company_id": current_user["company_id"]
        })
        
        if not prospect:
            raise HTTPException(status_code=404, detail="Prospect non trouvé")
            
        return format_prospect_response(prospect)
        
    except Exception as e:
        print(f"Erreur lors de la récupération du prospect: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@router.put("/prospects/{prospect_id}", response_model=Dict[str, Any])
async def update_prospect(
    prospect_id: str,
    prospect_data: Dict[str, Any],
    current_user: dict = Depends(verify_admin),
    db: AsyncIOMotorDatabase = Depends(get_database)
):
    try:
        prospect_oid = ObjectId(prospect_id)
        
        # Vérifier si le prospect existe
        existing_prospect = await db.prospects.find_one({
            "_id": prospect_oid,
            "company_id": current_user["company_id"]
        })
        
        if not existing_prospect:
            raise HTTPException(status_code=404, detail="Prospect non trouvé")

        # Vérifier l'email unique si modifié
        if prospect_data.get("email") and prospect_data["email"] != existing_prospect["email"]:
            email_exists = await db.prospects.find_one({
                "email": prospect_data["email"],
                "_id": {"$ne": prospect_oid}
            })
            if email_exists:
                raise HTTPException(status_code=409, detail="Email déjà utilisé")

        # Valider le statut de traitement
        if "processing_status" in prospect_data:
            if prospect_data["processing_status"] not in [status.value for status in ProcessingStatus]:
                raise HTTPException(
                    status_code=400,
                    detail=f"Statut de traitement invalide. Valeurs possibles: {[s.value for s in ProcessingStatus]}"
                )

        # Mettre à jour les données
        prospect_data["updated_at"] = datetime.utcnow()
        result = await db.prospects.update_one(
            {"_id": prospect_oid, "company_id": current_user["company_id"]},
            {"$set": prospect_data}
        )

        if result.modified_count == 0:
            raise HTTPException(status_code=500, detail="Erreur lors de la mise à jour")
            
        # Récupérer le prospect mis à jour
        updated_prospect = await db.prospects.find_one({"_id": prospect_oid})
        return format_prospect_response(updated_prospect)

    except Exception as e:
        print(f"Erreur lors de la modification du prospect: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@router.delete("/prospects/{prospect_id}")
async def delete_prospect(
    prospect_id: str,
    current_user: dict = Depends(verify_admin),
    db: AsyncIOMotorDatabase = Depends(get_database)
):
    try:
        prospect_oid = ObjectId(prospect_id)
        
        # Vérifier si le prospect existe
        prospect = await db.prospects.find_one({
            "_id": prospect_oid,
            "company_id": current_user["company_id"]
        })
        
        if not prospect:
            raise HTTPException(status_code=404, detail="Prospect non trouvé")

        result = await db.prospects.delete_one({
            "_id": prospect_oid,
            "company_id": current_user["company_id"]
        })
        
        if result.deleted_count == 0:
            raise HTTPException(status_code=500, detail="Erreur lors de la suppression")
            
        return {"message": "Prospect supprimé avec succès"}

    except Exception as e:
        print(f"Erreur lors de la suppression du prospect: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))
