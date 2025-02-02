from pydantic import BaseModel, validator
from datetime import date
from typing import Optional

class ScheduleBase(BaseModel):
    date: date
    start_time: str  # Format: "HH:MM"
    end_time: str    # Format: "HH:MM"
    shift_type: str  # e.g., "morning", "afternoon", "night"
    notes: Optional[str] = None

    @validator('start_time', 'end_time')
    def validate_time_format(cls, v):
        try:
            hour, minute = map(int, v.split(":"))
            if not (0 <= hour <= 23 and 0 <= minute <= 59):
                raise ValueError
            return f"{hour:02d}:{minute:02d}"
        except (ValueError, TypeError):
            raise ValueError("Time must be in format HH:MM")

    @validator('shift_type')
    def validate_shift_type(cls, v):
        valid_types = {"morning", "afternoon", "night"}
        if v.lower() not in valid_types:
            raise ValueError(f"Shift type must be one of: {', '.join(valid_types)}")
        return v.lower()

class ScheduleCreate(ScheduleBase):
    user_id: str

class Schedule(ScheduleBase):
    id: str
    user_id: str
    created_at: date
    updated_at: date

    class Config:
        from_attributes = True

class ScheduleUpdate(BaseModel):
    start_time: Optional[str] = None
    end_time: Optional[str] = None
    shift_type: Optional[str] = None
    notes: Optional[str] = None

    @validator('start_time', 'end_time')
    def validate_time_format(cls, v):
        if v is None:
            return v
        try:
            hour, minute = map(int, v.split(":"))
            if not (0 <= hour <= 23 and 0 <= minute <= 59):
                raise ValueError
            return f"{hour:02d}:{minute:02d}"
        except (ValueError, TypeError):
            raise ValueError("Time must be in format HH:MM")

    @validator('shift_type')
    def validate_shift_type(cls, v):
        if v is None:
            return v
        valid_types = {"morning", "afternoon", "night"}
        if v.lower() not in valid_types:
            raise ValueError(f"Shift type must be one of: {', '.join(valid_types)}")
        return v.lower()