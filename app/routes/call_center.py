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

router = APIRouter(tags=["call_center"])
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

def generate_password(length=12):
    alphabet = string.ascii_letters + string.digits + "!@#$%^&*"
    return ''.join(secrets.choice(alphabet) for _ in range(length))

def format_call_center_response(call_center: Dict[str, Any], include_password: bool = False) -> Dict[str, Any]:
    """Formate la réponse du call center de manière cohérente"""
    formatted_call_center = {
        "id": str(call_center.get("_id", "")),
        "first_name": call_center.get("first_name", ""),
        "last_name": call_center.get("last_name", ""),
        "email": call_center.get("email", ""),
        "username": call_center.get("username", ""),
        "phone": call_center.get("phone", ""),
        "address": call_center.get("address", ""),
        "city": call_center.get("city", ""),
        "postal_code": call_center.get("postal_code", ""),
        "country": call_center.get("country", ""),  # Nouveau champ
        "siret": call_center.get("siret", ""),      # Nouveau champ
        "photo": call_center.get("photo"),
        "role": call_center.get("role", "call_center"),
        "is_active": call_center.get("is_active", True),
        "company_id": call_center.get("company_id", ""),
        "created_at": call_center.get("created_at", datetime.utcnow()),
        "updated_at": call_center.get("updated_at", datetime.utcnow())
    }
    
    if include_password and "hashed_password" in call_center:
        formatted_call_center["password"] = call_center["hashed_password"]
        
    return formatted_call_center

@router.get("/call-centers", response_model=List[Dict[str, Any]])
async def get_call_centers(
    current_user: dict = Depends(verify_admin),
    db: AsyncIOMotorDatabase = Depends(get_database)
):
    try:
        call_centers = await db.users.find(
            {"role": "call_center", "company_id": current_user["company_id"]}
        ).to_list(1000)
        
        return [format_call_center_response(call_center) for call_center in call_centers]
        
    except Exception as e:
        print(f"Erreur lors de la récupération des call centers: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/call-centers", response_model=Dict[str, Any])
async def create_call_center(
    first_name: str = Form(...),
    last_name: str = Form(...),
    email: str = Form(...),
    phone: str = Form(...),
    address: str = Form(...),
    city: str = Form(...),
    postal_code: str = Form(...),
    country: str = Form(...),    # Nouveau champ
    siret: str = Form(...),      # Nouveau champ
    photo: Optional[UploadFile] = File(None),
    current_user: dict = Depends(verify_admin),
    db: AsyncIOMotorDatabase = Depends(get_database)
):
    try:
        # Vérifier si l'email existe déjà
        if await db.users.find_one({"email": email}):
            raise HTTPException(status_code=409, detail="Email déjà utilisé")

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
            filename = f"call_center_{username}_{datetime.now().timestamp()}.{photo.filename.split('.')[-1]}"
            file_location = f"static/photos/{filename}"
            os.makedirs("static/photos", exist_ok=True)
            with open(file_location, "wb+") as file_object:
                file_object.write(await photo.read())
            photo_path = f"/static/photos/{filename}"

        # Récupérer le nom de la société
        company = await db.companies.find_one({"_id": ObjectId(current_user["company_id"])})
        company_name = company.get("name", "Votre entreprise") if company else "Votre entreprise"

        # Créer le call center
        call_center_data = {
            "first_name": first_name,
            "last_name": last_name,
            "email": email,
            "username": username,
            "phone": phone,
            "address": address,
            "city": city,
            "postal_code": postal_code,
            "country": country,        # Nouveau champ
            "siret": siret,           # Nouveau champ
            "photo": photo_path,
            "role": "call_center",
            "is_active": True,
            "hashed_password": hashed_password,
            "created_at": datetime.utcnow(),
            "updated_at": datetime.utcnow(),
            "company_id": current_user["company_id"]
        }

        result = await db.users.insert_one(call_center_data)
        call_center_data["_id"] = result.inserted_id
        call_center_data["password"] = password

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
        
        return format_call_center_response(call_center_data, include_password=True)

    except Exception as e:
        print(f"Erreur lors de la création du call center: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/call-centers/{call_center_id}", response_model=Dict[str, Any])
async def get_call_center(
    call_center_id: str,
    current_user: dict = Depends(verify_admin),
    db: AsyncIOMotorDatabase = Depends(get_database)
):
    try:
        call_center = await db.users.find_one({
            "_id": ObjectId(call_center_id),
            "company_id": current_user["company_id"],
            "role": "call_center"
        })
        
        if not call_center:
            raise HTTPException(status_code=404, detail="Call center non trouvé")
            
        return format_call_center_response(call_center, include_password=True)
        
    except Exception as e:
        print(f"Erreur lors de la récupération du call center: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@router.put("/call-centers/{call_center_id}", response_model=Dict[str, Any])
async def update_call_center(
    call_center_id: str,
    first_name: str = Form(...),
    last_name: str = Form(...),
    email: str = Form(...),
    phone: str = Form(...),
    address: str = Form(...),
    city: str = Form(...),
    postal_code: str = Form(...),
    country: str = Form(...),    # Nouveau champ
    siret: str = Form(...),      # Nouveau champ
    photo: Optional[UploadFile] = File(None),
    current_user: dict = Depends(verify_admin),
    db: AsyncIOMotorDatabase = Depends(get_database)
):
    try:
        call_center_oid = ObjectId(call_center_id)
        
        # Vérifier si le call center existe
        existing_call_center = await db.users.find_one({
            "_id": call_center_oid,
            "company_id": current_user["company_id"],
            "role": "call_center"
        })
        
        if not existing_call_center:
            raise HTTPException(status_code=404, detail="Call center non trouvé")

        # Vérifier l'email unique
        if email != existing_call_center["email"]:
            email_exists = await db.users.find_one({
                "email": email,
                "_id": {"$ne": call_center_oid}
            })
            if email_exists:
                raise HTTPException(status_code=409, detail="Email déjà utilisé")

        # Gérer la photo
        photo_path = existing_call_center.get("photo")
        if photo:
            if photo_path and os.path.exists(photo_path.replace("/static/", "static/")):
                os.remove(photo_path.replace("/static/", "static/"))

            filename = f"call_center_{existing_call_center['username']}_{datetime.now().timestamp()}.{photo.filename.split('.')[-1]}"
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
            "country": country,    # Nouveau champ
            "siret": siret,       # Nouveau champ
            "photo": photo_path,
            "updated_at": datetime.utcnow()
        }

        result = await db.users.update_one(
            {"_id": call_center_oid, "company_id": current_user["company_id"]},
            {"$set": update_data}
        )

        if result.modified_count == 0:
            raise HTTPException(status_code=500, detail="Erreur lors de la mise à jour")
            
        # Récupérer le call center mis à jour
        updated_call_center = await db.users.find_one({"_id": call_center_oid})
        return format_call_center_response(updated_call_center)

    except Exception as e:
        print(f"Erreur lors de la modification du call center: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@router.delete("/call-centers/{call_center_id}")
async def delete_call_center(
    call_center_id: str,
    current_user: dict = Depends(verify_admin),
    db: AsyncIOMotorDatabase = Depends(get_database)
):
    try:
        call_center_oid = ObjectId(call_center_id)
        
        # Vérifier si le call center existe
        call_center = await db.users.find_one({
            "_id": call_center_oid,
            "company_id": current_user["company_id"],
            "role": "call_center"
        })
        
        if not call_center:
            raise HTTPException(status_code=404, detail="Call center non trouvé")

        # Supprimer la photo
        if call_center.get("photo"):
            photo_path = call_center["photo"].replace("/static/", "static/")
            if os.path.exists(photo_path):
                os.remove(photo_path)

        result = await db.users.delete_one({
            "_id": call_center_oid,
            "company_id": current_user["company_id"]
        })
        
        if result.deleted_count == 0:
            raise HTTPException(status_code=500, detail="Erreur lors de la suppression")
            
        return {"message": "Call center supprimé avec succès"}

    except Exception as e:
        print(f"Erreur lors de la suppression du call center: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/call-centers/{call_center_id}/toggle-status")
async def toggle_call_center_status(
    call_center_id: str,
    current_user: dict = Depends(verify_admin),
    db: AsyncIOMotorDatabase = Depends(get_database)
):
    try:
        call_center_oid = ObjectId(call_center_id)
        
        # Vérifier si le call center existe
        call_center = await db.users.find_one({
            "_id": call_center_oid,
            "company_id": current_user["company_id"],
            "role": "call_center"
        })
        
        if not call_center:
            raise HTTPException(status_code=404, detail="Call center non trouvé")

        new_status = not call_center["is_active"]
        result = await db.users.update_one(
            {"_id": call_center_oid, "company_id": current_user["company_id"]},
            {"$set": {
                "is_active": new_status,
                "updated_at": datetime.utcnow()
            }}
        )

        if result.modified_count == 0:
            raise HTTPException(status_code=500, detail="Erreur lors de la mise à jour du statut")

        # Récupérer le call center mis à jour
        updated_call_center = await db.users.find_one({"_id": call_center_oid})
        return format_call_center_response(updated_call_center)

    except Exception as e:
        print(f"Erreur lors de la modification du statut: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/call-centers/{call_center_id}/reset-password", response_model=Dict[str, Any])
async def reset_call_center_password(
    call_center_id: str,
    current_user: dict = Depends(verify_admin),
    db: AsyncIOMotorDatabase = Depends(get_database)
):
    try:
        call_center_oid = ObjectId(call_center_id)
        
        # Vérifier si le call center existe
        call_center = await db.users.find_one({
            "_id": call_center_oid,
            "company_id": current_user["company_id"],
            "role": "call_center"
        })
        
        if not call_center:
            raise HTTPException(status_code=404, detail="Call center non trouvé")

        # Récupérer le nom de la société
        company = await db.companies.find_one({"_id": ObjectId(current_user["company_id"])})
        company_name = company.get("name", "Votre entreprise") if company else "Votre entreprise"

        # Générer un nouveau mot de passe
        new_password = generate_password()
        hashed_password = pwd_context.hash(new_password)

        # Mettre à jour le mot de passe
        result = await db.users.update_one(
            {"_id": call_center_oid, "company_id": current_user["company_id"]},
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
                "email": call_center["email"],
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