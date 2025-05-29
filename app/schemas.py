from pydantic import BaseModel
from datetime import datetime
from typing import List, Optional, Dict

class Attributes(BaseModel):
    pets_allowed: bool = False
    barrier_free: bool = False
    toilet_available: bool = False
    food_available: bool = False
    medical_available: bool = False
    wifi_available: bool = False
    charging_available: bool = False
    equipment: str = ""

class Shelter(BaseModel):
    id: Optional[int] = None
    name: str
    address: str
    latitude: float
    longitude: float
    capacity: int
    current_occupancy: int
    attributes: Attributes
    photos: List[str] = []
    contact: Optional[str] = None
    operator: str
    opened_at: datetime
    status: str
    updated_at: Optional[datetime] = None
    company_id: int

    class Config:
        from_attributes = True

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