from pydantic import BaseModel, validator
from datetime import datetime
from typing import Optional
from enum import Enum

class AppointmentStatus(str, Enum):
    CREATED = "created"
    CONFIRMED = "confirmed"
    COMPLETED = "completed"
    CANCELLED = "cancelled"

class AppointmentBase(BaseModel):
    dateTime: datetime
    comment: Optional[str] = None
    name: str
    address: str
    city: str
    postal_code: str
    phone: str
    technician_id: str
    prospect_id: str  # Lien avec le prospect
    status: AppointmentStatus = AppointmentStatus.CREATED

class AppointmentCreate(AppointmentBase):
    company_id: str

class AppointmentUpdate(BaseModel):
    dateTime: Optional[datetime] = None
    comment: Optional[str] = None
    technician_id: Optional[str] = None
    status: Optional[AppointmentStatus] = None

class Appointment(AppointmentBase):
    id: str
    company_id: str
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True