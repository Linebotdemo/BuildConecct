# app/models.py
from sqlalchemy import (
    Column, Integer, String, Float, Boolean,
    DateTime, ForeignKey, Text, Index
)
from sqlalchemy.orm import relationship
from datetime import datetime
from database import Base  # ← ここを database.py からインポート

class Shelter(Base):
    __tablename__ = "shelters"
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, index=True)
    address = Column(String, index=True)
    latitude = Column(Float)
    longitude = Column(Float)
    capacity = Column(Integer)
    current_occupancy = Column(Integer)
    pets_allowed = Column(Boolean, default=False)
    barrier_free = Column(Boolean, default=False)
    toilet_available = Column(Boolean, default=False)
    food_available = Column(Boolean, default=False)
    medical_available = Column(Boolean, default=False)
    wifi_available = Column(Boolean, default=False)
    charging_available = Column(Boolean, default=False)
    equipment = Column(String, default="")
    photos = Column(String, default="")
    contact = Column(String, default="")
    operator = Column(String, default="")
    opened_at = Column(DateTime, default=datetime.utcnow)
    status = Column(String, default="open")
    updated_at = Column(DateTime, default=datetime.utcnow)

    audit_logs = relationship("AuditLog", back_populates="shelter")

    __table_args__ = (
        Index('idx_shelter_address', 'address'),
    )

class AuditLog(Base):
    __tablename__ = "audit_logs"
    id = Column(Integer, primary_key=True, index=True)
    shelter_id = Column(Integer, ForeignKey("shelters.id"), nullable=True)
    user       = Column(String, nullable=False)
    action     = Column(String, nullable=False)    # create/update/delete 等
    timestamp  = Column(DateTime, default=datetime.utcnow, nullable=False)
    details    = Column(Text, nullable=True)       # 変更内容の JSON/text

    shelter = relationship("Shelter", back_populates="audit_logs")
