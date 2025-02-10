from fastapi import APIRouter, HTTPException, UploadFile, File, Form, Depends
from typing import Optional
from passlib.context import CryptContext
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import os
from datetime import datetime
from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorDatabase
from app.config.database import get_database
from ..services.auth import AuthService
from bson import ObjectId

router = APIRouter()

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

async def get_auth_service():
    db = get_database()
    return AuthService(db)

@router.get("/")
async def get_companies(db: AsyncIOMotorDatabase = Depends(get_database)):
    try:
        companies = await db.companies.find().to_list(1000)
        for company in companies:
            company["id"] = str(company.pop("_id"))
        return companies
    except Exception as e:
        print(f"Erreur lors de la récupération des entreprises: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/")
async def create_company(
    name: str = Form(...),
    siret: str = Form(...),
    email: str = Form(...),
    password: str = Form(...),
    logo: Optional[UploadFile] = File(None),
    phone: Optional[str] = Form(None),
    address: Optional[str] = Form(None),
    postal_code: Optional[str] = Form(None),
    city: Optional[str] = Form(None),
    db: AsyncIOMotorDatabase = Depends(get_database)
):
    try:
        print(f"Tentative de création d'entreprise avec: {name}, {siret}, {email}")
        
        # Vérifier si une entreprise avec ce SIRET existe déjà
        existing_company = await db.companies.find_one({"siret": siret})
        if existing_company:
            raise HTTPException(
                status_code=409,
                detail="Cet identifiant SIRET est déjà utilisé par une autre entreprise"
            )

        # Vérifier si l'email est déjà utilisé
        existing_email_company = await db.companies.find_one({"email": email})
        existing_email_user = await db.users.find_one({"email": email})

        if existing_email_company or existing_email_user:
            raise HTTPException(
                status_code=409,
                detail="Cette adresse email est déjà utilisée par une autre entreprise ou un utilisateur (agent, technicien, admin ou call center). Veuillez en choisir une autre."
            )

        # Gérer l'upload du logo
        logo_path = None
        if logo:
            try:
                filename = f"{siret}_{logo.filename}".replace(" ", "_")
                file_location = f"static/logos/{filename}"
                os.makedirs("static/logos", exist_ok=True)
                with open(file_location, "wb+") as file_object:
                    content = await logo.read()
                    file_object.write(content)
                logo_path = f"/static/logos/{filename}"
                print(f"Logo sauvegardé: {logo_path}")
            except Exception as e:
                print(f"Erreur lors de la sauvegarde du logo: {str(e)}")
                raise HTTPException(
                    status_code=500,
                    detail=f"Erreur lors de la sauvegarde du logo: {str(e)}"
                )

        # Créer le document entreprise
        company_data = {
            "name": name,
            "siret": siret,
            "email": email,
            "password": password,
            "phone": phone,
            "address": address,
            "postal_code": postal_code,
            "city": city,
            "logo_url": logo_path,
            "is_active": True,
            "role": "admin",
            "created_at": datetime.utcnow()
        }

        print("Données de l'entreprise préparées:", company_data)
        
        try:
            result = await db.companies.insert_one(company_data)
            print(f"Entreprise créée avec ID: {result.inserted_id}")
        except Exception as e:
            print(f"Erreur lors de l'insertion dans MongoDB: {str(e)}")
            raise HTTPException(
                status_code=500,
                detail=f"Erreur lors de l'insertion dans MongoDB: {str(e)}"
            )

        # Envoyer l'email
        try:
            await send_credentials({
                "email": email,
                "companyName": name,
                "password": password
            })
            print(f"Email envoyé à {email}")
        except Exception as e:
            print(f"Erreur lors de l'envoi de l'email: {str(e)}")

        company_data['_id'] = str(result.inserted_id)
        return company_data

    except HTTPException as e:
        raise e
    except Exception as e:
        print(f"Erreur inattendue lors de la création de l'entreprise: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail=str(e)
        )

@router.post("/send-credentials")
async def send_credentials(data: dict):
    try:
        sender_email = "support@app.tag-appore.com"
        smtp_password = "FyrJXhtT21A}"
        
        msg = MIMEMultipart()
        msg['From'] = sender_email
        msg['To'] = data['email']
        msg['Subject'] = f"Vos identifiants pour {data['companyName']}"
        
        body = f"""
        Bienvenue chez Tag Appore Dashboard !
        
        Voici vos identifiants de connexion :
        Email : {data['email']}
        Mot de passe : {data['password']}
        
        Equipe Tag Appore.
        """
        
        msg.attach(MIMEText(body, 'plain'))
        
        with smtplib.SMTP_SSL('app.tag-appore.com', 465) as server:
            server.login(sender_email, smtp_password)
            server.send_message(msg)
            
        return {"message": "Credentials sent successfully"}
    except Exception as e:
        print(f"Erreur lors de l'envoi de l'email: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/{company_id}/toggle-lock")
async def toggle_company_lock(
    company_id: str,
    db: AsyncIOMotorDatabase = Depends(get_database),
    auth_service: AuthService = Depends(get_auth_service)
):
    try:
        print(f"Tentative de verrouillage pour l'entreprise: {company_id}")
        company_oid = ObjectId(company_id)
        
        company = await db.companies.find_one({"_id": company_oid})
        if not company:
            raise HTTPException(status_code=404, detail="Entreprise non trouvée")

        new_status = not company["is_active"]
        print(f"Changement de statut: {company['is_active']} -> {new_status}")
        
        result = await db.companies.update_one(
            {"_id": company_oid},
            {"$set": {
                "is_active": new_status,
                "updated_at": datetime.utcnow()
            }}
        )
        print(f"Résultat de la mise à jour: {result.modified_count} document(s)")

        if not new_status:
            users_result = await db.users.update_many(
                {"company_id": company_oid},
                {"$set": {
                    "is_active": False,
                    "updated_at": datetime.utcnow()
                }}
            )
            print(f"Utilisateurs désactivés: {users_result.modified_count}")
            
            await auth_service.invalidate_company_tokens(company_id)

        return {
            "status": "success",
            "message": "Statut de l'entreprise mis à jour avec succès",
            "is_active": new_status
        }
        
    except Exception as e:
        print(f"Erreur lors du verrouillage: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail=f"Erreur lors de la mise à jour du statut: {str(e)}"
        )

@router.put("/{company_id}")
async def update_company(
    company_id: str,
    name: str = Form(...),
    siret: str = Form(...),
    email: str = Form(...),
    phone: Optional[str] = Form(None),
    address: Optional[str] = Form(None),
    postal_code: Optional[str] = Form(None),
    city: Optional[str] = Form(None),
    website: Optional[str] = Form(None),
    is_active: bool = Form(...),
    password: Optional[str] = Form(None),
    logo: Optional[UploadFile] = File(None),
    db: AsyncIOMotorDatabase = Depends(get_database)
):
    try:
        company_oid = ObjectId(company_id)
        
        existing_company = await db.companies.find_one({"_id": company_oid})
        if not existing_company:
            raise HTTPException(status_code=404, detail="Entreprise non trouvée")

        # Vérifier si le SIRET est déjà utilisé (si changé)
        if siret != existing_company["siret"]:
            existing_siret = await db.companies.find_one({
                "siret": siret,
                "_id": {"$ne": company_oid}
            })
            if existing_siret:
                raise HTTPException(
                    status_code=409,
                    detail="Cet identifiant SIRET est déjà utilisé par une autre entreprise"
                )

        # Vérifier si l'email est déjà utilisé (si changé)
        if email != existing_company["email"]:
            existing_email_company = await db.companies.find_one({
                "email": email,
                "_id": {"$ne": company_oid}
            })
            existing_email_user = await db.users.find_one({"email": email})
            
            if existing_email_company or existing_email_user:
                raise HTTPException(
                    status_code=409,
                    detail="Cette adresse email est déjà utilisée par une autre entreprise ou un utilisateur (agent, technicien, admin ou call center). Veuillez en choisir une autre."
                )

        # Gérer l'upload du nouveau logo si fourni
        logo_path = existing_company.get("logo_url")
        if logo:
            filename = f"{siret}_{logo.filename}".replace(" ", "_")
            file_location = f"static/logos/{filename}"
            with open(file_location, "wb+") as file_object:
                file_object.write(await logo.read())
            logo_path = f"/static/logos/{filename}"

        # Préparer les données de mise à jour
        update_data = {
            "name": name,
            "siret": siret,
            "email": email,
            "phone": phone,
            "address": address,
            "postal_code": postal_code,
            "city": city,
            "website": website,
            "is_active": is_active,
            "logo_url": logo_path,
            "updated_at": datetime.utcnow()
        }

        # Ajouter le mot de passe si fourni
        if password:
            update_data["password"] = password
            try:
                await send_credentials({
                    "email": email,
                    "companyName": name,
                    "password": password
                })
            except Exception as e:
                print(f"Erreur lors de l'envoi de l'email: {str(e)}")

        result = await db.companies.update_one(
            {"_id": company_oid},
            {"$set": update_data}
        )

        if result.modified_count == 0:
            raise HTTPException(status_code=404, detail="Aucune modification effectuée")

        update_data["id"] = company_id
        return update_data

    except Exception as e:
        print(f"Erreur lors de la mise à jour de l'entreprise: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@router.delete("/{company_id}")
async def delete_company(
    company_id: str,
    db: AsyncIOMotorDatabase = Depends(get_database)
):
    try:
        company_oid = ObjectId(company_id)
        
        company = await db.companies.find_one({"_id": company_oid})
        if not company:
            raise HTTPException(
                status_code=404,
                detail="Entreprise non trouvée"
            )

        if company.get("logo_url"):
            logo_path = company["logo_url"].replace("/static/", "static/")
            if os.path.exists(logo_path):
                os.remove(logo_path)

        await db.users.delete_many({"company_id": company_oid})
        result = await db.companies.delete_one({"_id": company_oid})

        if result.deleted_count:
            return {
                "status": "success",
                "message": "Entreprise et ses données associées supprimées avec succès"
            }
        else:
            raise HTTPException(
                status_code=500,
                detail="Erreur lors de la suppression de l'entreprise"
            )

    except Exception as e:
        print(f"Erreur lors de la suppression de l'entreprise: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail=f"Erreur lors de la suppression: {str(e)}"
        )