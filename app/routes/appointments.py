# app/routes/appointments.py

from fastapi import APIRouter, Depends, HTTPException, status
from typing import List, Dict, Any
from motor.motor_asyncio import AsyncIOMotorDatabase
from bson import ObjectId
from datetime import datetime, timedelta
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

# Modification de la fonction check_appointment_conflict pour mieux gérer les chevauchements

async def check_appointment_conflict(
    db: AsyncIOMotorDatabase,
    technician_id: str,
    appointment_date: datetime,
    company_id: str,
    exclude_appointment_id: str = None
) -> bool:
    """
    Vérifie si un technicien a déjà un rendez-vous à la date et heure spécifiées
    
    Returns:
        bool: True s'il y a un conflit, False sinon
    """
    # Convertir la date de rendez-vous en objet datetime si ce n'est pas déjà le cas
    if isinstance(appointment_date, str):
        appointment_date = datetime.fromisoformat(appointment_date.replace('Z', '+00:00'))
    
    # Créer un intervalle autour du rendez-vous pour vérifier les conflits
    # Un rendez-vous typique dure environ 1 heure
    start_time = appointment_date - timedelta(minutes=15)  # 15 minutes avant
    end_time = appointment_date + timedelta(minutes=45)    # 45 minutes après
    
    # Construire la requête pour trouver les rendez-vous en conflit
    query = {
        "technician_id": technician_id,
        "company_id": company_id,
        "dateTime": {
            "$gte": start_time,
            "$lte": end_time
        }
    }
    
    # Si on met à jour un rendez-vous existant, l'exclure de la recherche
    if exclude_appointment_id:
        query["_id"] = {"$ne": ObjectId(exclude_appointment_id)}
    
    # Rechercher des rendez-vous existants qui pourraient être en conflit
    conflict = await db.appointments.find_one(query)
    
    if conflict:
        # Logguer le conflit pour faciliter le débogage
        print(f"Conflit détecté: Technicien {technician_id} a déjà un RDV à {appointment_date}")
        return True
    
    # Vérifier aussi les absences du technicien
    absence_query = {
        "technician_id": technician_id,
        "start_date": {"$lte": end_time},
        "end_date": {"$gte": start_time}
    }
    
    absence_conflict = await db.absences.find_one(absence_query)
    
    if absence_conflict:
        print(f"Conflit avec une absence: Technicien {technician_id} est indisponible à {appointment_date}")
        return True
    
    return False

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
            
        # Vérifier s'il y a un conflit d'horaire
        has_conflict = await check_appointment_conflict(
            db=db,
            technician_id=appointment_data["technician_id"],
            appointment_date=appointment_data["dateTime"],
            company_id=current_user["company_id"]
        )
        
        if has_conflict:
            raise HTTPException(
                status_code=409,
                detail="Conflit d'horaire: le technicien a déjà un rendez-vous à cette date et heure"
            )

        # Ajouter les champs système
        appointment_data["company_id"] = current_user["company_id"]
        appointment_data["created_at"] = datetime.utcnow()
        appointment_data["updated_at"] = datetime.utcnow()
        appointment_data["status"] = AppointmentStatus.CREATED.value

        result = await db.appointments.insert_one(appointment_data)
        appointment_data["_id"] = result.inserted_id
        
        return format_appointment_response(appointment_data)

    except HTTPException:
        raise
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
        
        # Vérifier s'il y a un conflit d'horaire
        if "dateTime" in appointment_data or "technician_id" in appointment_data:
            technician_id = appointment_data.get("technician_id", existing_appointment["technician_id"])
            appointment_date = appointment_data.get("dateTime", existing_appointment["dateTime"])
            
            has_conflict = await check_appointment_conflict(
                db=db,
                technician_id=technician_id,
                appointment_date=appointment_date,
                company_id=current_user["company_id"],
                exclude_appointment_id=appointment_id
            )
            
            if has_conflict:
                raise HTTPException(
                    status_code=409,
                    detail="Conflit d'horaire: le technicien a déjà un rendez-vous à cette date et heure"
                )

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

    except HTTPException:
        raise
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