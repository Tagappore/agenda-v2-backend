# app/models/prospect_comment.py
from pydantic import BaseModel, Field
from typing import Optional
from bson import ObjectId
from datetime import datetime
from enum import Enum


class CommentType(str, Enum):
    """Type de commentaire: qui l'a écrit"""
    REGIE = "regie"
    CALL_CENTER = "call_center"


class PyObjectId(ObjectId):
    @classmethod
    def __get_validators__(cls):
        yield cls.validate

    @classmethod
    def validate(cls, v):
        if not ObjectId.is_valid(v):
            raise ValueError("Invalid ObjectId")
        return ObjectId(v)

    @classmethod
    def __modify_schema__(cls, field_schema):
        field_schema.update(type="string")


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

    class Config:
        orm_mode = True
        allow_population_by_field_name = True
        json_encoders = {
            ObjectId: str
        }


class ProspectCommentCreate(ProspectCommentBase):
    """Modèle pour la création de commentaires de prospects"""
    pass


class ProspectCommentResponse(ProspectCommentBase):
    """Modèle pour la réponse de commentaires de prospects"""
    id: str

    class Config:
        orm_mode = True
        allow_population_by_field_name = True
        json_encoders = {
            ObjectId: str
        }