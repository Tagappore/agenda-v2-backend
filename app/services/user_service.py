from datetime import datetime
from typing import List, Optional
from bson import ObjectId

from motor.motor_asyncio import AsyncIOMotorClient
from ..models.user import UserCreate, UserUpdate, UserInDB, UserRole
from passlib.context import CryptContext

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

class UserService:
    def __init__(self, db: AsyncIOMotorClient):
        self.db = db
        self.collection = db.users

    def get_password_hash(self, password: str) -> str:
        return pwd_context.hash(password)

    async def create_user(self, creator_id: str, user_data: UserCreate) -> UserInDB:
        # Vérifier que le créateur existe
        creator = await self.collection.find_one({"_id": ObjectId(creator_id)})
        if not creator:
            raise ValueError("Creator not found")

        # Vérifier les permissions en fonction du rôle du créateur
        await self._verify_creation_permissions(creator["role"], user_data.role)

        # Vérifier si l'email existe déjà
        if await self.collection.find_one({"email": user_data.email}):
            raise ValueError("Email already registered")

        # Préparer les données utilisateur
        user_dict = user_data.dict()
        user_dict["hashed_password"] = self.get_password_hash(user_dict.pop("password"))
        user_dict["created_at"] = datetime.utcnow()
        user_dict["updated_at"] = datetime.utcnow()
        user_dict["created_by"] = creator_id

        # Insérer le nouvel utilisateur
        result = await self.collection.insert_one(user_dict)
        
        # Enregistrer l'action dans les logs
        await self._log_action(
            creator_id,
            f"Created new {user_data.role} user: {user_data.email}"
        )

        return await self.get_user_by_id(str(result.inserted_id))

    async def _verify_creation_permissions(self, creator_role: str, new_user_role: str):
        """Vérifie les permissions de création d'utilisateur"""
        
        allowed_creations = {
            UserRole.SUPER_ADMIN: [UserRole.ADMIN],
            UserRole.ADMIN: [UserRole.AGENT, UserRole.WORK],
            UserRole.AGENT: [UserRole.WORK],
            UserRole.WORK: []
        }

        if new_user_role not in allowed_creations[creator_role]:
            raise ValueError(
                f"A {creator_role} cannot create a {new_user_role} user"
            )

    async def get_user_by_id(self, user_id: str) -> Optional[UserInDB]:
        user = await self.collection.find_one({"_id": ObjectId(user_id)})
        if user:
            user["id"] = str(user["_id"])
            return UserInDB(**user)
        return None

    async def get_users_by_creator(self, creator_id: str) -> List[UserInDB]:
        users = await self.collection.find(
            {"created_by": creator_id}
        ).to_list(None)
        return [UserInDB(**{**user, "id": str(user["_id"])}) for user in users]

    async def update_user(
        self, 
        updater_id: str, 
        user_id: str, 
        user_update: UserUpdate
    ) -> Optional[UserInDB]:
        # Vérifier les permissions
        updater = await self.get_user_by_id(updater_id)
        target_user = await self.get_user_by_id(user_id)

        if not updater or not target_user:
            raise ValueError("Updater or target user not found")

        if not self._can_modify_user(updater.role, target_user.role):
            raise ValueError(
                f"A {updater.role} cannot modify a {target_user.role}"
            )

        update_data = user_update.dict(exclude_unset=True)
        if "password" in update_data:
            update_data["hashed_password"] = self.get_password_hash(
                update_data.pop("password")
            )

        update_data["updated_at"] = datetime.utcnow()

        await self.collection.update_one(
            {"_id": ObjectId(user_id)},
            {"$set": update_data}
        )

        # Log the update
        await self._log_action(
            updater_id,
            f"Updated user: {user_id}"
        )

        return await self.get_user_by_id(user_id)

    async def delete_user(self, deleter_id: str, user_id: str) -> bool:
        # Vérifier les permissions
        deleter = await self.get_user_by_id(deleter_id)
        target_user = await self.get_user_by_id(user_id)

        if not deleter or not target_user:
            raise ValueError("Deleter or target user not found")

        if not self._can_modify_user(deleter.role, target_user.role):
            raise ValueError(
                f"A {deleter.role} cannot delete a {target_user.role}"
            )

        result = await self.collection.delete_one({"_id": ObjectId(user_id)})

        if result.deleted_count:
            # Log the deletion
            await self._log_action(
                deleter_id,
                f"Deleted user: {user_id}"
            )
            return True
        return False

    def _can_modify_user(self, modifier_role: str, target_role: str) -> bool:
        """Vérifie si un utilisateur peut modifier un autre utilisateur"""
        
        role_hierarchy = {
            UserRole.SUPER_ADMIN: 4,
            UserRole.ADMIN: 3,
            UserRole.AGENT: 2,
            UserRole.WORK: 1
        }

        return role_hierarchy[modifier_role] > role_hierarchy[target_role]
    
    

    async def _log_action(self, user_id: str, action: str):
        """Enregistre une action dans les logs"""
        
        log_entry = {
            "user_id": user_id,
            "action": action,
            "timestamp": datetime.utcnow()
        }
        await self.db.logs.insert_one(log_entry)

    async def get_users_hierarchy(self, user_id: str) -> dict:
        """Récupère la hiérarchie des utilisateurs créés par un utilisateur"""
        
        user = await self.get_user_by_id(user_id)
        if not user:
            raise ValueError("User not found")

        hierarchy = {
            "user": user.dict(),
            "created_users": []
        }

        created_users = await self.get_users_by_creator(user_id)
        for created_user in created_users:
            sub_hierarchy = await self.get_users_hierarchy(str(created_user.id))
            hierarchy["created_users"].append(sub_hierarchy)

        return hierarchy
    
    async def check_email_availability(self, email: str) -> bool:
        """
        Vérifie si l'email est déjà utilisé par n'importe quel type d'utilisateur
        Retourne True si l'email est disponible, False sinon
        """
        # Vérifier dans la collection users
        existing_user = await self.collection.find_one({"email": email})
        if existing_user:
            return False

        # Si l'email est libre, retourner True
        return True

    async def create_user(self, creator_id: str, user_data: UserCreate) -> UserInDB:
        # Vérifier que le créateur existe
        creator = await self.collection.find_one({"_id": ObjectId(creator_id)})
        if not creator:
            raise ValueError("Creator not found")

        # Vérifier les permissions en fonction du rôle du créateur
        await self._verify_creation_permissions(creator["role"], user_data.role)

        # Vérifier si l'email est disponible
        if not await self.check_email_availability(user_data.email):
            raise ValueError("Cette adresse email est déjà utilisée par un autre utilisateur (agent, technicien, admin ou call center). Veuillez en choisir une autre.")