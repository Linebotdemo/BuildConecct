from sqlalchemy import (
    Column, Integer, String, Float, Boolean, DateTime, ForeignKey, Text, Index, LargeBinary
)
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from database import Base
from datetime import datetime  # 追加: datetime モジュールをインポート

class Shelter(Base):
    __tablename__ = "shelters"
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, index=True)
    address = Column(String)
    latitude = Column(Float)
    longitude = Column(Float)
    capacity = Column(Integer)
    current_occupancy = Column(Integer, default=0)
    pets_allowed = Column(Boolean, default=False)
    barrier_free = Column(Boolean, default=False)
    toilet_available = Column(Boolean, default=False)
    food_available = Column(Boolean, default=False)
    medical_available = Column(Boolean, default=False)
    wifi_available = Column(Boolean, default=False)
    charging_available = Column(Boolean, default=False)
    equipment = Column(Text)
    photos = Column(Text)
    contact = Column(String)
    operator = Column(String)
    opened_at = Column(DateTime)
    status = Column(String, default="open")
    updated_at = Column(DateTime, default=datetime.utcnow)  # datetime を使用
    company_id = Column(Integer, ForeignKey("companies.id"), nullable=True)

    audit_logs = relationship("AuditLog", back_populates="shelter")

    __table_args__ = (
        Index('idx_shelter_address', 'address'),
    )

class Photo(Base):
    __tablename__ = "photos"
    id = Column(Integer, primary_key=True, index=True)
    filename = Column(String, nullable=False)
    content_type = Column(String, nullable=False)
    data = Column(LargeBinary, nullable=True)

class AuditLog(Base):
    __tablename__ = "audit_logs"
    id = Column(Integer, primary_key=True, index=True)
    shelter_id = Column(Integer, ForeignKey("shelters.id"), nullable=True)
    user = Column(String, nullable=False)
    action = Column(String, nullable=False)
    timestamp = Column(DateTime, default=datetime.utcnow, nullable=False)
    details = Column(Text)
    shelter = relationship("Shelter", back_populates="audit_logs")

class Company(Base):
    __tablename__ = "companies"
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, unique=True, nullable=False)
    email = Column(String, unique=True, nullable=False)
    hashed_pw = Column(String, nullable=False)
    role = Column(String(50), default="company")  # "company" または "admin"
    created_at = Column(DateTime, nullable=False, server_default=func.now())