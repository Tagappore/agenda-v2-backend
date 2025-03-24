# app/routes/prospect_comments.py
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import JSONResponse
from typing import List, Dict, Any
from motor.motor_asyncio import AsyncIOMotorDatabase
from app.routes.auth import verify_admin_or_call_center
from app.config.database import get_database
from app.models.prospect_comment import CommentType, ProspectCommentCreate, ProspectCommentResponse
from bson import ObjectId
from datetime import datetime
import logging

router = APIRouter(tags=["prospect-comments"])

# Configurer le logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("prospect-comments")


def format_comment_response(comment: Dict[str, Any]) -> Dict[str, Any]:
    """Formate la réponse du commentaire de prospect de manière cohérente"""
    return {
        "id": str(comment.get("_id", "")),
        "prospect_id": comment.get("prospect_id", ""),
        "comment": comment.get("comment", ""),
        "type": comment.get("type", ""),
        "user_id": comment.get("user_id", ""),
        "user_name": comment.get("user_name", ""),
        "created_at": comment.get("created_at", datetime.utcnow()),
    }


@router.post("/prospect-comments", response_model=ProspectCommentResponse)
async def create_prospect_comment(
    comment_data: Dict[str, Any],
    current_user: dict = Depends(verify_admin_or_call_center),
    db: AsyncIOMotorDatabase = Depends(get_database)
):
    """Crée un nouveau commentaire pour un prospect"""
    try:
        logger.info(f"Création de commentaire par {current_user['email']} (rôle: {current_user['role']})")
        
        # Vérifier que le prospect existe
        prospect_id = comment_data.get("prospect_id")
        if not prospect_id:
            raise HTTPException(status_code=400, detail="ID du prospect requis")
        
        prospect = await db.prospects.find_one({"_id": ObjectId(prospect_id)})
        if not prospect:
            raise HTTPException(status_code=404, detail="Prospect non trouvé")
        
        # Vérifier les permissions selon le rôle
        if current_user["role"] in ["super_admin", "admin"]:
            # Admin ne peut commenter que les prospects de sa propre entreprise
            if prospect.get("company_id") != current_user["company_id"]:
                raise HTTPException(status_code=403, detail="Vous n'êtes pas autorisé à commenter ce prospect")
            # Admin ne peut créer que des commentaires de type 'regie'
            if comment_data.get("type") != CommentType.REGIE:
                comment_data["type"] = CommentType.REGIE
                logger.info("Type forcé à 'regie' pour utilisateur admin")
        
        elif current_user["role"] == "call_center":
            # Call center ne peut commenter que ses propres prospects
            if prospect.get("call_center_id") != current_user["id"]:
                raise HTTPException(status_code=403, detail="Vous n'êtes pas autorisé à commenter ce prospect")
            # Call center ne peut créer que des commentaires de type 'call_center'
            if comment_data.get("type") != CommentType.CALL_CENTER:
                comment_data["type"] = CommentType.CALL_CENTER
                logger.info("Type forcé à 'call_center' pour utilisateur call center")
        
        # Préparer les données du commentaire
        comment_data["user_id"] = current_user["id"]
        comment_data["user_name"] = current_user.get("name", current_user.get("username", current_user["email"]))
        comment_data["company_id"] = current_user["company_id"]
        comment_data["created_at"] = datetime.utcnow()
        
        # Insérer le commentaire dans la base de données
        result = await db.prospect_comments.insert_one(comment_data)
        
        # Récupérer le commentaire créé
        created_comment = await db.prospect_comments.find_one({"_id": result.inserted_id})
        return format_comment_response(created_comment)
    
    except Exception as e:
        logger.error(f"Erreur lors de la création du commentaire: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/prospects/{prospect_id}/comments", response_model=List[ProspectCommentResponse])
async def get_prospect_comments(
    prospect_id: str,
    current_user: dict = Depends(verify_admin_or_call_center),
    db: AsyncIOMotorDatabase = Depends(get_database)
):
    """Récupère tous les commentaires d'un prospect"""
    try:
        logger.info(f"Récupération des commentaires pour le prospect {prospect_id}")
        
        # Vérifier que le prospect existe
        prospect = await db.prospects.find_one({"_id": ObjectId(prospect_id)})
        if not prospect:
            raise HTTPException(status_code=404, detail="Prospect non trouvé")
        
        # Vérifier les permissions selon le rôle
        if current_user["role"] in ["super_admin", "admin"]:
            # Admin ne peut voir que les prospects de sa propre entreprise
            if prospect.get("company_id") != current_user["company_id"]:
                raise HTTPException(status_code=403, detail="Vous n'êtes pas autorisé à voir ce prospect")
        
        elif current_user["role"] == "call_center":
            # Call center ne peut voir que ses propres prospects
            if prospect.get("call_center_id") != current_user["id"]:
                raise HTTPException(status_code=403, detail="Vous n'êtes pas autorisé à voir ce prospect")
        
        # Récupérer les commentaires
        comments = await db.prospect_comments.find(
            {"prospect_id": prospect_id}
        ).sort("created_at", 1).to_list(None)
        
        # Formater la réponse
        return [format_comment_response(comment) for comment in comments]
    
    except Exception as e:
        logger.error(f"Erreur lors de la récupération des commentaires: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))