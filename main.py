from dotenv import load_dotenv
load_dotenv()

import os
import sys
import uuid
import tempfile
import datetime
import asyncio
import logging
import json
import textwrap
from datetime import datetime as dt, date, timezone
from typing import Optional, List
from fastapi.middleware.cors import CORSMiddleware

# FastAPI 関連
from fastapi import FastAPI, Depends, HTTPException, Form, WebSocket, WebSocketDisconnect, Request, APIRouter
from fastapi.responses import JSONResponse, RedirectResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from fastapi.exceptions import RequestValidationError
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.types import ASGIApp

# SQLAlchemy 関連
from sqlalchemy import create_engine, Column, Integer, String, Float, Text, Boolean, Date, DateTime, ForeignKey
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, relationship, Session, joinedload

# Pydantic
from pydantic import BaseModel, validator

# JWT, Passlib
from jose import JWTError, jwt
from passlib.context import CryptContext

# LINE Bot 関連
from linebot import LineBotApi, WebhookParser
from linebot.exceptions import InvalidSignatureError
from linebot.models import (
    MessageEvent, TextMessage, ImageMessage, AudioMessage, TextSendMessage,
    QuickReply, QuickReplyButton, MessageAction
)
import openai

# --- カスタムミドルウェア ---
class CacheControlMiddleware(BaseHTTPMiddleware):
    def __init__(self, app: ASGIApp):
        super().__init__(app)
    async def dispatch(self, request, call_next):
        response = await call_next(request)
        if request.url.path.startswith("/static") or request.url.path.startswith("/files"):
            response.headers["Cache-Control"] = "no-store"
        return response

# --- Configuration ---
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./test.db")
ADMIN_API_KEY = os.getenv("ADMIN_API_KEY", "default_admin_api_key")
JWT_SECRET = os.getenv("JWT_SECRET", "your_super_secret_key_here")
JWT_ALGORITHM = os.getenv("JWT_ALGORITHM", "HS256")
DEBUG = os.getenv("DEBUG", "True") == "True"

LINE_CHANNEL_ACCESS_TOKEN = os.getenv("LINE_CHANNEL_ACCESS_TOKEN")
LINE_CHANNEL_SECRET = os.getenv("LINE_CHANNEL_SECRET")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

line_api = LineBotApi(LINE_CHANNEL_ACCESS_TOKEN)
parser = WebhookParser(LINE_CHANNEL_SECRET)
openai.api_key = OPENAI_API_KEY

# JST のタイムゾーン設定
JST = timezone(datetime.timedelta(hours=+9))

# --- Logging Setup ---
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

# --- Database Setup ---
if DATABASE_URL.startswith("sqlite"):
    engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False}, echo=DEBUG)
else:
    engine = create_engine(DATABASE_URL, echo=DEBUG)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

# --- Models (SQLAlchemy) ---
class Company(Base):
    __tablename__ = "companies"
    id = Column(Integer, primary_key=True, index=True)
    company_name = Column(String, unique=True, nullable=False)
    company_code = Column(String, unique=True, nullable=False)
    api_key = Column(String, unique=True, nullable=False)
    users = relationship("User", back_populates="company", cascade="all, delete-orphan")
    projects = relationship("Project", back_populates="company", cascade="all, delete-orphan")
    reports = relationship("Report", back_populates="company", cascade="all, delete-orphan")
    schedule_items = relationship("ScheduleItem", back_populates="company", cascade="all, delete-orphan")
    orders = relationship("Order", back_populates="company", cascade="all, delete-orphan")
    inventories = relationship("Inventory", back_populates="company", cascade="all, delete-orphan")
    blueprints = relationship("Blueprint", back_populates="company", cascade="all, delete-orphan")
    materials = relationship("Material", back_populates="company", cascade="all, delete-orphan")
    employees = relationship("Employee", back_populates="company", cascade="all, delete-orphan")

class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True, index=True)
    email = Column(String, unique=True, nullable=False, index=True)
    hashed_password = Column(String, nullable=False)
    role = Column(String, default="user")
    active = Column(Boolean, default=True)
    company_id = Column(Integer, ForeignKey("companies.id"), nullable=True)
    company = relationship("Company", back_populates="users")

class Project(Base):
    __tablename__ = "projects"
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False)
    location = Column(String)
    building_type = Column(String)
    ground_floors = Column(Integer)
    basement_floors = Column(Integer)
    total_floor_area = Column(Float)
    start_date = Column(Date)
    end_date = Column(Date)
    project_manager = Column(String)
    ai_plan = Column(Text)
    progress = Column(Float, default=0.0)
    company_id = Column(Integer, ForeignKey("companies.id"), nullable=False)
    company = relationship("Company", back_populates="projects")
    reports = relationship("Report", back_populates="project", cascade="all, delete-orphan")
    schedule_items = relationship("ScheduleItem", back_populates="project", cascade="all, delete-orphan")
    orders = relationship("Order", back_populates="project", cascade="all, delete-orphan")
    inventories = relationship("Inventory", back_populates="project", cascade="all, delete-orphan")
    blueprints = relationship("Blueprint", back_populates="project", cascade="all, delete-orphan")

class Report(Base):
    __tablename__ = "reports"
    id = Column(Integer, primary_key=True, index=True)
    project_id = Column(Integer, ForeignKey("projects.id"), nullable=False)
    report_text = Column(Text, nullable=False)
    photo_url = Column(String, nullable=True)
    audio_url = Column(String, nullable=True)
    status = Column(String, default="pending")
    reporter = Column(String, nullable=True)
    company_id = Column(Integer, ForeignKey("companies.id"), nullable=False)
    created_at = Column(DateTime, default=lambda: dt.now(timezone.utc).astimezone(JST), nullable=False)
    company = relationship("Company", back_populates="reports")
    project = relationship("Project", back_populates="reports")

class ScheduleItem(Base):
    __tablename__ = "schedule_items"
    id = Column(Integer, primary_key=True, index=True)
    project_id = Column(Integer, ForeignKey("projects.id"), nullable=False)
    task = Column(String, nullable=False)
    assignee = Column(String, nullable=True)
    start_time = Column(DateTime, nullable=False)
    end_time = Column(DateTime, nullable=False)
    status = Column(String, default="not_started")
    company_id = Column(Integer, ForeignKey("companies.id"), nullable=False)
    project = relationship("Project", back_populates="schedule_items")
    company = relationship("Company", back_populates="schedule_items")

class Order(Base):
    __tablename__ = "orders"
    id = Column(Integer, primary_key=True, index=True)
    order_number = Column(String, nullable=False)
    project_id = Column(Integer, ForeignKey("projects.id"), nullable=False)
    material = Column(String, nullable=False)
    quantity = Column(Integer, nullable=False)
    order_status = Column(String, default="pending")
    surplus = Column(Boolean, default=False)
    storage = Column(String, nullable=True)
    order_date = Column(Date, nullable=True)
    delivery_date = Column(Date, nullable=True)
    supplier_name = Column(String, nullable=True)
    price = Column(Float, nullable=True)
    total_price = Column(Float, nullable=True)
    updated_by = Column(String, nullable=True)
    company_id = Column(Integer, ForeignKey("companies.id"), nullable=False)
    project = relationship("Project", back_populates="orders")
    company = relationship("Company", back_populates="orders")

class Inventory(Base):
    __tablename__ = "inventory"
    id = Column(Integer, primary_key=True, index=True)
    material_name = Column(String, nullable=False)
    quantity = Column(Integer, default=0)
    location = Column(String, nullable=True)
    project_id = Column(Integer, ForeignKey("projects.id"), nullable=False)
    company_id = Column(Integer, ForeignKey("companies.id"), nullable=False)
    last_updated = Column(DateTime, nullable=True)
    updated_by = Column(String, nullable=True)
    project = relationship("Project", back_populates="inventories")
    company = relationship("Company", back_populates="inventories")
    history = relationship("InventoryHistory", back_populates="inventory", cascade="all, delete-orphan")

class InventoryHistory(Base):
    __tablename__ = "inventory_history"
    id = Column(Integer, primary_key=True, index=True)
    inventory_id = Column(Integer, ForeignKey("inventory.id"), nullable=False)
    updated_at = Column(DateTime, default=lambda: dt.now(timezone.utc).astimezone(JST))
    updated_by = Column(String, nullable=True)
    change_data = Column(Text, nullable=True)
    inventory = relationship("Inventory", back_populates="history")

class Blueprint(Base):
    __tablename__ = "blueprints"
    id = Column(Integer, primary_key=True, index=True)
    project_id = Column(Integer, ForeignKey("projects.id"), nullable=False)
    name = Column(String, nullable=False)
    filename = Column(String, nullable=False)
    file_path = Column(String, nullable=False)
    version = Column(String, nullable=True)
    created_at = Column(DateTime, default=lambda: dt.now(timezone.utc).astimezone(JST), nullable=False)
    company_id = Column(Integer, ForeignKey("companies.id"), nullable=False)
    project = relationship("Project", back_populates="blueprints")
    company = relationship("Company", back_populates="blueprints")

class Material(Base):
    __tablename__ = "materials"
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False)
    price = Column(Float, nullable=False)
    supplier_name = Column(String, nullable=False)
    minimum_stock = Column(Integer, nullable=False)
    company_id = Column(Integer, ForeignKey("companies.id"), nullable=True)
    company = relationship("Company", back_populates="materials")

class Employee(Base):
    __tablename__ = "employees"
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False)
    qualifications = Column(String, nullable=True)
    company_id = Column(Integer, ForeignKey("companies.id"), nullable=True)
    company = relationship("Company", back_populates="employees")

class LineUser(Base):
    __tablename__ = "line_users"
    id = Column(Integer, primary_key=True, index=True)
    line_user_id = Column(String, unique=True, nullable=False)
    line_user_name = Column(String, nullable=True)
    company_code = Column(String, nullable=True)
    project_id = Column(Integer, nullable=True)
    registered = Column(Boolean, default=False)
    current_state = Column(String, nullable=True)
    temp_company_code = Column(String, nullable=True)
    temp_project_id = Column(Integer, nullable=True)

class History(Base):
    __tablename__ = "history"
    __table_args__ = {'extend_existing': True}
    id = Column(Integer, primary_key=True, index=True)
    action = Column(String, nullable=False)
    details = Column(Text, nullable=True)
    timestamp = Column(DateTime, default=lambda: dt.now(timezone.utc).astimezone(JST), nullable=False)

# テーブル作成
Base.metadata.create_all(bind=engine)

# --- Schemas (Pydantic) ---
class HistorySchema(BaseModel):
    id: Optional[int]
    action: str
    details: Optional[str] = None
    timestamp: Optional[dt] = None
    class Config:
        orm_mode = True

class CompanyBaseSchema(BaseModel):
    company_name: str
class CompanyCreateSchema(CompanyBaseSchema):
    company_code: Optional[str] = None
class CompanyOutSchema(CompanyBaseSchema):
    id: int
    company_code: str
    api_key: str
    class Config:
        from_attributes = True

class UserBaseSchema(BaseModel):
    email: str
    role: Optional[str] = "user"
    active: bool = True
class UserCreateSchema(UserBaseSchema):
    password: str
    company_id: Optional[int] = None
class UserOutSchema(UserBaseSchema):
    id: int
    company_id: Optional[int]
    class Config:
        from_attributes = True
class UserUpdateSchema(BaseModel):
    email: Optional[str] = None
    role: Optional[str] = None
    active: Optional[bool] = None
    company_id: Optional[int] = None
    password: Optional[str] = None
    class Config:
        from_attributes = True

class ProjectBaseSchema(BaseModel):
    name: str
    location: Optional[str] = None
    building_type: Optional[str] = None
    ground_floors: Optional[int] = None
    basement_floors: Optional[int] = None
    total_floor_area: Optional[float] = None
    project_manager: Optional[str] = None
class ProjectCreateSchema(ProjectBaseSchema):
    start_date: Optional[date] = None
    end_date: Optional[date] = None
class ProjectSchema(ProjectBaseSchema):
    id: int
    start_date: Optional[date] = None
    end_date: Optional[date] = None
    ai_plan: Optional[str] = None
    progress: Optional[float] = 0.0
    class Config:
        from_attributes = True

class ReportBaseSchema(BaseModel):
    project_id: int
    report_text: str
    photo_url: Optional[str] = None
    audio_url: Optional[str] = None
class ReportCreateSchema(ReportBaseSchema):
    status: str = "pending"
class ReportUpdateSchema(BaseModel):
    report_text: Optional[str] = None
    photo_url: Optional[str] = None
    audio_url: Optional[str] = None
    status: Optional[str] = None
    reporter: Optional[str] = None
    class Config:
        from_attributes = True
class ReportOutSchema(BaseModel):
    id: int
    project_id: int
    project_name: Optional[str] = None
    report_text: str
    photo_url: Optional[str] = None
    audio_url: Optional[str] = None
    status: str
    reporter: Optional[str] = None
    created_at: dt
    class Config:
        from_attributes = True
    @validator('created_at', pre=True, always=True)
    def convert_created_at_to_jst(cls, v):
        if v is None:
            return v
        if v.tzinfo is None:
            v = v.replace(tzinfo=timezone.utc)
        return v.astimezone(JST)

class ScheduleItemBaseSchema(BaseModel):
    project_id: int
    task: str
    assignee: Optional[str] = None
    start_time: dt
    end_time: dt
class ScheduleItemCreateSchema(ScheduleItemBaseSchema):
    status: str = "not_started"
class ScheduleItemSchema(ScheduleItemBaseSchema):
    id: int
    status: str
    class Config:
        from_attributes = True

class OrderBaseSchema(BaseModel):
    project_id: int
    order_number: Optional[str] = None
    material: str
    quantity: int
    storage: Optional[str] = None
    order_date: Optional[date] = None
    delivery_date: Optional[date] = None
    supplier_name: Optional[str] = None
    price: Optional[float] = None
    total_price: Optional[float] = None
    updated_by: Optional[str] = None
class OrderCreateSchema(OrderBaseSchema):
    order_status: str = "pending"
    surplus: bool = False
class OrderSchema(OrderBaseSchema):
    id: int
    order_status: str
    surplus: bool
    class Config:
        from_attributes = True

class InventoryBaseSchema(BaseModel):
    material_name: str
    quantity: int
    location: Optional[str] = None
    project_id: int
class InventoryCreateSchema(InventoryBaseSchema):
    pass
class InventorySchema(InventoryBaseSchema):
    id: int
    last_updated: Optional[dt] = None
    updated_by: Optional[str] = None
    class Config:
        from_attributes = True
class InventoryUpdateSchema(BaseModel):
    material_name: Optional[str] = None
    quantity: Optional[int] = None
    location: Optional[str] = None
    project_id: Optional[int] = None
    last_updated: Optional[dt] = None
    updated_by: Optional[str] = None
    class Config:
        from_attributes = True
class InventoryHistorySchema(BaseModel):
    id: int
    inventory_id: int
    updated_at: dt
    updated_by: Optional[str] = None
    change_data: Optional[str] = None
    class Config:
        from_attributes = True

class BlueprintBaseSchema(BaseModel):
    project_id: int
    name: str
    filename: str
    file_path: str
    version: Optional[str] = None
class BlueprintCreateSchema(BlueprintBaseSchema):
    pass
class BlueprintOutSchema(BlueprintBaseSchema):
    id: int
    created_at: dt
    company_id: int
    class Config:
        from_attributes = True

class MaterialBaseSchema(BaseModel):
    name: str
    price: float
    supplier_name: str
    minimum_stock: int
class MaterialCreateSchema(MaterialBaseSchema):
    company_id: Optional[int] = None
class MaterialSchema(MaterialBaseSchema):
    id: int
    company_id: Optional[int]
    class Config:
        from_attributes = True

class EmployeeBaseSchema(BaseModel):
    name: str
    qualifications: Optional[str] = None
class EmployeeCreateSchema(EmployeeBaseSchema):
    company_id: Optional[int] = None
class EmployeeSchema(EmployeeBaseSchema):
    id: int
    company_id: Optional[int]
    class Config:
        from_attributes = True

class LineUserBaseSchema(BaseModel):
    line_user_id: str
    line_user_name: Optional[str] = None
    company_code: Optional[str] = None
    project_id: Optional[int] = None
    registered: bool = False
    current_state: Optional[str] = None
class LineUserCreateSchema(LineUserBaseSchema):
    pass
class LineUserSchema(LineUserBaseSchema):
    id: int
    class Config:
        from_attributes = True

# --- Auth (Passlib, JWT) ---
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="token")
def verify_password(plain_password: str, hashed_password: str) -> bool:
    return pwd_context.verify(plain_password, hashed_password)
def get_password_hash(password: str) -> str:
    hashed = pwd_context.hash(password)
    logger.debug("Generated hash: %r", hashed)
    return hashed
ACCESS_TOKEN_EXPIRE_MINUTES = 180  # 3 hours
def create_access_token(data: dict, expires_delta: Optional[datetime.timedelta] = None):
    to_encode = data.copy()
    if expires_delta:
        expire = dt.now(timezone.utc) + expires_delta
    else:
        expire = dt.now(timezone.utc) + datetime.timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, JWT_SECRET, algorithm=JWT_ALGORITHM)
    logger.debug("JWT generated with expiration=%s", expire)
    return encoded_jwt
async def get_current_user(token: str = Depends(oauth2_scheme)):
    credentials_exception = HTTPException(
        status_code=401,
        detail="トークンの検証に失敗しました (期限切れなど)",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
        email: str = payload.get("sub")
        company_id = payload.get("company_id")
        role = payload.get("role")
        company_code = payload.get("company_code")
        if email is None:
            raise credentials_exception
        token_data = {"email": email, "company_id": company_id, "role": role, "company_code": company_code}
    except JWTError as e:
        logger.debug("JWT decoding error: %s", e)
        raise credentials_exception
    if token_data["email"] == "admin":
        return {"username": token_data["email"], "company_id": token_data["company_id"], "role": token_data["role"], "company_code": token_data["company_code"]}
    if token_data["role"] == "admin" and token_data["company_id"] is not None:
        return {"username": token_data["email"], "company_id": token_data["company_id"], "role": token_data["role"], "company_code": token_data["company_code"]}
    db = SessionLocal()
    try:
        user = db.query(User).filter(User.email == token_data["email"]).first()
        if not user:
            logger.debug("User not found for token email: %s", token_data["email"])
            raise credentials_exception
        company = db.query(Company).filter(Company.id == user.company_id).first()
        return {"username": user.email, "company_id": user.company_id, "role": user.role, "company_code": company.company_code if company else None}
    finally:
        db.close()

# --- CRUD Functions (統合版) ---
def get_company_by_code(db: Session, company_code: str) -> Optional[Company]:
    return db.query(Company).filter(Company.company_code == company_code).first()

def get_project(db: Session, project_id: int, company_id: Optional[int] = None) -> Optional[Project]:
    query = db.query(Project).filter(Project.id == project_id)
    if company_id is not None:
        query = query.filter(Project.company_id == company_id)
    return query.first()

def get_projects(db: Session, skip: int = 0, limit: int = 100, company_id: Optional[int] = None) -> List[Project]:
    query = db.query(Project)
    if company_id is not None:
        query = query.filter(Project.company_id == company_id)
    return query.offset(skip).limit(limit).all()

def create_project(db: Session, project_data: dict) -> Project:
    db_project = Project(**project_data)
    db.add(db_project)
    db.commit()
    db.refresh(db_project)
    return db_project

def update_project(db: Session, project_id: int, project_update: dict, company_id: Optional[int] = None) -> Optional[Project]:
    project = get_project(db, project_id, company_id)
    if not project:
        return None
    for key, value in project_update.items():
        setattr(project, key, value)
    db.commit()
    db.refresh(project)
    return project

def delete_project(db: Session, project_id: int, company_id: Optional[int] = None) -> bool:
    project = get_project(db, project_id, company_id)
    if project:
        db.delete(project)
        db.commit()
        return True
    return False

def get_report(db: Session, report_id: int, company_id: Optional[int] = None) -> Optional[Report]:
    query = db.query(Report).filter(Report.id == report_id)
    if company_id is not None:
        query = query.filter(Report.company_id == company_id)
    return query.first()

def get_reports(db: Session, skip: int = 0, limit: int = 100, status: Optional[str] = None,
                search: Optional[str] = None, company_id: Optional[int] = None, project_id: Optional[int] = None) -> List[Report]:
    query = db.query(Report)
    if company_id is not None:
        query = query.filter(Report.company_id == company_id)
    if project_id is not None:
        query = query.filter(Report.project_id == project_id)
    if status:
        query = query.filter(Report.status == status)
    if search:
        query = query.filter(Report.report_text.contains(search))
    return query.offset(skip).limit(limit).all()

def create_report(db: Session, report_data: dict) -> Report:
    db_report = Report(**report_data)
    db.add(db_report)
    db.commit()
    db.refresh(db_report)
    return db_report

def update_report(db: Session, report_id: int, report_update: dict, company_id: Optional[int] = None) -> Optional[Report]:
    report = get_report(db, report_id, company_id)
    if not report:
        return None
    for key, value in report_update.items():
        setattr(report, key, value)
    db.commit()
    db.refresh(report)
    return report

def delete_report(db: Session, report_id: int, company_id: Optional[int] = None) -> bool:
    report = get_report(db, report_id, company_id)
    if report:
        db.delete(report)
        db.commit()
        return True
    return False

def get_schedule_item(db: Session, item_id: int, company_id: Optional[int] = None) -> Optional[ScheduleItem]:
    query = db.query(ScheduleItem).filter(ScheduleItem.id == item_id)
    if company_id is not None:
        query = query.filter(ScheduleItem.company_id == company_id)
    return query.first()

def get_schedule_items(db: Session, skip: int = 0, limit: int = 100, status: Optional[str] = None,
                       project_id: Optional[int] = None, company_id: Optional[int] = None) -> List[ScheduleItem]:
    query = db.query(ScheduleItem)
    if company_id is not None:
        query = query.filter(ScheduleItem.company_id == company_id)
    if project_id:
        query = query.filter(ScheduleItem.project_id == project_id)
    if status:
        query = query.filter(ScheduleItem.status == status)
    return query.offset(skip).limit(limit).all()

def create_schedule_item(db: Session, item_data: dict) -> ScheduleItem:
    db_item = ScheduleItem(**item_data)
    db.add(db_item)
    db.commit()
    db.refresh(db_item)
    return db_item

def update_schedule_item(db: Session, item_id: int, item_update: dict, company_id: Optional[int] = None) -> Optional[ScheduleItem]:
    item = get_schedule_item(db, item_id, company_id)
    if not item:
        return None
    for key, value in item_update.items():
        setattr(item, key, value)
    db.commit()
    db.refresh(item)
    return item

def delete_schedule_item(db: Session, item_id: int, company_id: Optional[int] = None) -> bool:
    item = get_schedule_item(db, item_id, company_id)
    if item:
        db.delete(item)
        db.commit()
        return True
    return False

def get_order(db: Session, order_id: int, company_id: Optional[int] = None) -> Optional[Order]:
    query = db.query(Order).filter(Order.id == order_id)
    if company_id is not None:
        query = query.filter(Order.company_id == company_id)
    return query.first()

def get_orders(db: Session, skip: int = 0, limit: int = 100, company_id: Optional[int] = None) -> List[Order]:
    query = db.query(Order)
    if company_id is not None:
        query = query.filter(Order.company_id == company_id)
    return query.offset(skip).limit(limit).all()

def create_order(db: Session, order_data: dict) -> Order:
    if "price" in order_data and "quantity" in order_data:
        try:
            order_data["total_price"] = float(order_data["price"]) * int(order_data["quantity"])
        except Exception:
            order_data["total_price"] = None
    db_order = Order(**order_data)
    db.add(db_order)
    db.commit()
    db.refresh(db_order)
    return db_order

def update_order(db: Session, order_id: int, order_update: dict, company_id: Optional[int] = None) -> Optional[Order]:
    order = get_order(db, order_id, company_id)
    if not order:
        return None
    old_status = order.order_status
    for key, value in order_update.items():
        setattr(order, key, value)
    db.commit()
    db.refresh(order)
    if old_status == "ordered" and order.order_status == "received":
        update_inventory_for_order(db, order)
    return order

def delete_order(db: Session, order_id: int, company_id: Optional[int] = None) -> bool:
    order = get_order(db, order_id, company_id)
    if order:
        db.delete(order)
        db.commit()
        return True
    return False

def get_inventory_by_material_and_project(db: Session, material_name: str, project_id: int, company_id: Optional[int] = None) -> Optional[Inventory]:
    query = db.query(Inventory).filter(
        Inventory.material_name == material_name,
        Inventory.project_id == project_id
    )
    if company_id is not None:
        query = query.filter(Inventory.company_id == company_id)
    return query.first()

def update_inventory_for_order(db: Session, order: Order):
    inventory = get_inventory_by_material_and_project(db, order.material, order.project_id, order.company_id)
    if inventory:
        inventory.quantity += order.quantity
        inventory.updated_by = "system"
        inventory.last_updated = datetime.datetime.utcnow()
        db.commit()
    else:
        create_inventory(db, {
            "project_id": order.project_id,
            "material_name": order.material,
            "location": order.storage,
            "quantity": order.quantity,
            "updated_by": "system",
            "last_updated": datetime.datetime.utcnow(),
            "company_id": order.company_id
        })

def get_inventory(db: Session, inventory_id: int, company_id: Optional[int] = None) -> Optional[Inventory]:
    query = db.query(Inventory).filter(Inventory.id == inventory_id)
    if company_id is not None:
        query = query.filter(Inventory.company_id == company_id)
    return query.first()

def get_inventories(db: Session, skip: int = 0, limit: int = 100, search: Optional[str] = None,
                    project_id: Optional[int] = None, company_id: Optional[int] = None,
                    sort: Optional[str] = None) -> List[Inventory]:
    query = db.query(Inventory)
    if company_id is not None:
        query = query.filter(Inventory.company_id == company_id)
    if search:
        query = query.filter(Inventory.material_name.contains(search))
    if project_id:
        query = query.filter(Inventory.project_id == project_id)
    if sort:
        if sort == "id_asc":
            query = query.order_by(Inventory.id.asc())
        elif sort == "id_desc":
            query = query.order_by(Inventory.id.desc())
        elif sort == "quantity_asc":
            query = query.order_by(Inventory.quantity.asc())
        elif sort == "quantity_desc":
            query = query.order_by(Inventory.quantity.desc())
        else:
            query = query.order_by(Inventory.id.desc())
    else:
        query = query.order_by(Inventory.id.desc())
    return query.offset(skip).limit(limit).all()

def create_inventory(db: Session, inventory_data: dict) -> Inventory:
    db_inv = Inventory(**inventory_data)
    db.add(db_inv)
    db.commit()
    db.refresh(db_inv)
    return db_inv

def generate_order_number() -> str:
    ts = dt.now(JST).strftime("%y%m%d%H%M%S")
    suffix = str(uuid.uuid4())[:4]
    return f"ORD{ts}{suffix}"


def update_inventory(db: Session, inventory_id: int, inv_update: dict,
                     company_id: Optional[int] = None) -> Optional[Inventory]:
    inv = get_inventory(db, inventory_id, company_id)
    if not inv:
        return None
    for key, value in inv_update.items():
        setattr(inv, key, value)
    inv.last_updated = dt.now(timezone.utc).astimezone(JST)
    db.commit()
    db.refresh(inv)
    return inv

def delete_inventory(db: Session, inventory_id: int, company_id: Optional[int] = None) -> bool:
    inv = get_inventory(db, inventory_id, company_id)
    if inv:
        db.delete(inv)
        db.commit()
        return True
    return False

def create_inventory_history(db: Session, history_data: dict) -> InventoryHistory:
    db_history = InventoryHistory(**history_data)
    db.add(db_history)
    db.commit()
    db.refresh(db_history)
    return db_history

def get_inventory_history(db: Session, inventory_id: int, skip: int = 0, limit: int = 100,
                          sort: Optional[str] = None) -> List[InventoryHistory]:
    query = db.query(InventoryHistory).filter(InventoryHistory.inventory_id == inventory_id)
    if sort == "updated_at_asc":
        query = query.order_by(InventoryHistory.updated_at.asc())
    else:
        query = query.order_by(InventoryHistory.updated_at.desc())
    return query.offset(skip).limit(limit).all()

def get_blueprints(db: Session, skip: int = 0, limit: int = 100, company_id: Optional[int] = None,
                   project_id: Optional[int] = None) -> List[Blueprint]:
    query = db.query(Blueprint)
    if company_id is not None:
        query = query.filter(Blueprint.company_id == company_id)
    if project_id:
        query = query.filter(Blueprint.project_id == project_id)
    return query.offset(skip).limit(limit).all()

def create_blueprint(db: Session, blueprint_data: dict) -> Blueprint:
    db_bp = Blueprint(**blueprint_data)
    db.add(db_bp)
    db.commit()
    db.refresh(db_bp)
    return db_bp

def delete_blueprint(db: Session, blueprint_id: int, company_id: Optional[int] = None) -> bool:
    bp = db.query(Blueprint).filter(Blueprint.id == blueprint_id)
    if company_id is not None:
        bp = bp.filter(Blueprint.company_id == company_id)
    bp = bp.first()
    if bp:
        db.delete(bp)
        db.commit()
        return True
    return False

def get_materials(db: Session, skip: int = 0, limit: int = 100, company_id: Optional[int] = None) -> List[Material]:
    query = db.query(Material)
    if company_id is not None:
        query = query.filter(Material.company_id == company_id)
    return query.offset(skip).limit(limit).all()

def create_material(db: Session, material_data: dict) -> Material:
    db_mat = Material(**material_data)
    db.add(db_mat)
    db.commit()
    db.refresh(db_mat)
    return db_mat

def delete_material(db: Session, material_id: int, company_id: Optional[int] = None) -> bool:
    mat = db.query(Material).filter(Material.id == material_id)
    if company_id is not None:
        mat = mat.filter(Material.company_id == company_id)
    mat = mat.first()
    if mat:
        db.delete(mat)
        db.commit()
        return True
    return False

def get_employees(db: Session, skip: int = 0, limit: int = 100, company_id: Optional[int] = None) -> List[Employee]:
    query = db.query(Employee)
    if company_id is not None:
        query = query.filter(Employee.company_id == company_id)
    return query.offset(skip).limit(limit).all()

def create_employee(db: Session, employee_data: dict) -> Employee:
    db_emp = Employee(**employee_data)
    db.add(db_emp)
    db.commit()
    db.refresh(db_emp)
    return db_emp

def delete_employee(db: Session, employee_id: int, company_id: Optional[int] = None) -> bool:
    emp = db.query(Employee).filter(Employee.id == employee_id)
    if company_id is not None:
        emp = emp.filter(Employee.company_id == company_id)
    emp = emp.first()
    if emp:
        db.delete(emp)
        db.commit()
        return True
    return False

# --- LINE User 関連 ---
def get_line_user(db: Session, line_user_id: str) -> Optional[LineUser]:
    return db.query(LineUser).filter(LineUser.line_user_id == line_user_id).first()

def create_line_user(db: Session, line_user_id: str, user_name: str = "") -> LineUser:
    new_line_user = LineUser(
        line_user_id=line_user_id,
        line_user_name=user_name,
        registered=False
    )
    db.add(new_line_user)
    db.commit()
    db.refresh(new_line_user)
    return new_line_user

def update_line_user(db: Session, line_user: LineUser, updates: dict) -> LineUser:
    for key, value in updates.items():
        setattr(line_user, key, value)
    db.commit()
    db.refresh(line_user)
    return line_user

# --- FastAPI App Setup ---
app = FastAPI()
app.add_middleware(CacheControlMiddleware)
app.mount("/static", StaticFiles(directory="static", html=True), name="static")
app.mount("/files", StaticFiles(directory="files", html=True), name="files")

# Dependency
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

origins = [
    "https://buildconnect.onrender.com",  # ← あなたのフロントエンドURLに変更！
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=["https://buildconnect.onrender.com"],
    allow_credentials=True,
    allow_methods=["*"],           # 全メソッドを許可（GET, POST など）
    allow_headers=["*"],           # 全ヘッダーを許可
)

@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    logger.error(f"Validation error: {exc.errors()}")
    return JSONResponse(
        status_code=422,
        content={"detail": exc.errors()}
    )

# --- Endpoints ---
@app.get("/")
async def root():
    return RedirectResponse("/static/pages/admin_login.html")

# Admin Security Endpoint
@app.post("/admin-security")
async def admin_security(admin_key: str = Form(...), db: Session = Depends(get_db)):
    key = admin_key.strip()
    if not os.getenv("ADMIN_API_KEY") or not os.getenv("JWT_SECRET"):
        raise HTTPException(status_code=500, detail="Server configuration error")
    if key == os.getenv("ADMIN_API_KEY").strip():
        token = create_access_token({"sub": "admin", "company_id": None, "role": "admin", "company_code": None})
        return JSONResponse(content={
            "access_token": token,
            "token_type": "bearer",
            "redirect_url": "/static/pages/admin_dashboard.html"
        })
    company = db.query(Company).filter(Company.api_key == key).first()
    if company:
        token = create_access_token({"sub": company.company_name, "company_id": company.id, "role": "admin", "company_code": company.company_code})
        return JSONResponse(content={
            "access_token": token,
            "token_type": "bearer",
            "redirect_url": "/static/pages/project_management.html"
        })
    raise HTTPException(status_code=401, detail="無効な管理者APIキーです")

# Token Endpoint
@app.post("/token")
async def token(form_data: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_db)):
    user = db.query(User).filter(User.email == form_data.username).first()
    if not user or not verify_password(form_data.password, user.hashed_password):
        raise HTTPException(status_code=401, detail="メールアドレスまたはパスワードが間違っています")
    company = db.query(Company).filter(Company.id == user.company_id).first()
    access_token = create_access_token({
        "sub": user.email,
        "company_id": user.company_id,
        "role": user.role,
        "company_code": company.company_code if company else None
    })
    logger.debug(f"Token created for user: {user.email}")
    return {"access_token": access_token, "token_type": "bearer"}

# Company Endpoints
@app.get("/companies")
async def list_companies(db: Session = Depends(get_db), current_user: dict = Depends(get_current_user)):
    companies = db.query(Company).all()
    return [
        {
            "id": c.id,
            "company_name": c.company_name,
            "company_code": c.company_code,
            "api_key": c.api_key
        }
        for c in companies
    ]

@app.post("/company-registration", status_code=201)
async def create_company_endpoint(company: CompanyCreateSchema, db: Session = Depends(get_db), current_user: dict = Depends(get_current_user)):
    new_company = Company(
        company_name=company.company_name,
        company_code=str(uuid.uuid4())[:8],
        api_key=str(uuid.uuid4())
    )
    db.add(new_company)
    db.commit()
    db.refresh(new_company)
    return {"id": new_company.id, "company_code": new_company.company_code, "api_key": new_company.api_key}

# Project Endpoints
@app.get("/projects")
async def list_projects(db: Session = Depends(get_db), current_user: dict = Depends(get_current_user)):
    company_id = current_user.get("company_id")
    projects = db.query(Project).filter(Project.company_id == company_id).all()
    result = [
        {
            "id": p.id,
            "name": p.name,
            "location": p.location,
            "building_type": p.building_type,
            "ground_floors": p.ground_floors,
            "basement_floors": p.basement_floors,
            "total_floor_area": p.total_floor_area,
            "start_date": p.start_date.isoformat() if p.start_date else None,
            "end_date": p.end_date.isoformat() if p.end_date else None,
            "project_manager": p.project_manager,
            "ai_plan": p.ai_plan,
            "progress": p.progress,
            "company_id": p.company_id
        } for p in projects
    ]
    logger.debug(f"Projects returned: {result}")
    return result

@app.get("/projects/{project_id}")
async def get_project_detail(project_id: int, db: Session = Depends(get_db), current_user: dict = Depends(get_current_user)):
    company_id = current_user.get("company_id")
    project = db.query(Project).filter(Project.id == project_id, Project.company_id == company_id).first()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    return {
        "id": project.id,
        "name": project.name,
        "location": project.location,
        "building_type": project.building_type,
        "ground_floors": project.ground_floors,
        "basement_floors": project.basement_floors,
        "total_floor_area": project.total_floor_area,
        "start_date": project.start_date.isoformat() if project.start_date else None,
        "end_date": project.end_date.isoformat() if project.end_date else None,
        "project_manager": project.project_manager,
        "ai_plan": project.ai_plan,
        "progress": project.progress,
        "company_id": project.company_id
    }

@app.post("/projects", status_code=201)
async def create_project_endpoint(project: ProjectCreateSchema, db: Session = Depends(get_db), current_user: dict = Depends(get_current_user)):
    project_data = project.dict()
    project_data["company_id"] = current_user.get("company_id")
    new_project = create_project(db, project_data)
    return {"id": new_project.id, "name": new_project.name}

@app.put("/projects/{project_id}")
async def update_project_endpoint(project_id: int, project_update: ProjectCreateSchema, db: Session = Depends(get_db), current_user: dict = Depends(get_current_user)):
    updated = update_project(db, project_id, project_update.dict(), current_user.get("company_id"))
    if not updated:
        raise HTTPException(status_code=404, detail="Project not found")
    return {"id": updated.id, "name": updated.name}

@app.delete("/projects/{project_id}")
async def delete_project_endpoint(project_id: int, db: Session = Depends(get_db), current_user: dict = Depends(get_current_user)):
    success = delete_project(db, project_id, current_user.get("company_id"))
    if not success:
        raise HTTPException(status_code=404, detail="Project not found")
    return {"detail": "Deleted"}

# Report Endpoints
@app.get("/reports")
async def list_reports(project_id: Optional[int] = None, skip: int = 0, limit: int = 100,
                       db: Session = Depends(get_db), current_user: dict = Depends(get_current_user)):
    company_id = current_user.get("company_id")
    reports = get_reports(db, skip=skip, limit=limit, company_id=company_id, project_id=project_id)
    result = [
        {
            "id": r.id,
            "project_id": r.project_id,
            "project_name": r.project.name if r.project else None,
            "report_text": r.report_text,
            "photo_url": r.photo_url,
            "audio_url": r.audio_url,
            "status": r.status,
            "reporter": r.reporter,
            "created_at": r.created_at.isoformat()
        } for r in reports
    ]
    logger.debug(f"Reports returned: {result}")
    return result

@app.post("/reports", status_code=201)
async def create_report_endpoint(report: ReportCreateSchema, db: Session = Depends(get_db), current_user: dict = Depends(get_current_user)):
    report_data = report.dict()
    report_data["company_id"] = current_user.get("company_id")
    report_data["reporter"] = current_user.get("username")
    new_report = create_report(db, report_data)
    asyncio.create_task(report_manager.broadcast("NEW_REPORT"))
    return {
        "id": new_report.id,
        "project_id": new_report.project_id,
        "report_text": new_report.report_text,
        "photo_url": new_report.photo_url,
        "audio_url": new_report.audio_url,
        "status": new_report.status,
        "reporter": new_report.reporter,
        "created_at": new_report.created_at.isoformat()
    }

@app.put("/reports/{report_id}")
async def update_report_endpoint(report_id: int, report_update: ReportUpdateSchema, db: Session = Depends(get_db), current_user: dict = Depends(get_current_user)):
    updated = update_report(db, report_id, report_update.dict(exclude_unset=True), current_user.get("company_id"))
    if not updated:
        raise HTTPException(status_code=404, detail="Report not found")
    asyncio.create_task(report_manager.broadcast("NEW_REPORT"))
    return {
        "id": updated.id,
        "project_id": updated.project_id,
        "report_text": updated.report_text,
        "photo_url": updated.photo_url,
        "audio_url": updated.audio_url,
        "status": updated.status,
        "reporter": updated.reporter,
        "created_at": updated.created_at.isoformat()
    }

@app.delete("/reports/{report_id}")
async def delete_report_endpoint(report_id: int, db: Session = Depends(get_db), current_user: dict = Depends(get_current_user)):
    success = delete_report(db, report_id, current_user.get("company_id"))
    if not success:
        raise HTTPException(status_code=404, detail="Report not found")
    return {"detail": "Deleted"}

# Schedule Endpoints
@app.get("/schedule")
async def list_schedule(project_id: Optional[int] = None, skip: int = 0, limit: int = 100,
                        db: Session = Depends(get_db), current_user: dict = Depends(get_current_user)):
    company_id = current_user.get("company_id")
    schedule_items = get_schedule_items(db, skip=skip, limit=limit, company_id=company_id, project_id=project_id)
    result = [
        {
            "id": s.id,
            "project_id": s.project_id,
            "task": s.task,
            "assignee": s.assignee or "",
            "start_time": s.start_time.isoformat(),
            "end_time": s.end_time.isoformat(),
            "status": s.status
        } for s in schedule_items
    ]
    logger.debug(f"Schedule items returned: {result}")
    return result

@app.get("/schedule_all")
async def list_all_schedules(skip: int = 0, limit: int = 100,
                             db: Session = Depends(get_db), current_user: dict = Depends(get_current_user)):
    company_id = current_user.get("company_id")
    schedule_items = get_schedule_items(db, skip=skip, limit=limit, company_id=company_id)
    result = [
        {
            "id": s.id,
            "project_id": s.project_id,
            "task": s.task,
            "assignee": s.assignee or "",
            "start_time": s.start_time.isoformat(),
            "end_time": s.end_time.isoformat(),
            "status": s.status
        } for s in schedule_items
    ]
    logger.debug(f"All schedule items returned: {result}")
    return result

@app.get("/schedules")
async def list_schedules(project_id: Optional[int] = None, skip: int = 0, limit: int = 100,
                         db: Session = Depends(get_db), current_user: dict = Depends(get_current_user)):
    company_id = current_user.get("company_id")
    schedule_items = get_schedule_items(db, skip=skip, limit=limit, company_id=company_id, project_id=project_id)
    result = [
        {
            "id": s.id,
            "project_id": s.project_id,
            "task": s.task,
            "assignee": s.assignee or "",
            "start_time": s.start_time.isoformat(),
            "end_time": s.end_time.isoformat(),
            "status": s.status
        } for s in schedule_items
    ]
    logger.debug(f"Schedules returned: {result}")
    return result

@app.post("/schedule", status_code=201)
async def create_schedule_item_endpoint(schedule_item: ScheduleItemCreateSchema,
                                        db: Session = Depends(get_db), current_user: dict = Depends(get_current_user)):
    item_data = schedule_item.dict()
    item_data["company_id"] = current_user.get("company_id")
    new_item = create_schedule_item(db, item_data)
    return {
        "id": new_item.id,
        "project_id": new_item.project_id,
        "task": new_item.task,
        "assignee": new_item.assignee,
        "start_time": new_item.start_time.isoformat(),
        "end_time": new_item.end_time.isoformat(),
        "status": new_item.status
    }

@app.put("/schedule/{item_id}")
async def update_schedule_item_endpoint(item_id: int, item_update: ScheduleItemSchema,
                                        db: Session = Depends(get_db), current_user: dict = Depends(get_current_user)):
    updated = update_schedule_item(db, item_id, item_update.dict(exclude_unset=True), current_user.get("company_id"))
    if not updated:
        raise HTTPException(status_code=404, detail="Schedule item not found")
    return {
        "id": updated.id,
        "project_id": updated.project_id,
        "task": updated.task,
        "assignee": updated.assignee,
        "start_time": updated.start_time.isoformat(),
        "end_time": updated.end_time.isoformat(),
        "status": updated.status
    }

@app.delete("/schedule/{item_id}")
async def delete_schedule_item_endpoint(item_id: int,
                                        db: Session = Depends(get_db), current_user: dict = Depends(get_current_user)):
    success = delete_schedule_item(db, item_id, current_user.get("company_id"))
    if not success:
        raise HTTPException(status_code=404, detail="Schedule item not found")
    return {"detail": "Deleted"}

# Order Endpoints
@app.get("/orders")
async def list_orders(db: Session = Depends(get_db), current_user: dict = Depends(get_current_user)):
    company_id = current_user.get("company_id")
    orders = db.query(Order).options(joinedload(Order.project)).filter(Order.company_id == company_id).all()
    result = [
        {
            "id": o.id,
            "order_number": o.order_number or "-",
            "project_id": o.project_id,
            "project_name": o.project.name if o.project else None,
            "material": o.material,
            "quantity": o.quantity,
            "order_status": o.order_status,
            "surplus": o.surplus,
            "storage": o.storage,
            "order_date": o.order_date.isoformat() if o.order_date else None,
            "delivery_date": o.delivery_date.isoformat() if o.delivery_date else None,
            "supplier_name": o.supplier_name,
            "price": o.price,
            "total_price": o.total_price,
            "updated_by": o.updated_by
        } for o in orders
    ]
    logger.debug(f"Orders returned: {result}")
    return result

@app.post("/orders", status_code=201)
async def create_order_endpoint(order: OrderCreateSchema, db: Session = Depends(get_db), current_user: dict = Depends(get_current_user)):
    order_data = order.dict()
    order_data["company_id"] = current_user.get("company_id")
    # ← ここを追加
    order_data["order_number"] = generate_order_number()
    new_order = create_order(db, order_data)
    if new_order.order_status == "received":
        new_order.updated_by = f"注文番号:{new_order.order_number} {new_order.supplier_name} 購入分"
        update_inventory_for_order(db, new_order)
    return {
        "id": new_order.id,
        "order_number": new_order.order_number,
        "project_id": new_order.project_id,
        "project_name": new_order.project.name if new_order.project else None,
        "material": new_order.material,
        "quantity": new_order.quantity,
        "order_status": new_order.order_status,
        "surplus": new_order.surplus,
        "storage": new_order.storage,
        "order_date": new_order.order_date.isoformat() if new_order.order_date else None,
        "delivery_date": new_order.delivery_date.isoformat() if new_order.delivery_date else None,
        "supplier_name": new_order.supplier_name,
        "price": new_order.price,
        "total_price": new_order.total_price,
        "updated_by": new_order.updated_by
    }

@app.get("/debug-inventory")
def debug_inventory(db: Session = Depends(get_db)):
    inv = db.query(Inventory).order_by(Inventory.id.desc()).first()
    return {"updated_by": inv.updated_by}

@app.put("/orders/{order_id}")
async def update_order_endpoint(order_id: int, db: Session = Depends(get_db), current_user: dict = Depends(get_current_user)):
    order = db.query(Order).filter(Order.id == order_id, Order.company_id == current_user.get("company_id")).first()
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")
    order.order_status = "received"
    order.delivery_date = dt.now(timezone.utc).astimezone(JST).date()
    db.commit()
    update_inventory_for_order(db, order)
    return {"updated_by": order.updated_by}

@app.delete("/orders/{order_id}")
async def delete_order_endpoint(order_id: int, db: Session = Depends(get_db), current_user: dict = Depends(get_current_user)):
    success = delete_order(db, order_id, current_user.get("company_id"))
    if not success:
        raise HTTPException(status_code=404, detail="Order not found")
    return {"detail": "Deleted"}

# Inventory Endpoints
@app.get("/inventory")
async def list_inventory(skip: int = 0, limit: int = 15, sort: Optional[str] = None, search: Optional[str] = None,
                         project_id: Optional[int] = None, db: Session = Depends(get_db),
                         current_user: dict = Depends(get_current_user)):
    query = db.query(Inventory).options(joinedload(Inventory.project))
    if current_user.get("company_id") is not None:
        query = query.filter(Inventory.company_id == current_user.get("company_id"))
    if search:
        query = query.filter(Inventory.material_name.ilike(f"%{search}%"))
    if project_id:
        query = query.filter(Inventory.project_id == project_id)
    if sort:
        if sort == "id_asc":
            query = query.order_by(Inventory.id.asc())
        elif sort == "id_desc":
            query = query.order_by(Inventory.id.desc())
        elif sort == "quantity_asc":
            query = query.order_by(Inventory.quantity.asc())
        elif sort == "quantity_desc":
            query = query.order_by(Inventory.quantity.desc())
        else:
            query = query.order_by(Inventory.id.desc())
    else:
        query = query.order_by(Inventory.id.desc())
    items = query.offset(skip).limit(limit).all()
    result = [
        {
            "id": i.id,
            "material_name": i.material_name,
            "quantity": i.quantity,
            "location": i.location,
            "project_id": i.project_id,
            "project_name": i.project.name if i.project else "不明",
            "last_updated": i.last_updated.astimezone(JST).isoformat() if i.last_updated else None,
            "updated_by": i.updated_by
        } for i in items
    ]
    logger.debug(f"Inventory data returned: {result}")
    return result

@app.post("/inventory", status_code=201)
async def create_inventory_endpoint(inventory: InventoryCreateSchema, db: Session = Depends(get_db),
                                    current_user: dict = Depends(get_current_user)):
    inventory_data = inventory.dict()
    inventory_data["company_id"] = current_user.get("company_id")
    inventory_data["last_updated"] = dt.now(timezone.utc).astimezone(JST)
    inventory_data["updated_by"] = inventory_data.get("updated_by") or ""
    new_inv = create_inventory(db, inventory_data)
    return {
        "id": new_inv.id,
        "material_name": new_inv.material_name,
        "quantity": new_inv.quantity,
        "location": new_inv.location,
        "project_id": new_inv.project_id,
        "project_name": new_inv.project.name if new_inv.project else "不明",
        "last_updated": new_inv.last_updated.astimezone(JST).isoformat() if new_inv.last_updated else None,
        "updated_by": new_inv.updated_by
    }

@app.put("/inventory/{inventory_id}")
async def update_inventory_endpoint(inventory_id: int, inventory_update: InventoryUpdateSchema,
                                    db: Session = Depends(get_db), current_user: dict = Depends(get_current_user)):
    payload = inventory_update.dict(exclude_unset=True)
    updated = update_inventory(db, inventory_id, payload, current_user.get("company_id"))
    if not updated:
        raise HTTPException(status_code=404, detail="Inventory not found")
    if "updated_by" not in payload or not payload["updated_by"]:
        updated.updated_by = current_user.get("username") or current_user.get("email") or "Unknown"
    updated.last_updated = dt.now(timezone.utc).astimezone(JST)
    db.commit()
    db.refresh(updated)
    logger.debug(f"Updated inventory record: {updated.id}, updated_by: {updated.updated_by}")
    history_payload = {
        "inventory_id": updated.id,
        "updated_by": updated.updated_by,
        "change_data": json.dumps({
            "new": {
                "project_id": updated.project_id,
                "material_name": updated.material_name,
                "quantity": updated.quantity,
                "location": updated.location
            }
        })
    }
    try:
        created_history = create_inventory_history(db, history_payload)
        logger.debug(f"Created inventory history record: {created_history.id}")
    except Exception as e:
        logger.error(f"Failed to create inventory history: {str(e)}")
    return {
        "id": updated.id,
        "material_name": updated.material_name,
        "quantity": updated.quantity,
        "location": updated.location,
        "project_id": updated.project_id,
        "project_name": updated.project.name if updated.project else "不明",
        "last_updated": updated.last_updated.astimezone(JST).isoformat() if updated.last_updated else None,
        "updated_by": updated.updated_by
    }

@app.delete("/inventory/{inventory_id}")
async def delete_inventory_endpoint(inventory_id: int, db: Session = Depends(get_db),
                                    current_user: dict = Depends(get_current_user)):
    success = delete_inventory(db, inventory_id, current_user.get("company_id"))
    if not success:
        raise HTTPException(status_code=404, detail="Inventory not found")
    return {"detail": "Deleted"}

@app.get("/inventory/{inventory_id}/history")
async def list_inventory_history(inventory_id: int, skip: int = 0, limit: int = 15, sort: Optional[str] = None,
                                 db: Session = Depends(get_db), current_user: dict = Depends(get_current_user)):
    inventory = db.query(Inventory).filter(Inventory.id == inventory_id, Inventory.company_id == current_user.get("company_id")).first()
    if not inventory:
        raise HTTPException(status_code=404, detail="Inventory not found")
    history = get_inventory_history(db, inventory_id, skip, limit, sort)
    result = [
        {
            "id": h.id,
            "inventory_id": h.inventory_id,
            "updated_at": h.updated_at.astimezone(JST).isoformat() if h.updated_at else None,
            "updated_by": h.updated_by,
            "change_data": h.change_data
        } for h in history
    ]
    logger.debug(f"Inventory history returned: {result}")
    return result

# History Endpoint
@app.post("/history")
async def log_history_endpoint(history: HistorySchema, db: Session = Depends(get_db)):
    history_data = history.dict(exclude_unset=True)
    if "timestamp" not in history_data or history_data["timestamp"] is None:
        history_data["timestamp"] = dt.now(timezone.utc).astimezone(JST)
    new_history = History(**history_data)
    db.add(new_history)
    db.commit()
    db.refresh(new_history)
    return {"id": new_history.id, "action": new_history.action, "details": new_history.details, "timestamp": new_history.timestamp.isoformat()}

# Notifications Endpoint
@app.get("/notifications", response_model=List[ReportOutSchema])
def list_notifications(db: Session = Depends(get_db)):
    pending_reports = db.query(Report).filter(Report.status == "pending").all()
    urgent_keywords = ["遅延", "故障", "異常"]
    for r in pending_reports:
        r.is_urgent = any(kw in r.report_text for kw in urgent_keywords)
    pending_reports.sort(key=lambda r: (not getattr(r, "is_urgent", False), -r.created_at.timestamp()))
    top_reports = pending_reports[:5]
    result = []
    for r in top_reports:
        result.append({
            "id": r.id,
            "project_id": r.project_id,
            "project_name": r.project.name if r.project else None,
            "report_text": r.report_text,
            "photo_url": r.photo_url,
            "audio_url": r.audio_url,
            "status": r.status,
            "reporter": r.reporter,
            "created_at": r.created_at,
        })
    return result

# Registration Endpoints for Materials and Employees
@app.get("/registration/materials")
async def list_registration_materials(db: Session = Depends(get_db), current_user: dict = Depends(get_current_user)):
    company_id = current_user.get("company_id")
    materials_list = get_materials(db, company_id=company_id)
    result = [{"id": m.id, "name": m.name, "price": m.price, "supplier_name": m.supplier_name, "minimum_stock": m.minimum_stock} for m in materials_list]
    logger.debug(f"Materials returned: {result}")
    return result

@app.post("/registration/materials", status_code=201)
async def create_registration_material(material: MaterialCreateSchema, db: Session = Depends(get_db), current_user: dict = Depends(get_current_user)):
    material_data = material.dict()
    material_data["company_id"] = current_user.get("company_id")
    try:
        new_material = create_material(db, material_data)
        return {"id": new_material.id, "name": new_material.name, "price": new_material.price, "supplier_name": new_material.supplier_name, "minimum_stock": new_material.minimum_stock}
    except Exception as e:
        logger.error(f"Error creating material: {str(e)}")
        raise HTTPException(status_code=500, detail=f"材料の作成に失敗しました: {str(e)}")

@app.get("/registration/employees")
async def list_registration_employees(db: Session = Depends(get_db), current_user: dict = Depends(get_current_user)):
    company_id = current_user.get("company_id")
    employees_list = get_employees(db, company_id=company_id)
    result = [{"id": e.id, "name": e.name, "qualifications": e.qualifications} for e in employees_list]
    logger.debug(f"Employees returned: {result}")
    return result

@app.post("/registration/employees", status_code=201)
async def create_registration_employee(employee: EmployeeCreateSchema, db: Session = Depends(get_db), current_user: dict = Depends(get_current_user)):
    if current_user.get("role") not in ["admin", "superadmin"]:
        raise HTTPException(status_code=403, detail="権限がありません（管理者のみ）")
    employee_data = employee.dict()
    employee_data["company_id"] = current_user.get("company_id")
    new_employee = create_employee(db, employee_data)
    return {"id": new_employee.id, "name": new_employee.name, "qualifications": new_employee.qualifications}

@app.post("/debug-bulk-update-inventory")
def debug_bulk_update_inventory(db: Session = Depends(get_db)):
    inventories = db.query(Inventory).all()
    for inv in inventories:
        inv.updated_by = f"注文番号:{inv.id} コンクリートテスト 購入分"
        inv.last_updated = dt.now(timezone.utc).astimezone(JST)
    db.commit()
    return {"updated_count": len(inventories)}

# --- WebSocket Manager ---
class ReportManager:
    def __init__(self):
        self.active_connections: List[WebSocket] = []
    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)
        logger.debug(f"WebSocket connected. Total connections: {len(self.active_connections)}")
    def disconnect(self, websocket: WebSocket):
        self.active_connections.remove(websocket)
        logger.debug(f"WebSocket disconnected. Total connections: {len(self.active_connections)}")
    async def broadcast(self, message: str):
        logger.debug(f"Broadcasting '{message}' to {len(self.active_connections)} connections")
        for connection in self.active_connections:
            await connection.send_text(message)

report_manager = ReportManager()

# WebSocket for Reports
@app.websocket("/ws/reports")
async def ws_reports(websocket: WebSocket):
    await report_manager.connect(websocket)
    try:
        while True:
            data = await websocket.receive_text()
            await websocket.send_text(f"Message received: {data}")
    except WebSocketDisconnect:
        report_manager.disconnect(websocket)

# Blueprint Endpoints
@app.get("/projects/{project_id}/blueprints")
def list_blueprints(project_id: int, db: Session = Depends(get_db)):
    blueprints = db.query(Blueprint).filter(Blueprint.project_id == project_id).all()
    return [{"id": bp.id, "name": bp.name, "filename": bp.filename, "file_path": bp.file_path, "version": bp.version, "created_at": bp.created_at} for bp in blueprints]

# --- Startup Event でサンプルデータをシード ---
@app.on_event("startup")
async def startup_event():
    logger.debug("Startup event triggered: シードデータの投入開始")
    db = SessionLocal()
    try:
        company = db.query(Company).first()
        if not company:
            company = Company(
                company_name="株式会社テスト",
                company_code="TEST1234",
                api_key="test_api_key"
            )
            db.add(company)
            db.commit()
            db.refresh(company)
            logger.debug(f"サンプル会社作成: {company.company_name}")
        user = db.query(User).filter(User.email == "admin@test.com").first()
        if not user:
            user = User(
                email="admin@test.com",
                hashed_password=get_password_hash("password"),
                role="admin",
                company_id=company.id
            )
            db.add(user)
            db.commit()
            db.refresh(user)
            logger.debug(f"サンプル管理者ユーザー作成: {user.email}")
        project = db.query(Project).filter(Project.name == "テスト開発計画", Project.company_id == company.id).first()
        if not project:
            project = Project(
                name="テスト開発計画",
                location="東京",
                project_manager="山田太郎",
                start_date=date.today(),
                end_date=date.today(),
                company_id=company.id
            )
            db.add(project)
            db.commit()
            db.refresh(project)
            logger.debug(f"サンプルプロジェクト作成: {project.name}")
        employee = db.query(Employee).filter(Employee.name == "佐藤花子", Employee.company_id == company.id).first()
        if not employee:
            employee = Employee(
                name="佐藤花子",
                qualifications="資格A, 資格B",
                company_id=company.id
            )
            db.add(employee)
            db.commit()
            db.refresh(employee)
            logger.debug(f"サンプル従業員作成: {employee.name}")
        material = db.query(Material).filter(Material.name == "コンクリート", Material.company_id == company.id).first()
        if not material:
            material = Material(
                name="コンクリート",
                price=5000.0,
                supplier_name="コンクリートテスト",
                minimum_stock=100,
                company_id=company.id
            )
            db.add(material)
            db.commit()
            db.refresh(material)
            logger.debug(f"サンプル資材作成: {material.name}")
        inventory = db.query(Inventory).filter(Inventory.material_name == "コンクリート", Inventory.project_id == project.id).first()
        if not inventory:
            inventory = Inventory(
                material_name="コンクリート",
                quantity=150,
                location="倉庫A",
                project_id=project.id,
                company_id=company.id,
                last_updated=dt.now(timezone.utc).astimezone(JST),
                updated_by="admin@test.com"
            )
            db.add(inventory)
            db.commit()
            db.refresh(inventory)
            logger.debug(f"サンプル在庫作成: {inventory.material_name} 数量: {inventory.quantity}")
    finally:
        db.close()
    logger.debug("Startup event完了: シードデータの投入終了")

# LINE Bot ルーターの読み込み（line_bot.py 内の router をインクルード）
from line_bot import router as line_router
app.include_router(line_router)

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="127.0.0.1", port=8000, reload=True)
