from pydantic import BaseModel, Field
from typing import List, Optional
from datetime import datetime

class ShelterAttributes(BaseModel):
    pets_allowed: bool
    barrier_free: bool
    toilet_available: bool
    food_available: bool
    medical_available: bool
    wifi_available: bool
    charging_available: bool

class Shelter(BaseModel):
    id: Optional[int] = None
    name: str
    address: str = Field(..., min_length=1, max_length=255)
    latitude: float
    longitude: float
    capacity: int
    current_occupancy: int
    attributes: ShelterAttributes
    photos: List[str]
    contact: str
    operator: str
    opened_at: datetime
    status: str
    updated_at: Optional[datetime] = None

    class Config:
        orm_mode = True

class BulkUpdateRequest(BaseModel):
    shelter_ids: List[int]
    status: Optional[str] = None
    current_occupancy: Optional[int] = None


class ShelterUpdate(BaseModel):
    name: Optional[str] = None
    address: Optional[str] = Field(None, min_length=1, max_length=255)
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    capacity: Optional[int] = None
    current_occupancy: Optional[int] = None
    attributes: Optional[ShelterAttributes] = None
    photos: Optional[List[str]] = None
    contact: Optional[str] = None
    operator: Optional[str] = None
    opened_at: Optional[datetime] = None
    status: Optional[str] = None

    class Config:
        orm_mode = True

class AuditLog(BaseModel):
    id: Optional[int] = None
    action: str
    shelter_id: Optional[int] = None
    user: str
    timestamp: datetime

    class Config:
        orm_mode = True