# app/routes/appointments.py

from fastapi import APIRouter, Depends, HTTPException, status
from typing import List, Dict, Any
from motor.motor_asyncio import AsyncIOMotorDatabase
from bson import ObjectId
from datetime import datetime
from ..models.appointment import AppointmentCreate, AppointmentUpdate, Appointment, AppointmentStatus
from ..config.database import get_database
from .auth import verify_admin

router = APIRouter(tags=["appointments"])

def format_appointment_response(appointment: Dict[str, Any]) -> Dict[str, Any]:
    """Formate la réponse du rendez-vous de manière cohérente"""
    return {
        "id": str(appointment.get("_id", "")),
        "dateTime": appointment.get("dateTime"),
        "comment": appointment.get("comment", ""),
        "name": appointment.get("name", ""),
        "address": appointment.get("address", ""),
        "city": appointment.get("city", ""),
        "postal_code": appointment.get("postal_code", ""),
        "phone": appointment.get("phone", ""),
        "technician_id": appointment.get("technician_id", ""),
        "prospect_id": appointment.get("prospect_id", ""),
        "status": appointment.get("status", "created"),
        "company_id": appointment.get("company_id", ""),
        "created_at": appointment.get("created_at", datetime.utcnow()),
        "updated_at": appointment.get("updated_at", datetime.utcnow())
    }

@router.get("/appointments", response_model=List[Dict[str, Any]])
async def get_appointments(
    current_user: dict = Depends(verify_admin),
    db: AsyncIOMotorDatabase = Depends(get_database)
):
    try:
        appointments = await db.appointments.find({
            "company_id": current_user["company_id"]
        }).sort("dateTime", -1).to_list(1000)
        
        return [format_appointment_response(appointment) for appointment in appointments]
    except Exception as e:
        print(f"Erreur lors de la récupération des rendez-vous: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/appointments", response_model=Dict[str, Any])
async def create_appointment(
    appointment_data: Dict[str, Any],
    current_user: dict = Depends(verify_admin),
    db: AsyncIOMotorDatabase = Depends(get_database)
):
    try:
        # Vérifier que le prospect existe
        prospect = await db.prospects.find_one({
            "_id": ObjectId(appointment_data["prospect_id"]),
            "company_id": current_user["company_id"]
        })
        if not prospect:
            raise HTTPException(status_code=404, detail="Prospect non trouvé")

        # Vérifier que le technicien existe
        technician = await db.users.find_one({
            "_id": ObjectId(appointment_data["technician_id"]),
            "company_id": current_user["company_id"]
        })
        if not technician:
            raise HTTPException(status_code=404, detail="Technicien non trouvé")

        # Ajouter les champs système
        appointment_data["company_id"] = current_user["company_id"]
        appointment_data["created_at"] = datetime.utcnow()
        appointment_data["updated_at"] = datetime.utcnow()
        appointment_data["status"] = AppointmentStatus.CREATED.value

        result = await db.appointments.insert_one(appointment_data)
        appointment_data["_id"] = result.inserted_id
        
        return format_appointment_response(appointment_data)

    except Exception as e:
        print(f"Erreur lors de la création du rendez-vous: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/appointments/{appointment_id}", response_model=Dict[str, Any])
async def get_appointment(
    appointment_id: str,
    current_user: dict = Depends(verify_admin),
    db: AsyncIOMotorDatabase = Depends(get_database)
):
    try:
        appointment = await db.appointments.find_one({
            "_id": ObjectId(appointment_id),
            "company_id": current_user["company_id"]
        })
        
        if not appointment:
            raise HTTPException(status_code=404, detail="Rendez-vous non trouvé")
            
        return format_appointment_response(appointment)
        
    except Exception as e:
        print(f"Erreur lors de la récupération du rendez-vous: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@router.put("/appointments/{appointment_id}", response_model=Dict[str, Any])
async def update_appointment(
    appointment_id: str,
    appointment_data: Dict[str, Any],
    current_user: dict = Depends(verify_admin),
    db: AsyncIOMotorDatabase = Depends(get_database)
):
    try:
        # Vérifier que le rendez-vous existe
        existing_appointment = await db.appointments.find_one({
            "_id": ObjectId(appointment_id),
            "company_id": current_user["company_id"]
        })
        
        if not existing_appointment:
            raise HTTPException(status_code=404, detail="Rendez-vous non trouvé")

        # Si le technicien est modifié, vérifier qu'il existe
        if "technician_id" in appointment_data:
            technician = await db.users.find_one({
                "_id": ObjectId(appointment_data["technician_id"]),
                "company_id": current_user["company_id"]
            })
            if not technician:
                raise HTTPException(status_code=404, detail="Technicien non trouvé")

        # Mettre à jour le rendez-vous
        appointment_data["updated_at"] = datetime.utcnow()
        
        result = await db.appointments.update_one(
            {"_id": ObjectId(appointment_id), "company_id": current_user["company_id"]},
            {"$set": appointment_data}
        )

        if result.modified_count == 0:
            raise HTTPException(status_code=500, detail="Erreur lors de la mise à jour")

        # Récupérer le rendez-vous mis à jour
        updated_appointment = await db.appointments.find_one({"_id": ObjectId(appointment_id)})
        return format_appointment_response(updated_appointment)

    except Exception as e:
        print(f"Erreur lors de la modification du rendez-vous: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@router.delete("/appointments/{appointment_id}")
async def delete_appointment(
    appointment_id: str,
    current_user: dict = Depends(verify_admin),
    db: AsyncIOMotorDatabase = Depends(get_database)
):
    try:
        # Vérifier que le rendez-vous existe
        appointment = await db.appointments.find_one({
            "_id": ObjectId(appointment_id),
            "company_id": current_user["company_id"]
        })
        
        if not appointment:
            raise HTTPException(status_code=404, detail="Rendez-vous non trouvé")

        result = await db.appointments.delete_one({
            "_id": ObjectId(appointment_id),
            "company_id": current_user["company_id"]
        })
        
        if result.deleted_count == 0:
            raise HTTPException(status_code=500, detail="Erreur lors de la suppression")
            
        return {"message": "Rendez-vous supprimé avec succès"}

    except Exception as e:
        print(f"Erreur lors de la suppression du rendez-vous: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@router.put("/appointments/{appointment_id}/status", response_model=Dict[str, Any])
async def update_appointment_status(
    appointment_id: str,
    status: AppointmentStatus,
    current_user: dict = Depends(verify_admin),
    db: AsyncIOMotorDatabase = Depends(get_database)
):
    try:
        appointment = await db.appointments.find_one({
            "_id": ObjectId(appointment_id),
            "company_id": current_user["company_id"]
        })
        
        if not appointment:
            raise HTTPException(status_code=404, detail="Rendez-vous non trouvé")

        result = await db.appointments.update_one(
            {"_id": ObjectId(appointment_id)},
            {
                "$set": {
                    "status": status.value,
                    "updated_at": datetime.utcnow()
                }
            }
        )

        if result.modified_count == 0:
            raise HTTPException(status_code=500, detail="Erreur lors de la mise à jour du statut")

        updated_appointment = await db.appointments.find_one({"_id": ObjectId(appointment_id)})
        return format_appointment_response(updated_appointment)

    except Exception as e:
        print(f"Erreur lors de la mise à jour du statut: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))