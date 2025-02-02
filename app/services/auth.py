from datetime import datetime, timedelta
from typing import Optional, Dict, Any
from jose import JWTError, jwt
from fastapi import HTTPException
from passlib.context import CryptContext
from ..models.user import UserInDB, UserCreate, UserRole, User
from ..config import settings
from motor.motor_asyncio import AsyncIOMotorClient
from bson import ObjectId


pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

class AuthService:
    def __init__(self, db: AsyncIOMotorClient):
        self.db = db

    def verify_password(self, plain_password: str, hashed_password: str) -> bool:
        return pwd_context.verify(plain_password, hashed_password)

    def get_password_hash(self, password: str) -> str:
        return pwd_context.hash(password)

    async def get_user_by_email(self, email: str) -> Optional[Dict[str, Any]]:
        user = await self.db.users.find_one({"email": email})
        if user:
            user["id"] = str(user["_id"])
            return user
        return None

    async def invalidate_company_tokens(self, company_id: str):  # Ajout du self
        """
        Invalide tous les tokens d'une entreprise en ajoutant un timestamp de révocation
        """
        try:
            company_oid = ObjectId(company_id)
            revocation_timestamp = datetime.utcnow()
            
            # Mettre à jour l'entreprise
            await self.db.companies.update_one(  # Utilisation de self.db
                {"_id": company_oid},
                {"$set": {
                    "token_invalidation_timestamp": revocation_timestamp,
                    "updated_at": datetime.utcnow()
                }}
            )

            # Créer une entrée dans la collection des tokens révoqués
            await self.db.revoked_tokens.insert_one({  # Utilisation de self.db
                "company_id": company_oid,
                "revocation_timestamp": revocation_timestamp,
                "created_at": datetime.utcnow()
            })

            return True
        
        except Exception as e:
            print(f"Erreur lors de l'invalidation des tokens: {str(e)}")
            return False

    async def authenticate_user(self, email: str, password: str):
        print(f"Tentative d'authentification pour: {email}")
        
        # Vérifier d'abord dans la collection users (pour super_admin)
        user = await self.db.users.find_one({"email": email})
        if user:
            if not self.verify_password(password, user["hashed_password"]):
                print("Mot de passe incorrect pour super_admin")
                return False
            return {
                "id": str(user["_id"]),
                "email": user["email"],
                "role": user["role"],
                "username": user.get("username", ""),  # Optionnel pour rétrocompatibilité
            }

        # Si non trouvé, vérifier dans la collection companies (pour admin)
        company = await self.db.companies.find_one({"email": email})
        if company:
            print(f"Company trouvée: {company}")
            # Pour les companies, le mot de passe est stocké directement
            if password != company["password"]:
                print("Mot de passe incorrect pour company")
                return False
            
            if not company.get("is_active", True):
                print("Entreprise inactive")
                return False

            return {
                "id": str(company["_id"]),
                "email": company["email"],
                "role": "admin",
                "username": company["name"],  # Utiliser le nom de l'entreprise comme username
                "company_id": str(company["_id"]),
                "name": company["name"]
            }

        print("Utilisateur non trouvé")
        return False


    async def count_users_by_role(self, role: str) -> int:
        return await self.db.users.count_documents({"role": role})

    async def count_active_users(self) -> int:
        return await self.db.users.count_documents({"is_active": True})

    async def count_companies(self) -> int:
        return await self.db.companies.count_documents({})
    
    

    async def get_company_by_email(self, email: str) -> Optional[Dict[str, Any]]:
        company = await self.db.companies.find_one({"email": email})
        if company:
            company["id"] = str(company["_id"])
            return company
        return None

    async def verify_token(self, token: str) -> dict:  # Ajout du self
        try:
            # Décodage du token
            payload = jwt.decode(
                token, 
                settings.jwt_secret,  # Utilisation de settings au lieu de SECRET_KEY
                algorithms=[settings.jwt_algorithm]  # Utilisation de settings au lieu de ALGORITHM
            )
            
            # Vérifier si l'entreprise a révoqué ses tokens
            company = await self.db.companies.find_one(  # Utilisation de self.db
                {"_id": ObjectId(payload.get("company_id"))}
            )
            
            if company and company.get("token_invalidation_timestamp"):
                token_iat = datetime.fromtimestamp(payload["iat"])
                if token_iat < company["token_invalidation_timestamp"]:
                    raise HTTPException(
                        status_code=401,
                        detail="Token révoqué"
                    )
            
            return payload
            
        except JWTError:
            raise HTTPException(
                status_code=401,
                detail="Token invalide"
            )

    def create_access_token(self, data: dict, expires_delta: Optional[timedelta] = None):
        to_encode = data.copy()
        if expires_delta:
            expire = datetime.utcnow() + expires_delta
        else:
            expire = datetime.utcnow() + timedelta(minutes=15)
        to_encode.update({"exp": expire})
        encoded_jwt = jwt.encode(
            to_encode, 
            settings.jwt_secret, 
            algorithm=settings.jwt_algorithm
        )
        return encoded_jwt

    async def create_super_admin(self, user_data: UserCreate):
        # Vérifier si un super admin existe déjà
        if await self.db.users.find_one({"role": UserRole.SUPER_ADMIN}):
            raise ValueError("Super admin already exists")
        
        user_dict = user_data.dict()
        user_dict["hashed_password"] = self.get_password_hash(user_dict.pop("password"))
        user_dict["role"] = UserRole.SUPER_ADMIN
        user_dict["created_at"] = datetime.utcnow()
        user_dict["updated_at"] = datetime.utcnow()
        
        result = await self.db.users.insert_one(user_dict)
        user_dict["id"] = str(result.inserted_id)
        
        return UserInDB(**user_dict)
    

    async def send_credentials(self, email: str, password: str):
        """
        Vérifie les credentials et retourne un token d'accès si valide
        """
        user = await self.authenticate_user(email, password)
        
        if not user:
            raise HTTPException(
                status_code=401,
                detail="Email ou mot de passe incorrect"
            )

        # Vérifier si l'utilisateur et sa société sont actifs
        if not user.get("is_active", False):
            raise HTTPException(
                status_code=401,
                detail="Compte utilisateur désactivé"
            )

        if "company_id" in user:
            company = await self.db.companies.find_one({"_id": user["company_id"]})
            if company and not company.get("is_active", False):
                raise HTTPException(
                    status_code=401,
                    detail="Compte entreprise désactivé"
                )

        # Créer les données pour le token
        token_data = {
            "sub": str(user["_id"]),
            "email": user["email"],
            "role": user["role"],
            "company_id": str(user.get("company_id", "")) if "company_id" in user else None,
            "iat": datetime.utcnow()
        }

        # Créer le token avec une expiration de 24h
        access_token = self.create_access_token(
            data=token_data,
            expires_delta=timedelta(hours=24)
        )

        return {
            "access_token": access_token,
            "token_type": "bearer",
            "user": {
                "id": str(user["_id"]),
                "email": user["email"],
                "role": user["role"],
                "company_id": str(user.get("company_id", "")) if "company_id" in user else None
            }
        }
    
    async def cascade_deactivate_admin(self, admin_id: str):
        """Désactive un admin et tous ses utilisateurs associés"""
        try:
            # 1. Récupérer l'admin et son entreprise
            admin = await self.db.users.find_one({"_id": ObjectId(admin_id)})
            if not admin or admin["role"] != "admin":
                raise HTTPException(status_code=404, detail="Admin non trouvé")
            
            company_id = admin.get("company_id")
            
            # 2. Désactiver l'entreprise
            await self.db.companies.update_one(
                {"_id": ObjectId(company_id)},
                {
                    "$set": {
                        "is_active": False,
                        "updated_at": datetime.utcnow(),
                        "token_invalidation_timestamp": datetime.utcnow()
                    }
                }
            )
            
            # 3. Désactiver tous les agents liés à cette entreprise
            await self.db.users.update_many(
                {"company_id": ObjectId(company_id)},
                {
                    "$set": {
                        "is_active": False,
                        "updated_at": datetime.utcnow()
                    }
                }
            )
            
            return True
        except Exception as e:
            print(f"Erreur lors de la désactivation en cascade: {str(e)}")
            return False