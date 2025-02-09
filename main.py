from contextlib import asynccontextmanager
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from motor.motor_asyncio import AsyncIOMotorClient
import os
import asyncio
from fastapi.staticfiles import StaticFiles
from app.routes import auth, super_admin, admin, agent, work, companies
from app.config import settings
from app.routes.email import router as email_router
from typing import Dict
from app.routes import technician
from app.routes import call_center
from app.routes import prospect

# Gestionnaire des connexions WebSocket
class ConnectionManager:
    def __init__(self):
        self.active_connections: Dict[str, WebSocket] = {}
        self.reconnect_attempts: Dict[str, int] = {}
        self.heartbeat_tasks: Dict[str, asyncio.Task] = {}
        self.max_reconnect_attempts = settings.ws_max_reconnect_attempts
        self.heartbeat_interval = settings.ws_heartbeat_interval
        self.connection_timeout = settings.ws_connection_timeout

    async def heartbeat(self, client_id: str):
        """Tâche de heartbeat pour maintenir la connexion active"""
        while client_id in self.active_connections:
            try:
                await asyncio.sleep(self.heartbeat_interval)
                await self.active_connections[client_id].send_json({"type": "ping"})
            except Exception:
                await self.disconnect(client_id)
                break

    async def connect(self, client_id: str, websocket: WebSocket):
        try:
            await websocket.accept()
            self.active_connections[client_id] = websocket
            self.reconnect_attempts[client_id] = 0
            
            # Démarrer la tâche de heartbeat
            self.heartbeat_tasks[client_id] = asyncio.create_task(
                self.heartbeat(client_id)
            )
            
            print(f"Client {client_id} connecté")
        except Exception as e:
            print(f"Erreur lors de la connexion de {client_id}: {str(e)}")
            await self.disconnect(client_id)

    async def disconnect(self, client_id: str):
        if client_id in self.active_connections:
            # Annuler la tâche de heartbeat
            if client_id in self.heartbeat_tasks:
                self.heartbeat_tasks[client_id].cancel()
                del self.heartbeat_tasks[client_id]

            # Fermer la connexion WebSocket
            try:
                await self.active_connections[client_id].close()
            except Exception:
                pass

            del self.active_connections[client_id]
            print(f"Client {client_id} déconnecté")

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
    allow_origins=[
        "https://app.tag-appore.com",  # Sans le slash final
        "https://agenda-v2-backend.onrender.com",  # Sans le slash final
        "http://localhost:3000"  # Pour le développement local
    ],
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
            try:
                data = await websocket.receive_json()
                # Répondre aux pings pour maintenir la connexion
                if data.get("type") == "ping":
                    await websocket.send_json({"type": "pong"})
                # Traiter d'autres messages si nécessaire
            except WebSocketDisconnect:
                print(f"WebSocket déconnecté normalement pour {client_id}")
                break
            except Exception as e:
                print(f"Erreur WebSocket pour {client_id}: {str(e)}")
                break
    finally:
        manager.disconnect(client_id)

# Include routers
app.include_router(auth.router, prefix="/api/auth", tags=["auth"])
app.include_router(companies.router, prefix="/api/companies", tags=["companies"])
app.include_router(super_admin.router, prefix="/api", tags=["super-admin"])
app.include_router(admin.router, prefix="/api", tags=["admin"])
app.include_router(agent.router, prefix="/api", tags=["agent"])
app.include_router(work.router, prefix="/api", tags=["work"])
app.include_router(technician.router, prefix="/api", tags=["technicians"])
app.include_router(call_center.router, prefix="/api", tags=["call_centers"])
app.include_router(prospect.router, prefix="/api", tags=["prospects"])

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
