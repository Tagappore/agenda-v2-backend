
# backend/app/routes/simulateurs.py (notez le 's')
from fastapi import APIRouter, Depends, HTTPException, status
from app.models.simulateur import SimulateurData  # importation depuis simulateur.py (sans 's')
from app.routes.auth import verify_super_admin, get_auth_service  # Importer depuis routes/auth.py
from app.config.database import get_database
from typing import List
from bson import ObjectId
import pymongo
from datetime import datetime

router = APIRouter(prefix="/simulateur", tags=["simulateur"])

@router.post("/submit", status_code=status.HTTP_201_CREATED)
async def submit_simulateur_data(data: SimulateurData):
    """
    Enregistre les données du simulateur dans la base de données.
    Cette route est accessible publiquement pour permettre aux visiteurs de soumettre leurs informations.
    """
    try:
        db = await get_database()
        
        # Conversion des données pour MongoDB
        simulateur_data = data.dict()
        simulateur_data["created_at"] = datetime.now()
        
        # Insertion dans la base de données
        result = await db.simulateur_data.insert_one(simulateur_data)
        
        # Vérifier si l'insertion a réussi
        if result.inserted_id:
            return {"message": "Données enregistrées avec succès", "id": str(result.inserted_id)}
        else:
            raise HTTPException(status_code=500, detail="Erreur lors de l'enregistrement des données")
            
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erreur serveur: {str(e)}")

@router.get("/data", response_model=List[SimulateurData])
async def get_simulateur_data(current_user = Depends(is_super_admin)):
    """
    Récupère toutes les données du simulateur.
    Accessible uniquement aux super admins.
    """
    try:
        db = await get_database()
        
        # Récupération des données avec tri par date décroissante
        cursor = db.simulateur_data.find().sort("created_at", pymongo.DESCENDING)
        
        # Conversion des ObjectId en string pour la sérialisation JSON
        results = []
        async for document in cursor:
            document["id"] = str(document.pop("_id"))
            results.append(document)
            
        return results
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erreur serveur: {str(e)}")

@router.get("/data/{data_id}", response_model=SimulateurData)
async def get_simulateur_data_by_id(data_id: str, current_user = Depends(is_super_admin)):
    """
    Récupère les données détaillées d'une simulation par son ID.
    Accessible uniquement aux super admins.
    """
    try:
        db = await get_database()
        
        # Vérifier si l'id est valide
        if not ObjectId.is_valid(data_id):
            raise HTTPException(status_code=400, detail="ID non valide")
        
        # Récupération des données
        document = await db.simulateur_data.find_one({"_id": ObjectId(data_id)})
        
        if not document:
            raise HTTPException(status_code=404, detail="Données non trouvées")
            
        # Conversion de l'ObjectId en string pour la sérialisation JSON
        document["id"] = str(document.pop("_id"))
        
        return document
        
    except Exception as e:
        if isinstance(e, HTTPException):
            raise e
        raise HTTPException(status_code=500, detail=f"Erreur serveur: {str(e)}")

@router.delete("/data/{data_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_simulateur_data(data_id: str, current_user = Depends(is_super_admin)):
    """
    Supprime une entrée de simulation par son ID.
    Accessible uniquement aux super admins.
    """
    try:
        db = await get_database()
        
        # Vérifier si l'id est valide
        if not ObjectId.is_valid(data_id):
            raise HTTPException(status_code=400, detail="ID non valide")
        
        # Suppression de l'entrée
        result = await db.simulateur_data.delete_one({"_id": ObjectId(data_id)})
        
        if result.deleted_count == 0:
            raise HTTPException(status_code=404, detail="Données non trouvées")
            
        return None
        
    except Exception as e:
        if isinstance(e, HTTPException):
            raise e
        raise HTTPException(status_code=500, detail=f"Erreur serveur: {str(e)}")