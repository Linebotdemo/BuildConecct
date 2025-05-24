# utils.py

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

from database import get_db, Base, engine
from models import Company as CompanyModel

# テーブル作成
Base.metadata.create_all(bind=engine)

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
        orm_mode = True

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

@router.get("/register", response_class=HTMLResponse)
async def show_register(
    request: Request,
    credentials: HTTPBasicCredentials = Depends(security),
    companies: List[CompanyModel] = Depends(list_companies),
):
    # Basic 認証ユーザー／パスワード（環境変数で管理推奨）
    valid_user = os.getenv("REG_USER", "admin")
    valid_pass = os.getenv("REG_PASS", "pass123")
    if not (
        secrets.compare_digest(credentials.username, valid_user)
        and secrets.compare_digest(credentials.password, valid_pass)
    ):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Unauthorized",
            headers={"WWW-Authenticate": "Basic"},
        )

    # 認証成功 → register.html を companies 一覧付きでレンダリング
    return templates.TemplateResponse(
        "register.html",
        {
            "request": request,
            "companies": companies
        }
    )
