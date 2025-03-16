# app/routes/absences.py

from fastapi import APIRouter, Depends, HTTPException, status
from typing import List, Dict, Any
from motor.motor_asyncio import AsyncIOMotorDatabase
from bson import ObjectId
from datetime import datetime
from ..models.absence import AbsenceType, AbsenceCreate, AbsenceUpdate, Absence
from ..config.database import get_database
from .auth import verify_admin

router = APIRouter(tags=["absences"])

def format_absence_response(absence: Dict[str, Any]) -> Dict[str, Any]:
    """Formate la réponse d'absence de manière cohérente"""
    return {
        "id": str(absence.get("_id", "")),
        "title": absence.get("title", ""),
        "start_date": absence.get("start_date"),
        "end_date": absence.get("end_date"),
        "description": absence.get("description", ""),
        "absence_type": absence.get("absence_type", "personal"),
        "technician_id": absence.get("technician_id", ""),
        "company_id": absence.get("company_id", ""),
        "created_at": absence.get("created_at", datetime.utcnow()),
        "updated_at": absence.get("updated_at", datetime.utcnow()),
        "type": "absence",  # Pour compatibilité avec le frontend
        "status": "cancelled"  # Pour le rendu en rouge dans le frontend
    }

@router.get("/absences", response_model=List[Dict[str, Any]])
async def get_absences(
    current_user: dict = Depends(verify_admin),
    db: AsyncIOMotorDatabase = Depends(get_database)
):
    try:
        absences = await db.absences.find({
            "company_id": current_user["company_id"]
        }).sort("start_date", -1).to_list(1000)
        
        return [format_absence_response(absence) for absence in absences]
    except Exception as e:
        print(f"Erreur lors de la récupération des absences: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/absences", response_model=Dict[str, Any])
async def create_absence(
    absence_data: Dict[str, Any],
    current_user: dict = Depends(verify_admin),
    db: AsyncIOMotorDatabase = Depends(get_database)
):
    try:
        # Vérifier que le technicien existe
        technician = await db.users.find_one({
            "_id": ObjectId(absence_data["technician_id"]),
            "company_id": current_user["company_id"]
        })
        if not technician:
            raise HTTPException(status_code=404, detail="Technicien non trouvé")

        # Ajouter les champs système
        absence_data["company_id"] = current_user["company_id"]
        absence_data["created_at"] = datetime.utcnow()
        absence_data["updated_at"] = datetime.utcnow()
        
        # Assurer la compatibilité avec le frontend
        absence_data["type"] = "absence"
        absence_data["status"] = "cancelled"  # Pour le rendu en rouge

        result = await db.absences.insert_one(absence_data)
        absence_data["_id"] = result.inserted_id
        
        return format_absence_response(absence_data)

    except Exception as e:
        print(f"Erreur lors de la création de l'absence: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/absences/{absence_id}", response_model=Dict[str, Any])
async def get_absence(
    absence_id: str,
    current_user: dict = Depends(verify_admin),
    db: AsyncIOMotorDatabase = Depends(get_database)
):
    try:
        absence = await db.absences.find_one({
            "_id": ObjectId(absence_id),
            "company_id": current_user["company_id"]
        })
        
        if not absence:
            raise HTTPException(status_code=404, detail="Absence non trouvée")
            
        return format_absence_response(absence)
        
    except Exception as e:
        print(f"Erreur lors de la récupération de l'absence: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@router.put("/absences/{absence_id}", response_model=Dict[str, Any])
async def update_absence(
    absence_id: str,
    absence_data: Dict[str, Any],
    current_user: dict = Depends(verify_admin),
    db: AsyncIOMotorDatabase = Depends(get_database)
):
    try:
        # Vérifier que l'absence existe
        existing_absence = await db.absences.find_one({
            "_id": ObjectId(absence_id),
            "company_id": current_user["company_id"]
        })
        
        if not existing_absence:
            raise HTTPException(status_code=404, detail="Absence non trouvée")

        # Si le technicien est modifié, vérifier qu'il existe
        if "technician_id" in absence_data:
            technician = await db.users.find_one({
                "_id": ObjectId(absence_data["technician_id"]),
                "company_id": current_user["company_id"]
            })
            if not technician:
                raise HTTPException(status_code=404, detail="Technicien non trouvé")

        # Mettre à jour l'absence
        absence_data["updated_at"] = datetime.utcnow()
        
        # Maintenir les champs pour compatibilité avec le frontend
        absence_data["type"] = "absence"
        absence_data["status"] = "cancelled"  # Pour le rendu en rouge
        
        result = await db.absences.update_one(
            {"_id": ObjectId(absence_id), "company_id": current_user["company_id"]},
            {"$set": absence_data}
        )

        if result.modified_count == 0:
            raise HTTPException(status_code=500, detail="Erreur lors de la mise à jour")

        # Récupérer l'absence mise à jour
        updated_absence = await db.absences.find_one({"_id": ObjectId(absence_id)})
        return format_absence_response(updated_absence)

    except Exception as e:
        print(f"Erreur lors de la modification de l'absence: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@router.delete("/absences/{absence_id}")
async def delete_absence(
    absence_id: str,
    current_user: dict = Depends(verify_admin),
    db: AsyncIOMotorDatabase = Depends(get_database)
):
    try:
        # Vérifier que l'absence existe
        absence = await db.absences.find_one({
            "_id": ObjectId(absence_id),
            "company_id": current_user["company_id"]
        })
        
        if not absence:
            raise HTTPException(status_code=404, detail="Absence non trouvée")

        result = await db.absences.delete_one({
            "_id": ObjectId(absence_id),
            "company_id": current_user["company_id"]
        })
        
        if result.deleted_count == 0:
            raise HTTPException(status_code=500, detail="Erreur lors de la suppression")
            
        return {"message": "Absence supprimée avec succès"}

    except Exception as e:
        print(f"Erreur lors de la suppression de l'absence: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/technicians/{technician_id}/absences", response_model=List[Dict[str, Any]])
async def get_technician_absences(
    technician_id: str,
    current_user: dict = Depends(verify_admin),
    db: AsyncIOMotorDatabase = Depends(get_database)
):
    try:
        # Vérifier que le technicien existe
        technician = await db.users.find_one({
            "_id": ObjectId(technician_id),
            "company_id": current_user["company_id"],
            "role": "technician"
        })
        
        if not technician:
            raise HTTPException(status_code=404, detail="Technicien non trouvé")
        
        # Récupérer toutes les absences pour ce technicien
        absences = await db.absences.find({
            "technician_id": technician_id,
            "company_id": current_user["company_id"]
        }).sort("start_date", -1).to_list(1000)
        
        return [format_absence_response(absence) for absence in absences]
        
    except Exception as e:
        print(f"Erreur lors de la récupération des absences du technicien: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))