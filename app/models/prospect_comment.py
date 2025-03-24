# app/models/prospect_comment.py
from pydantic import BaseModel, Field, field_serializer
from typing import Optional, Any, ClassVar, Dict
from bson import ObjectId
from datetime import datetime
from enum import Enum


class CommentType(str, Enum):
    """Type de commentaire: qui l'a écrit"""
    REGIE = "regie"
    CALL_CENTER = "call_center"


class PyObjectId(str):
    """Classe pour gérer les ObjectId de MongoDB de manière compatible avec Pydantic V2"""
    @classmethod
    def __get_validators__(cls):
        # Cette méthode est conservée pour la compatibilité arrière
        return [cls.validate]

    @classmethod
    def validate(cls, v):
        if not ObjectId.is_valid(v):
            raise ValueError("Invalid ObjectId")
        return str(v)
    
    @classmethod
    def __get_pydantic_json_schema__(cls, _core_schema, field_schema):
        # Remplace __modify_schema__ pour Pydantic V2
        field_schema.update(type="string", format="objectid")
        return field_schema


class ProspectCommentBase(BaseModel):
    """Modèle de base pour les commentaires de prospects"""
    prospect_id: str
    comment: str
    type: CommentType
    user_id: str
    user_name: str
    created_at: datetime = Field(default_factory=datetime.utcnow)


class ProspectCommentInDB(ProspectCommentBase):
    """Modèle pour les commentaires de prospects en base de données"""
    id: PyObjectId = Field(default_factory=PyObjectId, alias="_id")
    company_id: str

    model_config = {
        "populate_by_name": True,
        "json_schema_extra": {
            "json_encoders": {
                ObjectId: str
            }
        }
    }


class ProspectCommentCreate(ProspectCommentBase):
    """Modèle pour la création de commentaires de prospects"""
    pass


class ProspectCommentResponse(ProspectCommentBase):
    """Modèle pour la réponse de commentaires de prospects"""
    id: str

    model_config = {
        "from_attributes": True,
        "populate_by_name": True
    }
    
    @field_serializer('created_at')
    def serialize_dt(self, dt: datetime) -> str:
        return dt.isoformat()