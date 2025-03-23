from contextlib import asynccontextmanager
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
import asyncio
from fastapi.staticfiles import StaticFiles
from app.routes import auth, super_admin, admin, agent, technician, companies, call_center, prospect
from app.config import settings
from app.routes.email import router as email_router
from typing import Dict
from app.routes import technician
from app.routes import call_center
from app.routes import prospect
from app.routes import appointments
from app.routes import health
from app.config.database import DatabaseConnection
from app.routes.absences import router as absences_router
from app.routes import call_center_prospect

# Au début du fichier, avant d'importer quoi que ce soit d'autre
import os
import sys
print(f"Démarrage de l'application avec Python {sys.version}")
print(f"Répertoire courant: {os.getcwd()}")
print(f"Variables d'environnement: {list(os.environ.keys())}")

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

    # Ajout d'une méthode pour envoyer des messages de désactivation
    async def send_deactivation_message(self, company_id: str):
        # Envoyer un message à tous les clients connectés de cette entreprise
        for client_id, websocket in list(self.active_connections.items()):
            try:
                # Vous devrez avoir une façon de déterminer quels clients
                # appartiennent à quelle entreprise
                await websocket.send_json({
                    "type": "company_deactivated",
                    "company_id": company_id
                })
            except Exception as e:
                print(f"Erreur lors de l'envoi du message de désactivation: {str(e)}")

manager = ConnectionManager()

# Gestionnaire de cycle de vie de l'application
@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup: Utiliser la connexion singleton à la base de données
    app.mongodb = await DatabaseConnection.get_database()
    app.websocket_manager = manager
    
    yield  # L'application s'exécute ici
    
    # Pas besoin de fermer la connexion ici, elle est gérée par le singleton

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
        "https://app.tag-appore.com", 
        "http://back.app.tag-appore.com", # Sans le slash final
        "https://back.app.tag-appore.com", # Version HTTPS
        "https://agenda-v2-backend.onrender.com",
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
        await manager.disconnect(client_id)

# Include routers
app.include_router(auth.router, prefix="/api/auth", tags=["auth"])
app.include_router(companies.router, prefix="/api/companies", tags=["companies"])
app.include_router(super_admin.router, prefix="/api", tags=["super-admin"])
app.include_router(admin.router, prefix="/api", tags=["admin"])
app.include_router(agent.router, prefix="/api", tags=["agent"])
app.include_router(technician.router, prefix="/api", tags=["technicians"])
app.include_router(prospect.router, prefix="/api", tags=["prospects"])
app.include_router(appointments.router, prefix="/api", tags=["appointments"])
app.include_router(health.router, prefix="/api", tags=["health"])
app.include_router(absences_router, prefix="/api", tags=["absences"])
app.include_router(call_center.router, prefix="/api", tags=["call_centers"])
app.include_router(call_center_prospect.router, prefix="/api", tags=["call_center_prospects"])

# Configuration des fichiers statiques
STATIC_DIR = os.path.join(os.path.dirname(os.path.realpath(__file__)), "static")
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

# Les événements de démarrage et d'arrêt ont été supprimés car ils sont redondants
# avec le gestionnaire de cycle de vie et créent des connexions inutiles

# Route racine
@app.get("/")
async def root():
    return {"message": "Welcome to the Dashboard API"}

# Méthode pour notification de désactivation (à appeler depuis super_admin.py)
async def notify_company_deactivation(company_id: str):
    await manager.send_deactivation_message(company_id)