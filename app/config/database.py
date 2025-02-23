from motor.motor_asyncio import AsyncIOMotorClient
from app.config.settings import settings

def get_database():
    client = AsyncIOMotorClient(settings.mongodb_url)
    return client[settings.database_name]  # Ajout du return ici
