from fastapi import APIRouter, Depends, HTTPException, status, File, Form, UploadFile
from typing import List, Dict, Any, Optional
from datetime import datetime
from motor.motor_asyncio import AsyncIOMotorDatabase
from ..services.auth import AuthService
from ..models.user import UserCreate, User, UserUpdate, AgentCreate, UserRole
from .auth import verify_admin_or_call_center as verify_admin, get_auth_service
from app.config.database import get_database
from bson import ObjectId
import os
import httpx
from passlib.context import CryptContext
import secrets
import string

router = APIRouter(prefix="/admin-user", tags=["admin"])
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

# Fonctions utilitaires
def generate_password(length=12):
    alphabet = string.ascii_letters + string.digits + "!@#$%^&*"
    return ''.join(secrets.choice(alphabet) for _ in range(length))

def format_user_response(user: Dict[str, Any], include_password: bool = False) -> Dict[str, Any]:
    formatted_user = {
        "id": str(user.get("_id", "")),
        "email": user.get("email", ""),
        "username": user.get("username", ""),
        "role": user.get("role", ""),
        "is_active": user.get("is_active", True),
        "first_name": user.get("first_name", ""),
        "last_name": user.get("last_name", ""),
        "phone": user.get("phone", ""),
        "address": user.get("address", ""),
        "city": user.get("city", ""),
        "postal_code": user.get("postal_code", ""),
        "photo": user.get("photo"),
        "company_id": user.get("company_id", ""),
        "created_at": user.get("created_at", datetime.utcnow()),
        "updated_at": user.get("updated_at", datetime.utcnow())
    }
    
    if include_password and "password" in user:
        formatted_user["password"] = user["password"]
    
    return formatted_user

# Routes pour les utilisateurs
@router.get("/users", response_model=List[Dict[str, Any]])
async def get_users(
    current_user: dict = Depends(verify_admin),
    db: AsyncIOMotorDatabase = Depends(get_database)
):
    try:
        users = await db.users.find({
            "role": {"$in": ["agent", "technician"]},
            "company_id": current_user["company_id"]
        }).to_list(1000)
        
        return [format_user_response(user) for user in users]
    
    except Exception as e:
        print(f"Erreur lors de la récupération des utilisateurs: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/users/{user_id}", response_model=Dict[str, Any])
async def get_user(
    user_id: str,
    current_user: dict = Depends(verify_admin),
    db: AsyncIOMotorDatabase = Depends(get_database)
):
    try:
        user = await db.users.find_one({
            "_id": ObjectId(user_id),
            "company_id": current_user["company_id"],
            "role": {"$in": ["agent", "technician"]}
        })
        
        if not user:
            raise HTTPException(status_code=404, detail="Utilisateur non trouvé")
            
        return format_user_response(user)
        
    except Exception as e:
        print(f"Erreur lors de la récupération de l'utilisateur: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@router.put("/users/{user_id}", response_model=Dict[str, Any])
async def update_user(
    user_id: str,
    user_update: UserUpdate,
    current_user: dict = Depends(verify_admin),
    db: AsyncIOMotorDatabase = Depends(get_database)
):
    try:
        user_oid = ObjectId(user_id)
        
        existing_user = await db.users.find_one({
            "_id": user_oid,
            "company_id": current_user["company_id"],
            "role": {"$in": ["agent", "technician"]}
        })
        
        if not existing_user:
            raise HTTPException(status_code=404, detail="Utilisateur non trouvé")

        if user_update.email and user_update.email != existing_user["email"]:
            existing_email = await db.users.find_one({
                "email": user_update.email,
                "_id": {"$ne": user_oid}
            })
            if existing_email:
                raise HTTPException(
                    status_code=409,
                    detail="Cette adresse email est déjà utilisée"
                )

        update_data = {
            k: v for k, v in user_update.dict(exclude_unset=True).items() if v is not None
        }
        update_data["updated_at"] = datetime.utcnow()

        result = await db.users.update_one(
            {"_id": user_oid, "company_id": current_user["company_id"]},
            {"$set": update_data}
        )

        if result.modified_count == 0:
            raise HTTPException(status_code=500, detail="Erreur lors de la mise à jour")

        updated_user = await db.users.find_one({"_id": user_oid})
        return format_user_response(updated_user)

    except Exception as e:
        print(f"Erreur lors de la modification de l'utilisateur: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@router.delete("/users/{user_id}")
async def delete_user(
    user_id: str,
    current_user: dict = Depends(verify_admin),
    db: AsyncIOMotorDatabase = Depends(get_database)
):
    try:
        user_oid = ObjectId(user_id)
        
        # Vérifier si l'utilisateur existe et récupérer ses informations
        user = await db.users.find_one({
            "_id": user_oid,
            "company_id": current_user["company_id"],
            "role": {"$in": ["agent", "technician"]}
        })
        
        if not user:
            raise HTTPException(status_code=404, detail="Utilisateur non trouvé")

        # Supprimer la photo si elle existe
        if user.get("photo"):
            photo_path = user["photo"].replace("/static/", "static/")
            if os.path.exists(photo_path):
                os.remove(photo_path)

        result = await db.users.delete_one({
            "_id": user_oid,
            "company_id": current_user["company_id"]
        })
        
        if result.deleted_count == 0:
            raise HTTPException(status_code=500, detail="Erreur lors de la suppression")
            
        return {"message": "Utilisateur supprimé avec succès"}

    except Exception as e:
        print(f"Erreur lors de la suppression de l'utilisateur: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@router.patch("/users/{user_id}/status")
async def toggle_user_status(
    user_id: str,
    status_update: dict,
    current_user: dict = Depends(verify_admin),
    db: AsyncIOMotorDatabase = Depends(get_database)
):
    try:
        user_oid = ObjectId(user_id)
        
        user = await db.users.find_one({
            "_id": user_oid,
            "company_id": current_user["company_id"],
            "role": {"$in": ["agent", "technician"]}
        })
        
        if not user:
            raise HTTPException(status_code=404, detail="Utilisateur non trouvé")

        is_active = status_update.get("is_active")
        if is_active is None:
            raise HTTPException(
                status_code=400,
                detail="Le champ is_active est requis"
            )

        result = await db.users.update_one(
            {"_id": user_oid, "company_id": current_user["company_id"]},
            {"$set": {
                "is_active": is_active,
                "updated_at": datetime.utcnow()
            }}
        )

        if result.modified_count == 0:
            raise HTTPException(status_code=500, detail="Erreur lors de la mise à jour du statut")

        updated_user = await db.users.find_one({"_id": user_oid})
        return format_user_response(updated_user)

    except Exception as e:
        print(f"Erreur lors de la modification du statut: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

# Route des statistiques
@router.get("/dashboard/stats")
async def get_dashboard_stats(
    current_user: dict = Depends(verify_admin),
    auth_service: AuthService = Depends(get_auth_service)
):
    try:
        # Statistiques globales qui ne nécessitent pas de company_id
        stats = {
            "total_agents": await auth_service.count_users_by_role("agent"),
            "total_technicians": await auth_service.count_users_by_role("technician"),
            "total_call_centers": await auth_service.count_users_by_role("call_center"),
            "active_agents": await auth_service.count_active_users_by_role("agent"),
            "active_technicians": await auth_service.count_active_users_by_role("technician"),
            "active_call_centers": await auth_service.count_active_users_by_role("call_center"),
        }

        # Statistiques spécifiques à l'entreprise
        if "company_id" in current_user and current_user["company_id"]:
            company_stats = {
                "total_appointments": await auth_service.count_total_appointments(current_user["company_id"]),
                "pending_appointments": await auth_service.count_pending_appointments(current_user["company_id"]),
                "todays_appointments": await auth_service.count_todays_appointments(current_user["company_id"]),
                "total_calls": 0,  # Temporairement à 0
                "todays_calls": 0,  # Temporairement à 0
                "total_prospects": await auth_service.count_total_prospects(current_user["company_id"]),
                "completion_rate": await auth_service.calculate_completion_rate(current_user["company_id"])
            }
            stats.update(company_stats)
        else:
            stats.update({
                "total_appointments": 0,
                "pending_appointments": 0,
                "todays_appointments": 0,
                "total_calls": 0,
                "todays_calls": 0,
                "total_prospects": 0,
                "completion_rate": 0
            })

        return stats

    except Exception as e:
        print(f"Erreur lors de la récupération des statistiques: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Erreur lors de la récupération des statistiques: {str(e)}"
        )
    
# Routes pour les agents
@router.post("/agents", response_model=Dict[str, Any])
async def create_agent(
    first_name: str = Form(...),
    last_name: str = Form(...),
    email: str = Form(...),
    phone: str = Form(...),
    address: str = Form(...),
    city: str = Form(...),
    postal_code: str = Form(...),
    photo: Optional[UploadFile] = File(None),
    current_user: dict = Depends(verify_admin),
    db: AsyncIOMotorDatabase = Depends(get_database)
):
    try:
        # Vérifier si l'email existe déjà
        existing_user = await db.users.find_one({"email": email})
        existing_company = await db.companies.find_one({"email": email})

        if existing_user or existing_company:
            raise HTTPException(
                status_code=409,
                detail="Cette adresse email est déjà utilisée par une autre entreprise ou un utilisateur"
            )

        # Générer username et password
        base_username = f"{first_name.lower()}.{last_name.lower()}".replace(" ", "")
        username = base_username
        counter = 1
        while await db.users.find_one({"username": username}):
            username = f"{base_username}{counter}"
            counter += 1

        password = generate_password()
        hashed_password = pwd_context.hash(password)

        # Gérer la photo
        photo_path = None
        if photo:
            filename = f"agent_{username}_{datetime.now().timestamp()}.{photo.filename.split('.')[-1]}"
            file_location = f"static/photos/{filename}"
            os.makedirs("static/photos", exist_ok=True)
            with open(file_location, "wb+") as file_object:
                file_object.write(await photo.read())
            photo_path = f"/static/photos/{filename}"

        # Récupérer le nom de la société
        company = await db.companies.find_one({"_id": ObjectId(current_user["company_id"])})
        company_name = company.get("name", "Votre entreprise") if company else "Votre entreprise"

        # Créer l'agent
        agent_data = {
            "first_name": first_name,
            "last_name": last_name,
            "email": email,
            "username": username,
            "phone": phone,
            "address": address,
            "city": city,
            "postal_code": postal_code,
            "photo": photo_path,
            "role": "agent",
            "is_active": True,
            "hashed_password": hashed_password,
            "created_at": datetime.utcnow(),
            "updated_at": datetime.utcnow(),
            "company_id": current_user["company_id"]
        }

        result = await db.users.insert_one(agent_data)
        agent_data["_id"] = result.inserted_id
        agent_data["password"] = password  # Pour l'envoi par email

        # Envoyer les identifiants par email
        async with httpx.AsyncClient() as client:
            email_data = {
                "email": email,
                "companyName": company_name,
                "password": password
            }
            email_response = await client.post(
                "https://agenda-v2-backend.onrender.com/api/send-credentials",
                data=email_data
            )
            if email_response.status_code != 200:
                print(f"Erreur lors de l'envoi de l'email: {email_response.text}")

        return format_user_response(agent_data, include_password=True)

    except Exception as e:
        print(f"Erreur lors de la création de l'agent: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/agents/{agent_id}/reset-password", response_model=Dict[str, Any])
async def reset_agent_password(
    agent_id: str,
    current_user: dict = Depends(verify_admin),
    db: AsyncIOMotorDatabase = Depends(get_database)
):
    try:
        agent_oid = ObjectId(agent_id)
        
        # Vérifier si l'agent existe
        agent = await db.users.find_one({
            "_id": agent_oid,
            "company_id": current_user["company_id"],
            "role": "agent"
        })
        
        if not agent:
            raise HTTPException(status_code=404, detail="Agent non trouvé")

        # Récupérer le nom de la société
        company = await db.companies.find_one({"_id": ObjectId(current_user["company_id"])})
        company_name = company.get("name", "Votre entreprise") if company else "Votre entreprise"

        # Générer un nouveau mot de passe
        new_password = generate_password()
        hashed_password = pwd_context.hash(new_password)

        # Mettre à jour le mot de passe
        result = await db.users.update_one(
            {"_id": agent_oid, "company_id": current_user["company_id"]},
            {"$set": {
                "hashed_password": hashed_password,
                "updated_at": datetime.utcnow()
            }}
        )

        if result.modified_count == 0:
            raise HTTPException(status_code=500, detail="Erreur lors de la réinitialisation du mot de passe")

        # Envoyer le nouveau mot de passe par email
        async with httpx.AsyncClient() as client:
            email_data = {
                "email": agent["email"],
                "companyName": company_name,
                "password": new_password
            }
            email_response = await client.post(
                "https://agenda-v2-backend.onrender.com/api/send-credentials",
                data=email_data
            )
            if email_response.status_code != 200:
                print(f"Erreur lors de l'envoi de l'email: {email_response.text}")

        return {"password": new_password}

    except Exception as e:
        print(f"Erreur lors de la réinitialisation du mot de passe: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))    