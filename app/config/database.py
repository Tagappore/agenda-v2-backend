from motor.motor_asyncio import AsyncIOMotorClient
from app.config.settings import settings
from typing import Optional

class DatabaseConnection:
    _instance: Optional[AsyncIOMotorClient] = None
    _db = None
    
    @classmethod
    async def get_instance(cls):
        if cls._instance is None:
            cls._instance = AsyncIOMotorClient(
                settings.mongodb_url,
                maxPoolSize=50,  # Augmente la taille du pool
                minPoolSize=10,  # Maintient un minimum de connexions
                maxIdleTimeMS=50000,  # Temps maximum d'inactivité
                waitQueueTimeoutMS=5000,  # Timeout pour les requêtes en attente
                retryWrites=True,
                serverSelectionTimeoutMS=5000,
            )
            # Vérification de la connexion
            try:
                await cls._instance.admin.command('ping')
            except Exception as e:
                cls._instance = None
                raise ConnectionError(f"Impossible de se connecter à MongoDB: {str(e)}")
            
            cls._db = cls._instance[settings.database_name]
            
            # Création des index principaux
            await cls._create_indexes()
            
    @classmethod
    async def _create_indexes(cls):
        # Créer les index nécessaires pour optimiser les requêtes fréquentes
        await cls._db.users.create_index([("email", 1)], unique=True)
        await cls._db.appointments.create_index([("date", 1)])
        await cls._db.appointments.create_index([("status", 1)])
        # Ajoutez d'autres index selon vos besoins

    @classmethod
    async def get_database(cls):
        if cls._instance is None:
            await cls.get_instance()
        return cls._db

async def get_database():
    return await DatabaseConnection.get_database()