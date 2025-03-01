# backend/app/routes/health.py
from fastapi import APIRouter

router = APIRouter(tags=["health"])

@router.get("/health")
async def health_check():
    """
    Simple endpoint pour vérifier que le serveur est en ligne
    et éviter les cold starts de Render.com
    """
    return {"status": "ok"}