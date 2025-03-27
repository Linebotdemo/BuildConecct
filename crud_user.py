from sqlalchemy.orm import Session
from typing import List, Optional
import models, schemas
from passlib.hash import bcrypt

def create_company(db: Session, company_data: dict):
    db_company = models.Company(
        company_name=company_data["company_name"],
        company_code=company_data["company_code"],
        api_key=company_data["api_key"]
    )
    db.add(db_company)
    db.commit()
    db.refresh(db_company)
    return db_company

def get_companies(db: Session, skip: int = 0, limit: int = 100) -> List[models.Company]:
    return db.query(models.Company).offset(skip).limit(limit).all()

def update_company(db: Session, company_id: int, company_data: dict):
    db_company = db.query(models.Company).filter(models.Company.id == company_id).first()
    if not db_company:
        return None
    db_company.company_name = company_data.get("company_name", db_company.company_name)
    db.commit()
    db.refresh(db_company)
    return db_company

def delete_company(db: Session, company_id: int):
    db_company = db.query(models.Company).filter(models.Company.id == company_id).first()
    if db_company:
        db.delete(db_company)
        db.commit()
        return True
    return False

def create_user(db: Session, user_data: schemas.UserCreate):
    hashed_pw = bcrypt.hash(user_data.password)
    db_user = models.User(
        email=user_data.email,
        hashed_password=hashed_pw,
        role=user_data.role,
        active=user_data.active,
        company_id=user_data.company_id
    )
    db.add(db_user)
    db.commit()
    db.refresh(db_user)
    return db_user

def get_user_by_email(db: Session, email: str):
    return db.query(models.User).filter(models.User.email == email).first()

def get_all_users(db: Session, skip: int = 0, limit: int = 100):
    return db.query(models.User).offset(skip).limit(limit).all()

def get_company_users(db: Session, company_id: int, skip: int = 0, limit: int = 100):
    return db.query(models.User).filter(models.User.company_id == company_id).offset(skip).limit(limit).all()

def update_user(db: Session, user_id: int, user_update: schemas.UserUpdate):
    db_user = db.query(models.User).filter(models.User.id == user_id).first()
    if not db_user:
        return None
    for key, value in user_update.dict(exclude_unset=True).items():
        setattr(db_user, key, value)
    db.commit()
    db.refresh(db_user)
    return db_user

def delete_user(db: Session, user_id: int):
    db_user = db.query(models.User).filter(models.User.id == user_id).first()
    if db_user:
        db.delete(db_user)
        db.commit()
        return True
    return False

# LINEユーザー管理
def get_line_user(db: Session, line_user_id: str):
    return db.query(models.LineUser).filter(models.LineUser.line_user_id == line_user_id).first()

def create_line_user(db: Session, line_user_id: str, user_name: str = ""):
    new_line_user = models.LineUser(
        line_user_id=line_user_id,
        line_user_name=user_name,
        registered=False
    )
    db.add(new_line_user)
    db.commit()
    db.refresh(new_line_user)
    return new_line_user

def update_line_user(db: Session, line_user: models.LineUser, updates: dict):
    for key, val in updates.items():
        setattr(line_user, key, val)
    db.commit()
    db.refresh(line_user)
    return line_user

def create_employee(db: Session, employee_data: dict):
    db_employee = models.Employee(**employee_data)
    db.add(db_employee)
    db.commit()
    db.refresh(db_employee)
    return db_employee

def get_employees(db: Session, skip: int = 0, limit: int = 100, company_id: Optional[int] = None):
    query = db.query(models.Employee)
    if company_id is not None:
        query = query.filter(models.Employee.company_id == company_id)
    return query.offset(skip).limit(limit).all()
