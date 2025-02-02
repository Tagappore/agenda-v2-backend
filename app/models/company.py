from datetime import datetime
from pydantic import BaseModel, Field, ConfigDict
from typing import Optional
from bson import ObjectId

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
    def __get_pydantic_json_schema__(cls, field_schema):
        field_schema.update(type="string")

class Company(BaseModel):
    model_config = ConfigDict(
        populate_by_name=True,  # Nouveau nom pour allow_population_by_field_name
        from_attributes=True,   # Nouveau nom pour orm_mode
        arbitrary_types_allowed=True,
        json_encoders={
            ObjectId: str
        }
    )

    id: Optional[PyObjectId] = Field(default=None, alias='_id')
    name: str
    siret: str
    email: str
    phone: Optional[str] = None
    address: Optional[str] = None
    postal_code: Optional[str] = None
    city: Optional[str] = None
    is_active: bool = True
    logo_url: Optional[str] = None
    token_invalidation_timestamp: Optional[datetime] = None
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)