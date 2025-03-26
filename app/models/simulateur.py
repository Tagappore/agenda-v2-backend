# backend/app/models/simulateur.py
from pydantic import BaseModel, EmailStr, Field
from typing import List, Dict, Optional
from datetime import datetime

class SubOptions(BaseModel):
    """Modèle pour les sous-options des travaux"""
    combles_type: List[str] = Field(default_factory=list)
    planchers_type: List[str] = Field(default_factory=list)
    murs_type: List[str] = Field(default_factory=list)
    chauffage_type: List[str] = Field(default_factory=list)
    chauffe_eau_type: List[str] = Field(default_factory=list)
    fenetres_type: List[str] = Field(default_factory=list)
    vmc_type: List[str] = Field(default_factory=list)
    solaire_type: List[str] = Field(default_factory=list)

class SimulateurData(BaseModel):
    """Modèle principal pour les données du simulateur"""
    profile: str
    housing: str
    age: str
    heating: List[str] = Field(default_factory=list)
    radiator: List[str] = Field(default_factory=list)
    energy: str
    surface: str
    works: List[str] = Field(default_factory=list)
    subOptions: SubOptions
    status: str
    address: str
    city: str
    department: str
    lastname: str
    firstname: str
    phone: str
    email: EmailStr
    consent: bool
    created_at: datetime = Field(default_factory=datetime.now)
    id: Optional[str] = None