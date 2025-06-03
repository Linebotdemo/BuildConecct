import os
import secrets
from datetime import datetime
from typing import List
from schemas import CompanyCreateSchema

from fastapi import APIRouter, Depends, HTTPException, status
from passlib.context import CryptContext
from pydantic import BaseModel, EmailStr
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from database import get_db
from models import Company as CompanyModel

print("→ LOADING utils.py (no create_all)")

pwd_ctx = CryptContext(schemes=["bcrypt"], deprecated="auto")

def hash_password(plain: str) -> str:
    return pwd_ctx.hash(plain)

# 🔽 クライアントからのリクエスト用（password付き）
class CompanyCreateSchema(BaseModel):
    name: str
    email: EmailStr
    password: str

# 🔽 レスポンス用
class CompanyOut(BaseModel):
    id: int
    name: str
    email: EmailStr
    role: str
    created_at: datetime
    class Config:
        from_attributes = True

router = APIRouter(prefix="/api/companies", tags=["companies"])

@router.get("/", response_model=List[CompanyOut])
def list_companies(db: Session = Depends(get_db)):
    return db.query(CompanyModel).order_by(CompanyModel.created_at.desc()).all()

@router.post("/", response_model=CompanyOut)
def create_company(company: CompanyCreateSchema, db: Session = Depends(get_db)):
    try:
        print(f"Received company data: {company.dict()}")
        existing_company = db.query(CompanyModel).filter(
            (CompanyModel.email == company.email) | (CompanyModel.name == company.name)
        ).first()
        if existing_company:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="自治体名またはメールアドレスが既に登録されています"
            )

        hashed_pw = hash_password(company.password)
        db_company = CompanyModel(
            name=company.name,
            email=company.email,
            hashed_pw=hashed_pw,
            role="company",  # デフォルトで company ロール
            created_at=datetime.utcnow()
        )
        db.add(db_company)
        db.commit()
        db.refresh(db_company)
        print(f"Company created: email={db_company.email}, role={db_company.role}")
        return db_company
    except IntegrityError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="自治体名またはメールアドレスが既に登録されています"
        )
    except Exception as e:
        print(f"Error creating company: {str(e)}")
        raise HTTPException(status_code=400, detail=f"自治体登録に失敗しました: {str(e)}")
