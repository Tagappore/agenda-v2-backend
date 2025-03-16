from pydantic import BaseModel
from datetime import datetime
from typing import Optional
from enum import Enum

class AbsenceType(str, Enum):
    PERSONAL = "personal"
    VACATION = "vacation"
    SICK = "sick"
    OTHER = "other"

class AbsenceBase(BaseModel):
    title: str
    start_date: datetime
    end_date: datetime
    technician_id: str
    description: Optional[str] = None
    absence_type: AbsenceType = AbsenceType.PERSONAL

class AbsenceCreate(AbsenceBase):
    company_id: str

class AbsenceUpdate(BaseModel):
    title: Optional[str] = None
    start_date: Optional[datetime] = None
    end_date: Optional[datetime] = None
    description: Optional[str] = None
    absence_type: Optional[AbsenceType] = None

class Absence(AbsenceBase):
    id: str
    company_id: str
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True