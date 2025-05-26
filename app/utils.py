import os
import secrets
from datetime import datetime
from typing import List

from fastapi import APIRouter, Depends, HTTPException
from passlib.context import CryptContext
from pydantic import BaseModel, EmailStr
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
print("→ LOADING utils.py (no create_all)")
from database import get_db
from models import Company as CompanyModel

pwd_ctx = CryptContext(schemes=["bcrypt"], deprecated="auto")

def hash_password(plain: str) -> str:
    return pwd_ctx.hash(plain)

class CompanyOut(BaseModel):
    id: int
    name: str
    email: EmailStr
    role: str  # 追加
    created_at: datetime
    class Config:
        from_attributes = True

router = APIRouter(prefix="/api/companies", tags=["companies"])

@router.get("/", response_model=List[CompanyOut])
async def list_companies(db: Session = Depends(get_db)):
    return db.query(CompanyModel).order_by(CompanyModel.created_at.desc()).all()