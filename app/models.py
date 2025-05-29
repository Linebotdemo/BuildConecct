from sqlalchemy import (
    Column, Integer, String, Float, Boolean, DateTime, ForeignKey, Index, LargeBinary
)
from sqlalchemy.orm import relationship
from database import Base
from datetime import datetime

class Shelter(Base):
    __tablename__ = "shelters"
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, index=True, nullable=False)  # 避難所名
    address = Column(String, nullable=False)  # 住所
    latitude = Column(Float, nullable=False)  # 緯度
    longitude = Column(Float, nullable=False)  # 経度
    capacity = Column(Integer, nullable=False)  # 定員
    current_occupancy = Column(Integer, default=0, nullable=False)  # 現在の利用人数
    pets_allowed = Column(Boolean, default=False, nullable=False)  # ペット可
    barrier_free = Column(Boolean, default=False, nullable=False)  # バリアフリー
    toilet_available = Column(Boolean, default=False, nullable=False)  # トイレ有無
    food_available = Column(Boolean, default=False, nullable=False)  # 食料提供
    medical_available = Column(Boolean, default=False, nullable=False)  # 医療対応
    wifi_available = Column(Boolean, default=False, nullable=False)  # Wi-Fi有無
    charging_available = Column(Boolean, default=False, nullable=False)  # 充電設備
    equipment = Column(String, nullable=True)  # その他の設備（自由記述）
    photos = Column(String, default="", nullable=True)  # 旧画像パス（互換性用、将来的に削除推奨）
    contact = Column(String, nullable=True)  # 連絡先
    operator = Column(String, nullable=False)  # 運営団体
    opened_at = Column(DateTime, nullable=False)  # 開設日時
    status = Column(String, default="open", nullable=False)  # 状態（open/closed）
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)  # 更新日時
    company_id = Column(Integer, ForeignKey("companies.id"), nullable=True)  # 運営企業ID

    # 関連
    audit_logs = relationship("AuditLog", back_populates="shelter")
    photos_rel = relationship("Photo", secondary="shelter_photos", back_populates="shelters")

    __table_args__ = (
        Index('idx_shelter_address', 'address'),  # 住所検索用インデックス
        Index('idx_shelter_location', 'latitude', 'longitude'),  # 位置検索用インデックス
    )

class Photo(Base):
    __tablename__ = "photos"
    id = Column(Integer, primary_key=True, index=True)
    filename = Column(String, nullable=False)  # ファイル名（例：image.jpg）
    content_type = Column(String, nullable=False)  # MIMEタイプ（例：image/jpeg）
    data = Column(LargeBinary, nullable=False)  # 画像バイナリデータ

    # 関連
    shelters = relationship("Shelter", secondary="shelter_photos", back_populates="photos_rel")

class ShelterPhoto(Base):
    __tablename__ = "shelter_photos"
    shelter_id = Column(Integer, ForeignKey("shelters.id"), primary_key=True)
    photo_id = Column(Integer, ForeignKey("photos.id"), primary_key=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)  # 関連付け日時

    __table_args__ = (
        Index('idx_shelter_photo', 'shelter_id', 'photo_id'),
    )

class AuditLog(Base):
    __tablename__ = "audit_logs"
    id = Column(Integer, primary_key=True, index=True)
    shelter_id = Column(Integer, ForeignKey("shelters.id"), nullable=True)  # 関連避難所
    user = Column(String, nullable=False)  # 操作ユーザー（例：メールアドレス）
    action = Column(String, nullable=False)  # 操作内容（例：create, update）
    timestamp = Column(DateTime, default=datetime.utcnow, nullable=False)  # 操作日時
    details = Column(String, nullable=True)  # 詳細（例：JSON形式の変更内容）

    # 関連
    shelter = relationship("Shelter", back_populates="audit_logs")

class Company(Base):
    __tablename__ = "companies"
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, unique=True, nullable=False)  # 企業名
    email = Column(String, unique=True, nullable=False)  # メールアドレス
    hashed_pw = Column(String, nullable=False)  # ハッシュ化されたパスワード
    role = Column(String, default="company", nullable=False)  # ロール（例：company, admin）
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)  # 登録日時