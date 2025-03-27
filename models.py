import datetime
from sqlalchemy import Column, Integer, String, Float, Text, Boolean, Date, DateTime, ForeignKey
from sqlalchemy.orm import relationship
from database import Base

# ------------------------
# Company
# ------------------------
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

# ------------------------
# User
# ------------------------
class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True, index=True)
    email = Column(String, unique=True, nullable=False, index=True)
    hashed_password = Column(String, nullable=False)
    role = Column(String, default="user")
    active = Column(Boolean, default=True)
    company_id = Column(Integer, ForeignKey("companies.id"), nullable=True)

    company = relationship("Company", back_populates="users")

# ------------------------
# Project
# ------------------------
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

# ------------------------
# Report
# ------------------------
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
    created_at = Column(DateTime, default=datetime.datetime.utcnow, nullable=False)

    company = relationship("Company", back_populates="reports")
    project = relationship("Project", back_populates="reports")

# ------------------------
# ScheduleItem
# ------------------------
class ScheduleItem(Base):
    __tablename__ = "schedule_items"
    id = Column(Integer, primary_key=True, index=True)
    project_id = Column(Integer, ForeignKey("projects.id"), nullable=False)
    task = Column(String, nullable=False)
    start_time = Column(DateTime, nullable=False)
    end_time = Column(DateTime, nullable=False)
    status = Column(String, default="not_started")
    company_id = Column(Integer, ForeignKey("companies.id"), nullable=False)

    project = relationship("Project", back_populates="schedule_items")
    company = relationship("Company", back_populates="schedule_items")

# ------------------------
# Order
# ------------------------
class Order(Base):
    __tablename__ = "orders"
    id = Column(Integer, primary_key=True, index=True)
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
    company_id = Column(Integer, ForeignKey("companies.id"), nullable=False)

    project = relationship("Project", back_populates="orders")
    company = relationship("Company", back_populates="orders")

# ------------------------
# Inventory
# ------------------------
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
    updated_at = Column(DateTime, default=datetime.datetime.utcnow)
    updated_by = Column(String, nullable=True)
    change_data = Column(Text, nullable=True)

    inventory = relationship("Inventory", back_populates="history")

# ------------------------
# Blueprint
# ------------------------
class Blueprint(Base):
    __tablename__ = "blueprints"
    id = Column(Integer, primary_key=True, index=True)
    project_id = Column(Integer, ForeignKey("projects.id"), nullable=False)
    name = Column(String, nullable=False)
    filename = Column(String, nullable=False)
    file_path = Column(String, nullable=False)
    version = Column(String, nullable=True)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)
    company_id = Column(Integer, ForeignKey("companies.id"), nullable=False)

    project = relationship("Project", back_populates="blueprints")
    company = relationship("Company", back_populates="blueprints")

# ------------------------
# LineUser
# ------------------------
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

# ------------------------
# Material
# ------------------------
class Material(Base):
    __tablename__ = "materials"
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False)
    price = Column(Float, nullable=False)
    supplier_name = Column(String, nullable=False)
    minimum_stock = Column(Integer, nullable=False)
    company_id = Column(Integer, ForeignKey("companies.id"), nullable=True)

    company = relationship("Company", back_populates="materials")

# ------------------------
# Employee
# ------------------------
class Employee(Base):
    __tablename__ = "employees"
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False)
    qualifications = Column(String, nullable=True)
    company_id = Column(Integer, ForeignKey("companies.id"), nullable=True)

    company = relationship("Company", back_populates="employees")
