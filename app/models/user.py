import datetime
from pydantic import BaseModel, EmailStr
from typing import Optional
from enum import Enum

class UserRole(str, Enum):
    SUPER_ADMIN = "super_admin"
    ADMIN = "admin"
    AGENT = "agent"
    WORK = "work"

class UserBase(BaseModel):
    email: EmailStr
    username: str
    role: UserRole
    is_active: bool = True

class UserCreate(UserBase):
    password: str

class UserUpdate(BaseModel):
    email: Optional[EmailStr] = None
    username: Optional[str] = None
    is_active: Optional[bool] = None

class UserInDB(UserBase):
    id: str
    hashed_password: str
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    phone: Optional[str] = None
    address: Optional[str] = None
    city: Optional[str] = None
    postal_code: Optional[str] = None
    photo: Optional[str] = None
    company_id: Optional[str] = None
    created_at: datetime.datetime = datetime.datetime.now()
    updated_at: datetime.datetime = datetime.datetime.now()

    class Config:
        from_attributes = True

class User(BaseModel):
    id: str
    email: str
    username: str
    role: UserRole
    is_active: bool
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    phone: Optional[str] = None
    address: Optional[str] = None
    city: Optional[str] = None
    postal_code: Optional[str] = None
    photo: Optional[str] = None
    company_id: Optional[str] = None
    created_at: datetime.datetime
    updated_at: datetime.datetime

    class Config:
        from_attributes = True
        json_encoders = {
            datetime.datetime: lambda dt: dt.isoformat()
        }

class AgentCreate(UserCreate):
    first_name: str
    last_name: str
    phone: str
    address: str
    city: str
    postal_code: str
    photo: Optional[str] = None
    company_id: str
    role: UserRole = UserRole.AGENT

class AgentUpdate(UserUpdate):
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    phone: Optional[str] = None
    address: Optional[str] = None
    city: Optional[str] = None
    postal_code: Optional[str] = None
    photo: Optional[str] = None