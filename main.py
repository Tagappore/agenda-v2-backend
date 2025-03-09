from contextlib import asynccontextmanager
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from motor.motor_asyncio import AsyncIOMotorClient
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
from app.routes import share_links
from datetime import datetime

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
        self.last_activity: Dict[str, float] = {}  # Pour suivre l'activité des clients

    async def heartbeat(self, client_id: str):
        """Tâche de heartbeat pour maintenir la connexion active"""
        while client_id in self.active_connections:
            try:
                await asyncio.sleep(self.heartbeat_interval)
                # Vérifier si le client est encore actif
                current_time = datetime.now().timestamp()
                if client_id in self.last_activity:
                    last_activity = self.last_activity[client_id]
                    time_since_last_activity = current_time - last_activity
                    
                    # Si pas d'activité depuis 2 fois l'intervalle de heartbeat, déconnecter
                    if time_since_last_activity > (self.heartbeat_interval * 2):
                        print(f"Client {client_id} inactif depuis {time_since_last_activity}s, déconnexion")
                        await self.disconnect(client_id)
                        break
                
                # Envoyer le ping
                await self.active_connections[client_id].send_json({"type": "ping"})
                
                # Mettre à jour le moment de la dernière activité
                self.last_activity[client_id] = current_time
            except Exception as e:
                print(f"Erreur de heartbeat pour {client_id}: {str(e)}")
                await self.disconnect(client_id)
                break

    async def connect(self, client_id: str, websocket: WebSocket):
        try:
            await websocket.accept()
            self.active_connections[client_id] = websocket
            self.reconnect_attempts[client_id] = 0
            self.last_activity[client_id] = datetime.now().timestamp()
            
            # Démarrer la tâche de heartbeat
            self.heartbeat_tasks[client_id] = asyncio.create_task(
                self.heartbeat(client_id)
            )
            
            # Envoyer un message de bienvenue
            await websocket.send_json({
                "type": "connection_established",
                "message": "Connexion WebSocket établie",
                "client_id": client_id,
                "timestamp": datetime.now().timestamp()
            })
            
            print(f"Client {client_id} connecté")
        except Exception as e:
            print(f"Erreur lors de la connexion de {client_id}: {str(e)}")
            await self.disconnect(client_id)

    async def disconnect(self, client_id: str):
        if client_id in self.active_connections:
            # Annuler la tâche de heartbeat
            if client_id in self.heartbeat_tasks:
                try:
                    self.heartbeat_tasks[client_id].cancel()
                except Exception as e:
                    print(f"Erreur lors de l'annulation du heartbeat pour {client_id}: {str(e)}")
                finally:
                    if client_id in self.heartbeat_tasks:
                        del self.heartbeat_tasks[client_id]

            # Nettoyer les autres structures de données
            if client_id in self.last_activity:
                del self.last_activity[client_id]
            
            if client_id in self.reconnect_attempts:
                del self.reconnect_attempts[client_id]

            # Fermer la connexion WebSocket
            try:
                await self.active_connections[client_id].close()
            except Exception as e:
                print(f"Erreur lors de la fermeture de la connexion pour {client_id}: {str(e)}")

            # Supprimer de la liste des connexions actives
            del self.active_connections[client_id]
            print(f"Client {client_id} déconnecté")

    async def send_to_client(self, client_id: str, message: dict):
        """Envoie un message à un client spécifique"""
        if client_id in self.active_connections:
            try:
                await self.active_connections[client_id].send_json(message)
                self.last_activity[client_id] = datetime.now().timestamp()
                return True
            except Exception as e:
                print(f"Erreur lors de l'envoi à {client_id}: {str(e)}")
                await self.disconnect(client_id)
                return False
        return False

    async def send_to_company(self, company_id: str, message: dict):
        """Envoie un message à tous les clients connectés d'une entreprise"""
        success_count = 0
        company_prefix = f"company_{company_id}_"
        for client_id, connection in list(self.active_connections.items()):
            if client_id.startswith(company_prefix):
                try:
                    await connection.send_json(message)
                    self.last_activity[client_id] = datetime.now().timestamp()
                    success_count += 1
                except Exception as e:
                    print(f"Erreur lors de l'envoi à {client_id}: {str(e)}")
                    await self.disconnect(client_id)
        return success_count

    async def send_deactivation_message(self, company_id: str):
        """Envoie un message de désactivation à tous les clients d'une entreprise"""
        message = {
            "type": "deactivation",
            "message": "Votre compte a été désactivé",
            "timestamp": datetime.now().timestamp()
        }
        count = await self.send_to_company(company_id, message)
        print(f"Message de désactivation envoyé à {count} clients de l'entreprise {company_id}")
        return count

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
                # Mettre à jour le timestamp d'activité
                manager.last_activity[client_id] = datetime.now().timestamp()
                
                # Répondre selon le type de message
                message_type = data.get("type", "")
                
                # Répondre aux pings pour maintenir la connexion
                if message_type == "ping":
                    await websocket.send_json({
                        "type": "pong",
                        "timestamp": datetime.now().timestamp()
                    })
                
                # Répondre aux heartbeats du client
                elif message_type == "heartbeat":
                    await websocket.send_json({
                        "type": "heartbeat_response",
                        "timestamp": datetime.now().timestamp()
                    })
                
                # Message de connexion initial
                elif message_type == "connect":
                    await websocket.send_json({
                        "type": "connected",
                        "client_id": client_id,
                        "timestamp": datetime.now().timestamp()
                    })
                
                # Log pour tout autre type de message
                else:
                    print(f"Message reçu de {client_id}: {data}")
                    
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
app.include_router(call_center.router, prefix="/api", tags=["call_centers"])
app.include_router(prospect.router, prefix="/api", tags=["prospects"])
app.include_router(appointments.router, prefix="/api", tags=["appointments"])
app.include_router(health.router, prefix="/api",tags=["health"])
app.include_router(share_links.router, prefix="/api", tags=["share-links"])

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
    if hasattr(app, 'websocket_manager'):
        return await app.websocket_manager.send_deactivation_message(company_id)
    return 0