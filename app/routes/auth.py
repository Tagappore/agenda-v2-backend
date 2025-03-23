from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from jose import JWTError, jwt
from fastapi import Form
from ..services.auth import AuthService
from ..models.user import UserCreate, User
from ..config import settings
from ..config.database import get_database
from datetime import datetime, timedelta, timezone
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import smtplib

router = APIRouter(tags=["auth"])
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="token")

# Dependency to get the auth service
async def get_auth_service(db = Depends(get_database)):
    return AuthService(db)

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

@router.post("/token")
async def login(
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
    
    # Augmenter la durée de vie du token à 24 heures (1440 minutes)
    access_token_expires = timedelta(minutes=1440)
    
    # Préparer les données pour le token JWT, inclure les infos utilisateur essentielles
    token_data = {
        "sub": user["email"],
        "role": user["role"],
        "user_id": str(user["_id"]) if "_id" in user else str(user["id"]),
        "company_id": str(user["company_id"]) if "company_id" in user else None,
        "name": user.get("name", ""),
        "is_active": user.get("is_active", True)
    }
    
    access_token = auth_service.create_access_token(
        data=token_data, expires_delta=access_token_expires
    )
    
    # Retourner toutes les données nécessaires en une seule fois
    user_response = {
        "id": str(user["_id"]) if "_id" in user else str(user["id"]),
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

async def get_current_user(token: str = Depends(oauth2_scheme)):
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
            
        # Extraire les informations utilisateur directement du token
        # sans requête à la base de données
        current_time = datetime.now()
        user = {
            "id": payload.get("user_id"),
            "email": email,
            "role": payload.get("role"),
            "company_id": payload.get("company_id"),
            "name": payload.get("name", ""),
            "is_active": payload.get("is_active", True),
            "created_at": current_time,
            "updated_at": current_time
        }
        
        return user
        
    except JWTError:
        raise credentials_exception

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
    # Les données utilisateur sont déjà disponibles depuis le token JWT
    # Pas besoin de requête additionnelle à la base de données
    current_time = datetime.now()
    user_dict = {
        "id": current_user["id"],
        "email": current_user["email"],
        "username": current_user.get("username", current_user["email"]),
        "role": current_user["role"],
        "is_active": current_user.get("is_active", True),
        "first_name": current_user.get("first_name", ""),
        "last_name": current_user.get("last_name", ""),
        "phone": current_user.get("phone", ""),
        "address": current_user.get("address", ""),
        "city": current_user.get("city", ""),
        "postal_code": current_user.get("postal_code", ""),
        "photo": current_user.get("photo", ""),
        "company_id": current_user["company_id"],
        "created_at": current_user.get("created_at", current_time),
        "updated_at": current_user.get("updated_at", current_time)
    }
    
    return user_dict

# Dependency to verify super admin role - optimisée, sans requête BD
async def verify_super_admin(
    current_user: dict = Depends(get_current_user)
):
    if current_user["role"] != "super_admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only super admins can access this resource"
        )
    return current_user

# Dependency to verify admin role - optimisée, sans requête BD
async def verify_admin(
    current_user: dict = Depends(get_current_user)
):
    if current_user["role"] not in ["super_admin", "admin"]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only admins can access this resource"
        )
    return current_user

# Dependency to verify admin role - optimisée, sans requête BD
async def verify_admin_or_call_center(
    current_user: dict = Depends(get_current_user)
):
    if current_user["role"] not in ["super_admin", "admin", "call_center"]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only admins and call centers can access this resource"
        )
    return current_user

# Dependency to verify agent role - optimisée, sans requête BD
async def verify_agent(
    current_user: dict = Depends(get_current_user)
):
    if current_user["role"] not in ["super_admin", "admin", "agent"]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only agents can access this resource"
        )
    return current_user