from fastapi import APIRouter, Depends, HTTPException, status, File, Form, UploadFile
from typing import List, Optional, Dict, Any
from motor.motor_asyncio import AsyncIOMotorDatabase
from ..services.auth import AuthService
from ..models.user import UserCreate, User, UserUpdate, UserRole
from .auth import verify_admin, get_auth_service
from app.config.database import get_database
from bson import ObjectId
import os
import httpx
from datetime import datetime
from passlib.context import CryptContext
import secrets
import string

router = APIRouter(tags=["technician"])
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

def generate_password(length=12):
    alphabet = string.ascii_letters + string.digits + "!@#$%^&*"
    return ''.join(secrets.choice(alphabet) for _ in range(length))

def format_technician_response(technician: Dict[str, Any], include_password: bool = False) -> Dict[str, Any]:
    formatted_technician = {
        "id": str(technician.get("_id", "")),
        "first_name": technician.get("first_name", ""),
        "last_name": technician.get("last_name", ""),
        "email": technician.get("email", ""),
        "username": technician.get("username", ""),
        "phone": technician.get("phone", ""),
        "address": technician.get("address", ""),
        "city": technician.get("city", ""),
        "postal_code": technician.get("postal_code", ""),
        "departments": technician.get("departments", []),  # Nouveau champ
        "photo": technician.get("photo"),
        "role": technician.get("role", "technician"),
        "is_active": technician.get("is_active", True),
        "company_id": technician.get("company_id", ""),
        "created_at": technician.get("created_at", datetime.utcnow()),
        "updated_at": technician.get("updated_at", datetime.utcnow())
    }
    
    if include_password and "hashed_password" in technician:
        formatted_technician["password"] = technician["hashed_password"]
        
    return formatted_technician

@router.get("/technicians", response_model=List[Dict[str, Any]])
async def get_technicians(
    current_user: dict = Depends(verify_admin),
    db: AsyncIOMotorDatabase = Depends(get_database)
):
    try:
        technicians = await db.users.find(
            {"role": "technician", "company_id": current_user["company_id"]}
        ).to_list(1000)
        
        return [format_technician_response(technician) for technician in technicians]
        
    except Exception as e:
        print(f"Erreur lors de la récupération des techniciens: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/technicians", response_model=Dict[str, Any])
async def create_technician(
    first_name: str = Form(...),
    last_name: str = Form(...),
    email: str = Form(...),
    phone: str = Form(...),
    address: str = Form(...),
    city: str = Form(...),
    postal_code: str = Form(...),
    departments: str = Form(...),  # Nouveau champ
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
                detail="Cette adresse email est déjà utilisée par une autre entreprise ou un utilisateur (agent, technicien, admin ou call center). Veuillez en choisir une autre."
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
            filename = f"technician_{username}_{datetime.now().timestamp()}.{photo.filename.split('.')[-1]}"
            file_location = f"static/photos/{filename}"
            os.makedirs("static/photos", exist_ok=True)
            with open(file_location, "wb+") as file_object:
                file_object.write(await photo.read())
            photo_path = f"/static/photos/{filename}"

        # Récupérer le nom de la société
        company = await db.companies.find_one({"_id": ObjectId(current_user["company_id"])})
        company_name = company.get("name", "Votre entreprise") if company else "Votre entreprise"

        # Créer le technicien
        technician_data = {
            "first_name": first_name,
            "last_name": last_name,
            "email": email,
            "username": username,
            "phone": phone,
            "address": address,
            "city": city,
            "postal_code": postal_code,
            "photo": photo_path,
            "departments": departments.split(','),  # Conversion de la chaîne en liste
            "role": "technician",
            "is_active": True,
            "hashed_password": hashed_password,
            "created_at": datetime.utcnow(),
            "updated_at": datetime.utcnow(),
            "company_id": current_user["company_id"]
        }

        result = await db.users.insert_one(technician_data)
        technician_data["_id"] = result.inserted_id
        technician_data["password"] = password

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
        
        return format_technician_response(technician_data, include_password=True)

    except Exception as e:
        print(f"Erreur lors de la création du technicien: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/technicians/{technician_id}", response_model=Dict[str, Any])
async def get_technician(
    technician_id: str,
    current_user: dict = Depends(verify_admin),
    db: AsyncIOMotorDatabase = Depends(get_database)
):
    try:
        technician = await db.users.find_one({
            "_id": ObjectId(technician_id),
            "company_id": current_user["company_id"],
            "role": "technician"
        })
        
        if not technician:
            raise HTTPException(status_code=404, detail="Technicien non trouvé")
            
        return format_technician_response(technician, include_password=True)
        
    except Exception as e:
        print(f"Erreur lors de la récupération du technicien: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@router.put("/technicians/{technician_id}", response_model=Dict[str, Any])
async def update_technician(
    technician_id: str,
    first_name: str = Form(...),
    last_name: str = Form(...),
    email: str = Form(...),
    phone: str = Form(...),
    address: str = Form(...),
    city: str = Form(...),
    postal_code: str = Form(...),
    departments: str = Form(...),  # Nouveau champ
    photo: Optional[UploadFile] = File(None),
    current_user: dict = Depends(verify_admin),
    db: AsyncIOMotorDatabase = Depends(get_database)
):
    try:
        technician_oid = ObjectId(technician_id)
        
        # Vérifier si le technicien existe
        existing_technician = await db.users.find_one({
            "_id": technician_oid,
            "company_id": current_user["company_id"],
            "role": "technician"
        })
        
        if not existing_technician:
            raise HTTPException(status_code=404, detail="Technicien non trouvé")

        # Vérifier l'email unique
        if email != existing_technician["email"]:
            existing_email_user = await db.users.find_one({
                "email": email,
                "_id": {"$ne": technician_oid}
            })
            existing_email_company = await db.companies.find_one({"email": email})
            
            if existing_email_user or existing_email_company:
                raise HTTPException(
                    status_code=409,
                    detail="Cette adresse email est déjà utilisée par une autre entreprise ou un utilisateur (agent, technicien, admin ou call center). Veuillez en choisir une autre."
                )

        # Gérer la photo
        photo_path = existing_technician.get("photo")
        if photo:
            if photo_path and os.path.exists(photo_path.replace("/static/", "static/")):
                os.remove(photo_path.replace("/static/", "static/"))

            filename = f"technician_{existing_technician['username']}_{datetime.now().timestamp()}.{photo.filename.split('.')[-1]}"
            file_location = f"static/photos/{filename}"
            os.makedirs("static/photos", exist_ok=True)
            with open(file_location, "wb+") as file_object:
                content = await photo.read()
                file_object.write(content)
            photo_path = f"/static/photos/{filename}"

        # Mettre à jour les données
        update_data = {
            "first_name": first_name,
            "last_name": last_name,
            "email": email,
            "phone": phone,
            "address": address,
            "city": city,
            "postal_code": postal_code,
            "departments": departments.split(','), # Conversion de la chaîne en liste
            "photo": photo_path,
            "updated_at": datetime.utcnow()
        }

        result = await db.users.update_one(
            {"_id": technician_oid, "company_id": current_user["company_id"]},
            {"$set": update_data}
        )

        if result.modified_count == 0:
            raise HTTPException(status_code=500, detail="Erreur lors de la mise à jour")
            
        # Récupérer le technicien mis à jour
        updated_technician = await db.users.find_one({"_id": technician_oid})
        return format_technician_response(updated_technician)

    except Exception as e:
        print(f"Erreur lors de la modification du technicien: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@router.delete("/technicians/{technician_id}")
async def delete_technician(
    technician_id: str,
    current_user: dict = Depends(verify_admin),
    db: AsyncIOMotorDatabase = Depends(get_database)
):
    try:
        technician_oid = ObjectId(technician_id)
        
        # Vérifier si le technicien existe
        technician = await db.users.find_one({
            "_id": technician_oid,
            "company_id": current_user["company_id"],
            "role": "technician"
        })
        
        if not technician:
            raise HTTPException(status_code=404, detail="Technicien non trouvé")

        # Supprimer la photo
        if technician.get("photo"):
            photo_path = technician["photo"].replace("/static/", "static/")
            if os.path.exists(photo_path):
                os.remove(photo_path)

        result = await db.users.delete_one({
            "_id": technician_oid,
            "company_id": current_user["company_id"]
        })
        
        if result.deleted_count == 0:
            raise HTTPException(status_code=500, detail="Erreur lors de la suppression")
            
        return {"message": "Technicien supprimé avec succès"}

    except Exception as e:
        print(f"Erreur lors de la suppression du technicien: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/technicians/{technician_id}/toggle-status")
async def toggle_technician_status(
    technician_id: str,
    current_user: dict = Depends(verify_admin),
    db: AsyncIOMotorDatabase = Depends(get_database)
):
    try:
        technician_oid = ObjectId(technician_id)
        
        # Vérifier si le technicien existe
        technician = await db.users.find_one({
            "_id": technician_oid,
            "company_id": current_user["company_id"],
            "role": "technician"
        })
        
        if not technician:
            raise HTTPException(status_code=404, detail="Technicien non trouvé")

        new_status = not technician["is_active"]
        result = await db.users.update_one(
            {"_id": technician_oid, "company_id": current_user["company_id"]},
            {"$set": {
                "is_active": new_status,
                "updated_at": datetime.utcnow()
            }}
        )

        if result.modified_count == 0:
            raise HTTPException(status_code=500, detail="Erreur lors de la mise à jour du statut")

        # Récupérer le technicien mis à jour
        updated_technician = await db.users.find_one({"_id": technician_oid})
        return format_technician_response(updated_technician)

    except Exception as e:
        print(f"Erreur lors de la modification du statut: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/technicians/{technician_id}/reset-password", response_model=Dict[str, Any])
async def reset_technician_password(
    technician_id: str,
    current_user: dict = Depends(verify_admin),
    db: AsyncIOMotorDatabase = Depends(get_database)
):
    try:
        technician_oid = ObjectId(technician_id)
        
        # Vérifier si le technicien existe
        technician = await db.users.find_one({
            "_id": technician_oid,
            "company_id": current_user["company_id"],
            "role": "technician"
        })
        
        if not technician:
            raise HTTPException(status_code=404, detail="Technicien non trouvé")

        # Récupérer le nom de la société
        company = await db.companies.find_one({"_id": ObjectId(current_user["company_id"])})
        company_name = company.get("name", "Votre entreprise") if company else "Votre entreprise"

        # Générer un nouveau mot de passe
        new_password = generate_password()
        hashed_password = pwd_context.hash(new_password)

        # Mettre à jour le mot de passe
        result = await db.users.update_one(
            {"_id": technician_oid, "company_id": current_user["company_id"]},
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
                "email": technician["email"],
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