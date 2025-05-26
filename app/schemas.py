from pydantic import BaseModel, Field, EmailStr
from typing import List, Optional
from datetime import datetime

class Shelter(BaseModel):
    id: Optional[int] = None
    name: str = Field(..., min_length=1, max_length=255)
    address: str = Field(..., min_length=1, max_length=255)
    latitude: float
    longitude: float
    capacity: int = Field(..., ge=0)
    current_occupancy: int = Field(..., ge=0)
    pets_allowed: bool = False
    barrier_free: bool = False
    toilet_available: bool = False
    food_available: bool = False
    medical_available: bool = False
    wifi_available: bool = False
    charging_available: bool = False
    equipment: Optional[str] = None
    photos: List[str] = []
    contact: Optional[str] = None
    operator: str = Field(..., min_length=1, max_length=255)
    opened_at: datetime
    status: str = Field(..., pattern="^(open|closed)$")
    updated_at: Optional[datetime] = None
    company_id: Optional[int] = None

    class Config:
        from_attributes = True

class ShelterUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=255)
    address: Optional[str] = Field(None, min_length=1, max_length=255)
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    capacity: Optional[int] = Field(None, ge=0)
    current_occupancy: Optional[int] = Field(None, ge=0)
    pets_allowed: Optional[bool] = None
    barrier_free: Optional[bool] = None
    toilet_available: Optional[bool] = None
    food_available: Optional[bool] = None
    medical_available: Optional[bool] = None
    wifi_available: Optional[bool] = None
    charging_available: Optional[bool] = None
    equipment: Optional[str] = None
    photos: Optional[List[str]] = None
    contact: Optional[str] = None
    operator: Optional[str] = Field(None, min_length=1, max_length=255)
    opened_at: Optional[datetime] = None
    status: Optional[str] = Field(None, pattern="^(open|closed)$")

    class Config:
        from_attributes = True

class BulkUpdateRequest(BaseModel):
    shelter_ids: List[int]
    status: Optional[str] = Field(None, pattern="^(open|closed)$")
    current_occupancy: Optional[int] = Field(None, ge=0)

    class Config:
        from_attributes = True

class AuditLog(BaseModel):
    id: Optional[int] = None
    action: str
    shelter_id: Optional[int] = None
    user: str
    timestamp: datetime
    details: Optional[str] = None

    class Config:
        from_attributes = True

class CompanySchema(BaseModel):
    id: Optional[int] = None
    name: str = Field(..., min_length=1, max_length=255)
    email: EmailStr
    password: Optional[str] = Field(None, min_length=6)
    role: str = Field(default="company", pattern="^(company|admin)$")
    hashed_pw: Optional[str] = None
    created_at: Optional[datetime] = None

    class Config:
        from_attributes = True