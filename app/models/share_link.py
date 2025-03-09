from datetime import datetime, timedelta
from pydantic import BaseModel, Field, validator
from typing import Optional, List
import secrets
import string
from bson import ObjectId

class PyObjectId(ObjectId):
    @classmethod
    def __get_validators__(cls):
        yield cls.validate

    @classmethod
    def validate(cls, v):
        if not ObjectId.is_valid(v):
            raise ValueError("Invalid objectid")
        return ObjectId(v)

    @classmethod
    def __modify_schema__(cls, field_schema):
        field_schema.update(type="string")

# Fonction pour générer un token sécurisé
def generate_secure_token(length=32):
    alphabet = string.ascii_letters + string.digits
    return ''.join(secrets.choice(alphabet) for _ in range(length))

class ShareLinkBase(BaseModel):
    technician_id: PyObjectId
    expires_at: datetime
    can_add_appointments: bool = False
    token: str = Field(default_factory=lambda: generate_secure_token(32))
    created_at: datetime = Field(default_factory=datetime.utcnow)
    created_by: Optional[PyObjectId] = None  # L'utilisateur qui a créé le lien
    is_active: bool = True
    access_count: int = 0  # Compteur d'accès au lien
    last_accessed_at: Optional[datetime] = None
    ip_whitelist: List[str] = []  # Liste d'adresses IP autorisées (optionnel)
    
    class Config:
        arbitrary_types_allowed = True
        json_encoders = {
            ObjectId: str
        }

class ShareLinkCreate(BaseModel):
    technician_id: str
    duration: int  # Durée en heures
    duration_unit: str = "hours"  # "hours", "days", "months"
    can_add_appointments: bool = False
    created_by: Optional[str] = None
    ip_whitelist: List[str] = []
    
    @validator('duration_unit')
    def validate_duration_unit(cls, v):
        allowed_units = ["hours", "days", "months"]
        if v not in allowed_units:
            raise ValueError(f"La durée doit être en {', '.join(allowed_units)}")
        return v
    
    @validator('duration')
    def validate_duration(cls, v):
        if v <= 0:
            raise ValueError("La durée doit être positive")
        return v
    
    def calculate_expiry(self) -> datetime:
        now = datetime.utcnow()
        if self.duration_unit == "hours":
            return now + timedelta(hours=self.duration)
        elif self.duration_unit == "days":
            return now + timedelta(days=self.duration)
        elif self.duration_unit == "months":
            # Approximation pour les mois (30 jours)
            return now + timedelta(days=30 * self.duration)
        return now + timedelta(hours=self.duration)  # Défaut

class ShareLinkDB(ShareLinkBase):
    id: PyObjectId = Field(default_factory=PyObjectId, alias="_id")
    
    class Config:
        allow_population_by_field_name = True
        arbitrary_types_allowed = True
        json_encoders = {
            ObjectId: str
        }

class ShareLinkResponse(BaseModel):
    id: str
    technician_id: str
    expires_at: datetime
    can_add_appointments: bool
    token: str
    created_at: datetime
    created_by: Optional[str] = None
    is_active: bool
    access_count: int
    last_accessed_at: Optional[datetime] = None
    share_url: str
    remaining_time: str  # Temps restant avant expiration (formaté)
    
    class Config:
        arbitrary_types_allowed = True
        json_encoders = {
            ObjectId: str
        }

class ShareLinkRevoke(BaseModel):
    id: str
    revoked_by: Optional[str] = None
    reason: Optional[str] = None