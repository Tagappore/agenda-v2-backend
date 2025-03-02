# Correction pour auth.py - Supprimer la fonction get_current_user doublée
# et ajouter une gestion optimisée des délais

from fastapi import APIRouter, Depends, HTTPException, status, BackgroundTasks
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from jose import JWTError, jwt
from fastapi import Form
from motor.motor_asyncio import AsyncIOMotorClient
from ..services.auth import AuthService
from ..models.user import UserCreate, User
from ..config import settings
from datetime import datetime, timedelta, timezone
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import smtplib
import asyncio

router = APIRouter(tags=["auth"])
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="token")

# Dependency to get the database instance
async def get_db():
    client = AsyncIOMotorClient(settings.mongodb_url)
    db = client[settings.database_name]
    try:
        yield db
    finally:
        client.close()

# Dependency to get the auth service
async def get_auth_service(db: AsyncIOMotorClient = Depends(get_db)):
    return AuthService(db)

# Helper function to get the current user - VERSION UNIFIÉE
async def get_current_user(
    token: str = Depends(oauth2_scheme),
    auth_service: AuthService = Depends(get_auth_service)
):
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    
    try:
        payload = jwt.decode(
            token, settings.jwt_secret, algorithms=[settings.jwt_algorithm]
        )
        email: str = payload.get("sub")
        if email is None:
            raise credentials_exception
    except JWTError:
        raise credentials_exception
        
    user = await auth_service.get_user_by_email(email)
    if user is None:
        # Vérifier si c'est une entreprise
        company = await auth_service.get_company_by_email(email)
        if company is None:
            raise credentials_exception
        # S'assurer que tous les champs nécessaires sont présents
        user = {
            "id": str(company["_id"]),
            "email": company["email"],
            "role": "admin",
            "name": company["name"],
            "company_id": str(company["_id"]),
            "username": company["email"],
            "_id": company["_id"]  # Ajout pour assurer la compatibilité
        }
    
    # Vérifier si l'utilisateur ou l'entreprise est actif
    if not user.get("is_active", True):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Compte utilisateur désactivé",
            headers={"WWW-Authenticate": "Bearer"},
        )
        
    return user

@router.post("/auth/reset-password")
async def reset_password(
    email: str = Form(...),
    auth_service: AuthService = Depends(get_auth_service)
):
    try:
        # Réinitialiser le mot de passe
        new_password = await auth_service.reset_password(email)
        
        # Configuration email
        sender_email = "support@app.tag-appore.com"
        smtp_password = "FyrJXhtT21A}"
        
        # Créer le message
        msg = MIMEMultipart()
        msg['From'] = sender_email
        msg['To'] = email
        msg['Subject'] = "Réinitialisation de votre mot de passe Tag Appore"
        
        body = f"""
        Bonjour,
        
        Voici votre nouveau mot de passe pour votre compte Tag Appore : {new_password}
        
        Nous vous recommandons de le changer lors de votre prochaine connexion.
        
        Cordialement,
        L'équipe Tag Appore
        """
        
        msg.attach(MIMEText(body, 'plain'))
        
        # Envoyer l'email via O2switch
        with smtplib.SMTP_SSL('app.tag-appore.com', 465) as server:
            server.login(sender_email, smtp_password)
            server.send_message(msg)
            
        return {"message": "Un nouveau mot de passe a été envoyé à votre adresse email"}
        
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=str(e)
        )

# Tâche d'arrière-plan pour enregistrer les connexions
async def record_login(auth_service, user_id):
    try:
        await asyncio.sleep(1)  # Ne pas bloquer la réponse
        await auth_service.record_user_login(user_id)
    except Exception as e:
        print(f"Erreur lors de l'enregistrement de la connexion: {e}")

@router.post("/token")
async def login(
    background_tasks: BackgroundTasks,
    form_data: OAuth2PasswordRequestForm = Depends(),
    auth_service: AuthService = Depends(get_auth_service)
):
    # Authentification optimisée
    user = await auth_service.authenticate_user(form_data.username, form_data.password)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Email ou mot de passe incorrect",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    # Vérifier si l'utilisateur est actif
    if not user.get("is_active", True):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Compte utilisateur désactivé",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    access_token_expires = timedelta(minutes=settings.access_token_expire_minutes)
    access_token = auth_service.create_access_token(
        data={"sub": user["email"]}, expires_delta=access_token_expires
    )
    
    # Enregistrer la connexion en arrière-plan
    background_tasks.add_task(record_login, auth_service, str(user["_id"]))
    
    # Retourner toutes les données nécessaires en une seule fois
    user_response = {
        "id": str(user["_id"]),
        "email": user["email"],
        "role": user["role"],
        "username": user.get("username", ""),
        "name": user.get("name", ""),
        "company_id": str(user.get("company_id", "")) if user.get("company_id") else None,
        "is_active": user.get("is_active", True),
        "first_name": user.get("first_name", ""),
        "last_name": user.get("last_name", "")
    }
    
    return {
        "access_token": access_token,
        "token_type": "bearer",
        "user": user_response
    }

@router.post("/create-super-admin", response_model=User)
async def create_super_admin(
    user_data: UserCreate,
    auth_service: AuthService = Depends(get_auth_service)
):
    try:
        user = await auth_service.create_super_admin(user_data)
        return user
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )

@router.get("/me", response_model=User)
async def read_users_me(
    current_user: dict = Depends(get_current_user)
):
    # Convertir le document MongoDB en format compatible avec le modèle User
    current_time = datetime.now()
    user_dict = {
        "id": str(current_user["_id"]) if "_id" in current_user else str(current_user["id"]),
        "email": current_user["email"],
        "username": current_user.get("username", current_user["email"]),
        "role": current_user["role"],
        "is_active": current_user.get("is_active", True),
        "first_name": current_user.get("first_name"),
        "last_name": current_user.get("last_name"),
        "phone": current_user.get("phone"),
        "address": current_user.get("address"),
        "city": current_user.get("city"),
        "postal_code": current_user.get("postal_code"),
        "photo": current_user.get("photo"),
        "company_id": str(current_user["company_id"]) if "company_id" in current_user else None,
        "created_at": current_user.get("created_at", current_time),
        "updated_at": current_user.get("updated_at", current_time)
    }
    
    return user_dict

# Dependency to verify super admin role
async def verify_super_admin(
    current_user: dict = Depends(get_current_user)
):
    if current_user["role"] != "super_admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only super admins can access this resource"
        )
    return current_user

# Dependency to verify admin role
async def verify_admin(
    current_user: dict = Depends(get_current_user)
):
    if current_user["role"] not in ["super_admin", "admin"]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only admins can access this resource"
        )
    return current_user

# Dependency to verify agent role
async def verify_agent(
    current_user: dict = Depends(get_current_user)
):
    if current_user["role"] not in ["super_admin", "admin", "agent"]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only agents can access this resource"
        )
    return current_user