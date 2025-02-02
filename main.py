from contextlib import asynccontextmanager
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from motor.motor_asyncio import AsyncIOMotorClient
import os
from fastapi.staticfiles import StaticFiles
from app.routes import auth, super_admin, admin, agent, work, companies
from app.config import settings
from app.routes.email import router as email_router
from typing import Dict

# Gestionnaire des connexions WebSocket
class ConnectionManager:
    def __init__(self):
        self.active_connections: Dict[str, WebSocket] = {}

    async def connect(self, client_id: str, websocket: WebSocket):
        await websocket.accept()
        self.active_connections[client_id] = websocket

    def disconnect(self, client_id: str):
        if client_id in self.active_connections:
            del self.active_connections[client_id]

    async def send_deactivation_message(self, company_id: str):
        """Envoie un message de désactivation à tous les clients connectés d'une entreprise"""
        for client_id, websocket in self.active_connections.items():
            if client_id.startswith(f"company_{company_id}"):
                try:
                    await websocket.send_json({
                        "type": "deactivation",
                        "message": "Votre compte a été désactivé"
                    })
                except:
                    await self.disconnect(client_id)

manager = ConnectionManager()

# Gestionnaire de cycle de vie de l'application
@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup: Connexion à la base de données
    app.mongodb_client = AsyncIOMotorClient(settings.mongodb_url)
    app.mongodb = app.mongodb_client[settings.database_name]
    app.websocket_manager = manager
    
    yield  # L'application s'exécute ici
    
    # Shutdown: Fermeture de la connexion à la base de données
    app.mongodb_client.close()

# Création de l'application avec le gestionnaire de cycle de vie
app = FastAPI(
    title="Dashboard API",
    lifespan=lifespan
)

# Intégration du router email
app.include_router(email_router, prefix="/api")

# Configuration CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["https://app.tag-appore.com/"],  # À configurer avec les domaines autorisés en production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["*"]
)

# WebSocket endpoint
@app.websocket("/ws/{client_id}")
async def websocket_endpoint(websocket: WebSocket, client_id: str):
    await manager.connect(client_id, websocket)
    try:
        while True:
            data = await websocket.receive_json()
            # Garder la connexion active et traiter les messages si nécessaire
    except WebSocketDisconnect:
        manager.disconnect(client_id)
    except Exception as e:
        print(f"WebSocket error: {str(e)}")
        manager.disconnect(client_id)

# Include routers
app.include_router(auth.router, prefix="/api/auth", tags=["auth"])
app.include_router(companies.router, prefix="/api/companies", tags=["companies"])
app.include_router(super_admin.router, prefix="/api", tags=["super-admin"])
app.include_router(admin.router, prefix="/api", tags=["admin"])
app.include_router(agent.router, prefix="/api", tags=["agent"])
app.include_router(work.router, prefix="/api", tags=["work"])

# Configuration des fichiers statiques
STATIC_DIR = os.path.join(os.path.dirname(os.path.realpath(__file__)), "static")
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

# Events de démarrage et d'arrêt
@app.on_event("startup")
async def startup():
    app.mongodb_client = AsyncIOMotorClient(settings.mongodb_url)
    app.mongodb = app.mongodb_client[settings.database_name]

@app.on_event("shutdown")
async def shutdown():
    app.mongodb_client.close()

# Route racine
@app.get("/")
async def root():
    return {"message": "Welcome to the Dashboard API"}

# Méthode pour notification de désactivation (à appeler depuis super_admin.py)
async def notify_company_deactivation(company_id: str):
    await manager.send_deactivation_message(company_id)
