import os
import secrets
from datetime import datetime
from typing import List

from fastapi import (
    APIRouter,
    Depends,
    Form,
    HTTPException,
    Request,
    status
)
from fastapi.responses import HTMLResponse
from fastapi.security import HTTPBasic, HTTPBasicCredentials
from fastapi.templating import Jinja2Templates
from passlib.context import CryptContext
from pydantic import BaseModel, EmailStr
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
print("→ LOADING utils.py (no create_all)")
from database import get_db
from models import Company as CompanyModel

# パスワードハッシュ用
pwd_ctx = CryptContext(schemes=["bcrypt"], deprecated="auto")

def hash_password(plain: str) -> str:
    return pwd_ctx.hash(plain)

# Pydantic スキーマ
class CompanyOut(BaseModel):
    id: int
    name: str
    email: EmailStr
    created_at: datetime
    class Config:
        from_attributes = True  # orm_mode を from_attributes に変更

# ルーター＆テンプレート設定
router = APIRouter(prefix="/api/companies", tags=["companies"])
templates = Jinja2Templates(directory="templates")
security = HTTPBasic()

@router.post("/", response_model=CompanyOut)
async def register_company(
    name: str = Form(...),
    email: EmailStr = Form(...),
    password: str = Form(...),
    db: Session = Depends(get_db)
):
    hashed = hash_password(password)
    company = CompanyModel(
        name=name,
        email=email,
        hashed_pw=hashed,
        created_at=datetime.utcnow()
    )
    db.add(company)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(
            status_code=400,
            detail="その企業名またはメールは既に登録されています"
        )
    db.refresh(company)
    return company

@router.get("/", response_model=List[CompanyOut])
async def list_companies(db: Session = Depends(get_db)):
    return db.query(CompanyModel)\
             .order_by(CompanyModel.created_at.desc())\
             .all()

