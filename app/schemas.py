from pydantic import BaseModel
from datetime import datetime
from typing import List, Optional, Dict

class ShelterAttributes(BaseModel):
    pets_allowed: Optional[bool] = False
    barrier_free: Optional[bool] = False
    toilet_available: Optional[bool] = False
    food_available: Optional[bool] = False
    medical_available: Optional[bool] = False
    wifi_available: Optional[bool] = False
    charging_available: Optional[bool] = False

class ShelterCreate(BaseModel):
    name: str
    address: str
    latitude: float
    longitude: float
    capacity: int
    current_occupancy: int
    attributes: ShelterAttributes
    contact: Optional[str] = None
    operator: Optional[str] = None
    opened_at: Optional[str] = None
    status: Optional[str] = "open"
    company_id: int

class ShelterSchema(ShelterCreate):
    id: int
    class Config:
        orm_mode = True

class ShelterUpdate(BaseModel):
    name: Optional[str] = None
    address: Optional[str] = None
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    capacity: Optional[int] = None
    current_occupancy: Optional[int] = None
    attributes: Optional[Dict] = None
    photos: Optional[List[str]] = None
    contact: Optional[str] = None
    operator: Optional[str] = None
    opened_at: Optional[datetime] = None
    status: Optional[str] = None

    class Config:
        from_attributes = True

class AuditLog(BaseModel):
    id: Optional[int] = None
    action: str
    shelter_id: Optional[int] = None
    user: str
    timestamp: datetime

    class Config:
        from_attributes = True

class BulkUpdateRequest(BaseModel):
    shelter_ids: List[int]
    status: Optional[str] = None
    current_occupancy: Optional[int] = None

class CompanySchema(BaseModel):
    id: Optional[int] = None
    email: str
    name: str
    hashed_password: str
    role: str
    created_at: datetime

    class Config:
        from_attributes = True

class PhotoUploadResponse(BaseModel):
    ids: List[int]
    photo_urls: List[str]

    class Config:
        from_attributes = True
