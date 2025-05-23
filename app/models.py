
# app/models.py

from sqlalchemy import (
    Column,
    Integer,
    String,
    Float,
    Boolean,
    DateTime,
    ForeignKey,
    Text,
    Index,
    LargeBinary
)
from sqlalchemy.orm import relationship
from sqlalchemy import Column, Integer, String, DateTime, func
from datetime import datetime
from database import Base  # database.py で定義した declarative_base()

class Shelter(Base):
    __tablename__ = "shelters"

    id                = Column(Integer, primary_key=True, index=True)
    name              = Column(String, index=True, nullable=False)
    address           = Column(String, index=True, nullable=False)
    latitude          = Column(Float, nullable=False)
    longitude         = Column(Float, nullable=False)
    capacity          = Column(Integer, nullable=False)
    current_occupancy = Column(Integer, nullable=False, default=0)
    pets_allowed      = Column(Boolean, default=False)
    barrier_free      = Column(Boolean, default=False)
    toilet_available  = Column(Boolean, default=False)
    food_available    = Column(Boolean, default=False)
    medical_available = Column(Boolean, default=False)
    wifi_available    = Column(Boolean, default=False)
    charging_available= Column(Boolean, default=False)
    equipment         = Column(String, default="")
    photos            = Column(String, default="")  # URL一覧をカンマ区切りで保存
    contact           = Column(String, default="")
    operator          = Column(String, default="")
    opened_at         = Column(DateTime, default=datetime.utcnow)
    status            = Column(String, default="open")  # "open" or "closed"
    updated_at        = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    owner_id          = Column(Integer, ForeignKey("companies.id"), nullable=False)
    owner             = relationship("Company", back_populates="shelters")

    # Shelter と紐付く監査ログ
    audit_logs        = relationship("AuditLog", back_populates="shelter")

    __table_args__ = (
        Index('idx_shelter_address', 'address'),
    )


class Photo(Base):
    __tablename__ = "photos"

    id           = Column(Integer, primary_key=True, index=True)
    filename     = Column(String, nullable=False)
    content_type = Column(String, nullable=False)
    data         = Column(LargeBinary, nullable=True)  # 画像バイナリデータを格納


class AuditLog(Base):
    __tablename__ = "audit_logs"

    id         = Column(Integer, primary_key=True, index=True)
    shelter_id = Column(Integer, ForeignKey("shelters.id"), nullable=True)
    user       = Column(String, nullable=False)
    action     = Column(String, nullable=False)    # create/update/delete など
    timestamp  = Column(DateTime, default=datetime.utcnow, nullable=False)
    details    = Column(Text, nullable=True)       # 変更内容の詳細

    # AuditLog と Shelter を双方向関連付け
    shelter    = relationship("Shelter", back_populates="audit_logs")

class Company(Base):
    __tablename__ = "companies"

    id         = Column(Integer, primary_key=True, index=True)
    name       = Column(String, unique=True, nullable=False)
    email      = Column(String, unique=True, nullable=False)
    hashed_pw  = Column(String, nullable=False)
    created_at = Column(DateTime, nullable=False, server_default=func.now())

    # (必要ならば) 自社が作成した避難所とのリレーション
    shelters   = relationship("Shelter", back_populates="owner")