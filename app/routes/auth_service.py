from passlib.context import CryptContext
from jose import jwt
from datetime import datetime, timedelta, timezone
from bson import ObjectId
import secrets
import string

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

class AuthService:
    def __init__(self, db):
        self.db = db
        self.pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

    def verify_password(self, plain_password, hashed_password):
        return self.pwd_context.verify(plain_password, hashed_password)

    def get_password_hash(self, password):
        return self.pwd_context.hash(password)

    async def get_user_by_email(self, email: str):
        user = await self.db.users.find_one({"email": email})
        if user:
            user["id"] = str(user.pop("_id"))
            return user
        return None

    async def get_company_by_email(self, email: str):
        return await self.db.companies.find_one({"email": email})

    async def authenticate_user(self, email: str, password: str):
        user = await self.db.users.find_one({"email": email})
        if not user:
            # Vérifier si c'est une entreprise
            company = await self.db.companies.find_one({"email": email})
            if not company or not self.verify_password(password, company["password"]):
                return False
            # Créer un objet utilisateur à partir de l'entreprise
            user = {
                "_id": company["_id"],
                "email": company["email"],
                "role": "admin",
                "name": company["name"],
                "company_id": company["_id"]  # L'entreprise est sa propre company_id
            }
        else:
            if not self.verify_password(password, user["password"]):
                return False
        
        return user

    def create_access_token(self, data: dict, expires_delta: timedelta = None):
        """
        Optimisé: Les informations utilisateur sont déjà incluses dans data
        """
        to_encode = data.copy()
        if expires_delta:
            expire = datetime.now(timezone.utc) + expires_delta
        else:
            expire = datetime.now(timezone.utc) + timedelta(minutes=15)
        
        # Ajout seulement de l'expiration, les autres données sont déjà incluses
        to_encode.update({"exp": expire.timestamp()})
        
        encoded_jwt = jwt.encode(to_encode, settings.jwt_secret, algorithm=settings.jwt_algorithm)
        return encoded_jwt

    async def create_super_admin(self, user_data):
        # Vérifier si l'utilisateur existe déjà
        existing_user = await self.db.users.find_one({"email": user_data.email})
        if existing_user:
            raise ValueError("Un utilisateur avec cet email existe déjà")

        # Hash du mot de passe
        hashed_password = self.get_password_hash(user_data.password)
        
        # Création du super admin
        user_dict = {
            "email": user_data.email,
            "password": hashed_password,
            "role": "super_admin",
            "is_active": True,
            "created_at": datetime.utcnow(),
            "updated_at": datetime.utcnow()
        }
        
        result = await self.db.users.insert_one(user_dict)
        user_dict["_id"] = result.inserted_id
        
        # Convertir l'ID en chaîne pour le retour
        user_dict["id"] = str(user_dict.pop("_id"))
        
        return user_dict

    async def reset_password(self, email: str):
        """
        Réinitialise le mot de passe d'un utilisateur et retourne le nouveau mot de passe
        """
        # Générer un nouveau mot de passe aléatoire
        alphabet = string.ascii_letters + string.digits
        new_password = ''.join(secrets.choice(alphabet) for i in range(12))
        
        # Hacher le nouveau mot de passe
        hashed_password = self.get_password_hash(new_password)
        
        # Mettre à jour l'utilisateur ou l'entreprise
        user_result = await self.db.users.update_one(
            {"email": email},
            {"$set": {"password": hashed_password, "updated_at": datetime.utcnow()}}
        )
        
        if user_result.modified_count == 0:
            # Si aucun utilisateur n'a été modifié, essayer avec les entreprises
            company_result = await self.db.companies.update_one(
                {"email": email},
                {"$set": {"password": hashed_password, "updated_at": datetime.utcnow()}}
            )
            
            if company_result.modified_count == 0:
                raise ValueError("Aucun utilisateur ou entreprise trouvé avec cet email")
        
        return new_password

# Ajout de l'import settings qui était manquant
from ..config import settings