from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    # Configuration MongoDB existante
    mongodb_url: str
    database_name: str 
    jwt_secret: str
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 30

    # Configuration WebSocket
    ws_heartbeat_interval: int = 30  # Intervalle de ping en secondes
    ws_connection_timeout: int = 60  # Timeout de connexion en secondes
    ws_max_reconnect_attempts: int = 3  # Nombre maximum de tentatives de reconnexion
    ws_reconnect_interval: int = 5  # Intervalle entre les tentatives en secondes

    class Config:
        env_file = ".env"
        
settings = Settings()