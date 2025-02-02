from fastapi import APIRouter, Depends, HTTPException, status
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

# Helper function to get the current user
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
        raise credentials_exception
        
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
        sender_email = "contact@tag-appore.com"
        smtp_password = ",4)%vdrnYDPq"
        
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
        with smtplib.SMTP_SSL('vautour.o2switch.net', 465) as server:
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
    user = await auth_service.authenticate_user(form_data.username, form_data.password)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Email ou mot de passe incorrect",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    access_token_expires = timedelta(minutes=settings.access_token_expire_minutes)
    access_token = auth_service.create_access_token(
        data={"sub": user["email"]}, expires_delta=access_token_expires
    )
    
    # Créer un dictionnaire de base avec les champs communs
    user_response = {
        "email": user["email"],
        "role": user["role"],
        "id": str(user["id"])
    }

    # Ajouter les champs optionnels s'ils existent
    if "username" in user:
        user_response["username"] = user["username"]
    if "name" in user:
        user_response["name"] = user["name"]
    if "company_id" in user:
        user_response["company_id"] = user["company_id"]
    
    return {
        "access_token": access_token,
        "token_type": "bearer",
        "user": user_response
    }

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
        company = await auth_service.get_company_by_email(email)
        if company is None:
            raise credentials_exception
        # S'assurer que tous les champs nécessaires sont présents
        user = {
            "id": str(company["_id"]),
            "email": company["email"],
            "role": "admin",
            "name": company["name"],
            "company_id": str(company["_id"]),  # Ajout du company_id
            "username": company["email"]  # Utiliser l'email comme username par défaut
        }
        
    return user


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
    current_time = datetime.datetime.now()
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