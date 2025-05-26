from sqlalchemy import (
    Column, Integer, String, Float, Boolean, DateTime, ForeignKey, Index, LargeBinary
)
from sqlalchemy.orm import relationship
from database import Base
from datetime import datetime

class Shelter(Base):
    __tablename__ = "shelters"
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, index=True, nullable=False)
    address = Column(String, nullable=False)
    latitude = Column(Float, nullable=False)
    longitude = Column(Float, nullable=False)
    capacity = Column(Integer, nullable=False)
    current_occupancy = Column(Integer, default=0, nullable=False)
    pets_allowed = Column(Boolean, default=False, nullable=False)
    barrier_free = Column(Boolean, default=False, nullable=False)
    toilet_available = Column(Boolean, default=False, nullable=False)
    food_available = Column(Boolean, default=False, nullable=False)
    medical_available = Column(Boolean, default=False, nullable=False)
    wifi_available = Column(Boolean, default=False, nullable=False)
    charging_available = Column(Boolean, default=False, nullable=False)
    equipment = Column(String, nullable=True)
    photos = Column(String, default="")
    contact = Column(String, nullable=True)
    operator = Column(String, nullable=False)
    opened_at = Column(DateTime, nullable=False)
    status = Column(String, default="open", nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
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
    details = Column(String, nullable=True)
    shelter = relationship("Shelter", back_populates="audit_logs")

class Company(Base):
    __tablename__ = "companies"
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, unique=True, nullable=False)
    email = Column(String, unique=True, nullable=False)
    hashed_pw = Column(String, nullable=False)
    role = Column(String, default="company", nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)