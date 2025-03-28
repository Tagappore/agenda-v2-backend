from fastapi import APIRouter, Depends, HTTPException, status, File, Form, UploadFile
from typing import List, Optional, Dict, Any
from motor.motor_asyncio import AsyncIOMotorDatabase
from ..services.auth import AuthService
from ..models.user import UserCreate, User, UserUpdate, UserRole, AgentCreate, AgentUpdate
from .auth import verify_admin, get_auth_service
from app.config.database import get_database
from bson import ObjectId
import os
import httpx
from datetime import datetime
from passlib.context import CryptContext
import secrets
import string

router = APIRouter(tags=["agent"])
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

def generate_password(length=12):
   alphabet = string.ascii_letters + string.digits + "!@#$%^&*"
   return ''.join(secrets.choice(alphabet) for _ in range(length))

def format_agent_response(agent: Dict[str, Any], include_password: bool = False) -> Dict[str, Any]:
   """Formate la réponse de l'agent de manière cohérente"""
   formatted_agent = {
       "id": str(agent.get("_id", "")),
       "first_name": agent.get("first_name", ""),
       "last_name": agent.get("last_name", ""),
       "email": agent.get("email", ""),
       "username": agent.get("username", ""),
       "phone": agent.get("phone", ""),
       "address": agent.get("address", ""),
       "city": agent.get("city", ""),
       "postal_code": agent.get("postal_code", ""),
       "photo": agent.get("photo"),
       "role": agent.get("role", "agent"),
       "is_active": agent.get("is_active", True),
       "company_id": agent.get("company_id", ""),
       "created_at": agent.get("created_at", datetime.utcnow()),
       "updated_at": agent.get("updated_at", datetime.utcnow())
   }
   
   if include_password and "hashed_password" in agent:
            formatted_agent["password"] = agent["hashed_password"]
       
   return formatted_agent

@router.get("/agents", response_model=List[Dict[str, Any]])
async def get_agents(
   current_user: dict = Depends(verify_admin),
   db: AsyncIOMotorDatabase = Depends(get_database)
):
   try:
       agents = await db.users.find(
           {"role": "agent", "company_id": current_user["company_id"]}
       ).to_list(1000)
       
       return [format_agent_response(agent) for agent in agents]
       
   except Exception as e:
       print(f"Erreur lors de la récupération des agents: {str(e)}")
       raise HTTPException(status_code=500, detail=str(e))

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
       agent_data["password"] = password

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
       
       return format_agent_response(agent_data, include_password=True)

   except Exception as e:
       print(f"Erreur lors de la création de l'agent: {str(e)}")
       raise HTTPException(status_code=500, detail=str(e))

@router.get("/agents/{agent_id}", response_model=Dict[str, Any])
async def get_agent(
   agent_id: str,
   current_user: dict = Depends(verify_admin),
   db: AsyncIOMotorDatabase = Depends(get_database)
):
   try:
       agent = await db.users.find_one({
           "_id": ObjectId(agent_id),
           "company_id": current_user["company_id"],
           "role": "agent"
       })
       
       if not agent:
           raise HTTPException(status_code=404, detail="Agent non trouvé")
           
       return format_agent_response(agent, include_password=True)
   
   
   
       
   except Exception as e:
       print(f"Erreur lors de la récupération de l'agent: {str(e)}")
       raise HTTPException(status_code=500, detail=str(e))
   
   


@router.put("/agents/{agent_id}", response_model=Dict[str, Any])
async def update_agent(
   agent_id: str,
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
       agent_oid = ObjectId(agent_id)
       
       # Vérifier si l'agent existe
       existing_agent = await db.users.find_one({
           "_id": agent_oid,
           "company_id": current_user["company_id"],
           "role": "agent"
       })
       
       if not existing_agent:
           raise HTTPException(status_code=404, detail="Agent non trouvé")

       # Vérifier l'email unique

       if email != existing_agent["email"]:
            existing_email_user = await db.users.find_one({
                "email": email,
                "_id": {"$ne": agent_oid}
            })
            existing_email_company = await db.companies.find_one({"email": email})
            
            if existing_email_user or existing_email_company:
                raise HTTPException(
                    status_code=409,
                    detail="Cette adresse email est déjà utilisée par une autre entreprise ou un utilisateur (agent, technicien, admin ou call center). Veuillez en choisir une autre."
                )

       # Gérer la photo
       photo_path = existing_agent.get("photo")
       if photo:
           if photo_path and os.path.exists(photo_path.replace("/static/", "static/")):
               os.remove(photo_path.replace("/static/", "static/"))

           filename = f"agent_{existing_agent['username']}_{datetime.now().timestamp()}.{photo.filename.split('.')[-1]}"
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
           "photo": photo_path,
           "updated_at": datetime.utcnow()
       }

       result = await db.users.update_one(
           {"_id": agent_oid, "company_id": current_user["company_id"]},
           {"$set": update_data}
       )

       if result.modified_count == 0:
           raise HTTPException(status_code=500, detail="Erreur lors de la mise à jour")
           
       # Récupérer l'agent mis à jour
       updated_agent = await db.users.find_one({"_id": agent_oid})
       return format_agent_response(updated_agent)

   except Exception as e:
       print(f"Erreur lors de la modification de l'agent: {str(e)}")
       raise HTTPException(status_code=500, detail=str(e))

@router.delete("/agents/{agent_id}")
async def delete_agent(
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

       # Supprimer la photo
       if agent.get("photo"):
           photo_path = agent["photo"].replace("/static/", "static/")
           if os.path.exists(photo_path):
               os.remove(photo_path)

       result = await db.users.delete_one({
           "_id": agent_oid,
           "company_id": current_user["company_id"]
       })
       
       if result.deleted_count == 0:
           raise HTTPException(status_code=500, detail="Erreur lors de la suppression")
           
       return {"message": "Agent supprimé avec succès"}

   except Exception as e:
       print(f"Erreur lors de la suppression de l'agent: {str(e)}")
       raise HTTPException(status_code=500, detail=str(e))

@router.post("/agents/{agent_id}/toggle-status")
async def toggle_agent_status(
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

       new_status = not agent["is_active"]
       result = await db.users.update_one(
           {"_id": agent_oid, "company_id": current_user["company_id"]},
           {"$set": {
               "is_active": new_status,
               "updated_at": datetime.utcnow()
           }}
       )

       if result.modified_count == 0:
           raise HTTPException(status_code=500, detail="Erreur lors de la mise à jour du statut")

       # Récupérer l'agent mis à jour
       updated_agent = await db.users.find_one({"_id": agent_oid})
       return format_agent_response(updated_agent)

   except Exception as e:
       print(f"Erreur lors de la modification du statut: {str(e)}")
       raise HTTPException(status_code=500, detail=str(e))

@router.get("/dashboard/stats")
async def get_dashboard_stats(
   current_user: dict = Depends(verify_admin),
   auth_service: AuthService = Depends(get_auth_service)
):
   try:
       stats = {
           "total_technician": await auth_service.count_users_by_role("technician"),
           "active_technician": await auth_service.count_active_users_by_role("technician"),
           "total_agents": await auth_service.count_users_by_role("agent"),
           "active_agents": await auth_service.count_active_users_by_role("agent")
       }
       return stats
   except Exception as e:
       print(f"Erreur lors de la récupération des statistiques: {str(e)}")
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