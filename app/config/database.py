# Modification de database.py
from motor.motor_asyncio import AsyncIOMotorClient
from app.config.settings import settings

# Créer une seule instance de client partagée
_client = None

async def get_database():
    global _client
    if _client is None:
        _client = AsyncIOMotorClient(
            settings.mongodb_url,
            maxPoolSize=10,  # Ajuster selon vos besoins
            minPoolSize=5,
            waitQueueTimeoutMS=1000,
            connectTimeoutMS=5000
        )
    return _client[settings.database_name]
