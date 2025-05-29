import sys
import os
import json
import uuid
import io
import logging
import traceback
from datetime import datetime, timedelta
from sqlalchemy.sql import func
from fastapi import FastAPI, Depends
from typing import List, Optional, Dict
from fastapi import (
    FastAPI,
    Depends,
    HTTPException,
    WebSocket,
    status,
    File,
    UploadFile,
    Request,
    Form,
    Query,
)
from fastapi.responses import HTMLResponse, Response, FileResponse, JSONResponse, StreamingResponse
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from passlib.context import CryptContext
from jose import JWTError, jwt
from sqlalchemy.orm import Session
from pydantic import ValidationError
import httpx
import xml.etree.ElementTree as ET

# ロギング設定
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)

# デバッグ用ログ
logger.info("Current working directory: %s", os.getcwd())
logger.info("Python sys.path: %s", sys.path)

# --- DB周り ---
from database import SessionLocal, engine, Base, get_db

# --- ORMモデル ---
from models import (
    Shelter as ShelterModel,
    AuditLog as AuditLogModel,
    Company as CompanyModel,
    Photo as PhotoModel,
)

# --- Pydanticスキーマ ---
from schemas import (
    Shelter as ShelterSchema,
    ShelterUpdate as ShelterUpdateSchema,
    AuditLog as AuditLogSchema,
    BulkUpdateRequest,
    CompanySchema,
)

# --- 企業周りのRouter ---
from utils import router as company_router

# FastAPI アプリケーション
app = FastAPI(title="SafeShelter API", version="1.0.0")

# 環境変数の検証
REQUIRED_ENV_VARS = ["YAHOO_APPID", "JWT_SECRET_KEY", "REG_PASS", "DATABASE_URL"]
missing_vars = [var for var in REQUIRED_ENV_VARS if not os.getenv(var)]
if missing_vars:
    error_msg = f"Missing required environment variables: {', '.join(missing_vars)}"
    logger.error(error_msg)
    raise RuntimeError(error_msg)

# 環境変数
YAHOO_APPID = os.getenv("YAHOO_APPID")
REG_PASS = os.getenv("REG_PASS")
SECRET_KEY = os.getenv("JWT_SECRET_KEY")
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 30
ENV = os.getenv("ENV", "production")

# テンプレートディレクトリ設定
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DEFAULT_TEMPLATE_DIR = os.path.join(BASE_DIR, "templates")
TEMPLATE_DIR = os.getenv("TEMPLATE_DIR", DEFAULT_TEMPLATE_DIR)

# テンプレートディレクトリ確認
try:
    os.makedirs(TEMPLATE_DIR, exist_ok=True)
    logger.info("Template directory: %s", os.path.abspath(TEMPLATE_DIR))
    template_files = os.listdir(TEMPLATE_DIR)
    logger.info("Available templates: %s", template_files)
    if "index.html" not in template_files:
        logger.warning("index.html not found in template directory")
    if "login.html" not in template_files:
        logger.warning("login.html not found in template directory")
except Exception as e:
    logger.error("Error accessing template directory: %s", str(e))

# 静的ファイル・テンプレート設定
STATIC_DIR = os.path.join(BASE_DIR, "static")
DATA_DIR = os.path.join(BASE_DIR, "data")
os.makedirs(STATIC_DIR, exist_ok=True)
os.makedirs(DATA_DIR, exist_ok=True)
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
app.mount("/data", StaticFiles(directory=DATA_DIR), name="data")
templates = Jinja2Templates(directory=TEMPLATE_DIR)
connected_clients: Dict[str, WebSocket] = {}

# CORS設定
app.add_middleware(
    CORSMiddleware,
    allow_origins=["https://safeshelter.onrender.com"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# パスワードハッシュ用
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

# 認証方式
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/company-token")

# HTTP クライアント
client = httpx.Client(timeout=10.0)

# スタートアップイベント
@app.on_event("startup")
async def on_startup():
    logger.info("Starting database initialization...")
    try:
        Base.metadata.create_all(bind=engine)  # テーブル作成
        with SessionLocal() as db:
            admin = db.query(CompanyModel).filter(CompanyModel.email == "admin@example.com").first()
            logger.info("Admin check: %s", admin)
            if not admin:
                hashed_pw = pwd_context.hash("admin123")
                admin = CompanyModel(
                    email="admin@example.com",
                    name="管理者",
                    hashed_pw=hashed_pw,
                    role="admin",
                    created_at=datetime.utcnow(),
                )
                db.add(admin)
                db.commit()
                logger.info("Admin account created successfully")
            else:
                logger.info("Admin account exists: email=%s, role=%s", admin.email, admin.role)
    except Exception as e:
        logger.error("Error creating admin account: %s\n%s", str(e), traceback.format_exc())
        raise

# 企業登録／一覧 用 API をマウント
app.include_router(company_router)

# トークン検証
async def get_current_user(token: str = Depends(oauth2_scheme), db: Session = Depends(get_db)):
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="トークンが無効です",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        logger.info("Received token: %s...", token[:10])
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        email: str = payload.get("sub")
        role: str = payload.get("role")
        exp: int = payload.get("exp")
        logger.info("Decoded payload: sub=%s, role=%s, exp=%s", email, role, exp)
        if email is None or role not in ["company", "admin"]:
            logger.error("Invalid email or role: email=%s, role=%s", email, role)
            raise credentials_exception
        if exp is None or datetime.utcnow().timestamp() > exp:
            logger.error("Token expired: exp=%s, current=%s", exp, datetime.utcnow().timestamp())
            raise credentials_exception
        company = db.query(CompanyModel).filter(CompanyModel.email == email).first()
        if company is None:
            logger.error("No company found for email: %s", email)
            raise credentials_exception
        logger.info("Authenticated user: email=%s, role=%s, id=%s", company.email, company.role, company.id)
        return company
    except JWTError as e:
        logger.error("JWT decode error: %s", str(e))
        raise credentials_exception

# トークン生成エンドポイント
@app.post("/api/company-token", response_model=dict)
async def create_company_access_token(
    form_data: OAuth2PasswordRequestForm = Depends(),
    db: Session = Depends(get_db),
):
    logger.info("Token request: username=%s", form_data.username)
    company = db.query(CompanyModel).filter(CompanyModel.email == form_data.username).first()
    if not company or not pwd_context.verify(form_data.password, company.hashed_pw):
        logger.error("Authentication failed for username: %s", form_data.username)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="メールアドレスまたはパスワードが正しくありません",
            headers={"WWW-Authenticate": "Bearer"},
        )
    access_token_expires = datetime.utcnow() + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = jwt.encode(
        {
            "sub": company.email,
            "role": company.role,
            "exp": access_token_expires,
        },
        SECRET_KEY,
        algorithm=ALGORITHM,
    )
    logger.info("Token generated: sub=%s, role=%s, token=%s...", company.email, company.role, access_token[:10])
    return {"access_token": access_token, "token_type": "bearer"}

# ログアクション関数
def log_action(db: Session, action: str, shelter_id: Optional[int] = None, user: Optional[str] = "system"):
    try:
        db_log = AuditLogModel(
            action=action,
            shelter_id=shelter_id,
            user=user,
            timestamp=datetime.utcnow(),
        )
        db.add(db_log)
        db.commit()
        logger.info("Logged action: %s by %s, shelter_id=%s", action, user, shelter_id)
    except Exception as e:
        logger.error("Error logging action: %s\n%s", str(e), traceback.format_exc())
        db.rollback()

# WebSocketブロードキャスト
async def broadcast_shelter_update(data: dict):
    logger.info("Broadcasting update: %s", data)
    disconnected = []
    for client_id, ws in connected_clients.items():
        try:
            await ws.send_json(data)
            logger.debug("Sent to %s", client_id)
        except Exception as e:
            logger.error("Broadcast error to %s: %s", client_id, str(e))
            disconnected.append(client_id)
    for client_id in disconnected:
        if client_id in connected_clients:
            del connected_clients[client_id]
            logger.info("Disconnected client: %s", client_id)

# ログイン画面（GET）
@app.get("/login", response_class=HTMLResponse)
async def login_get(request: Request):
    try:
        logger.info("Rendering login.html for GET /login")
        template_path = os.path.join(TEMPLATE_DIR, "login.html")
        if not os.path.exists(template_path):
            logger.error("Template file not found: %s", template_path)
            raise HTTPException(status_code=500, detail=f"テンプレートファイルが見つかりません: {template_path}")
        return templates.TemplateResponse(
            "login.html",
            {"request": request, "error": None},
        )
    except Exception as e:
        logger.error("Error rendering login.html: %s\n%s", str(e), traceback.format_exc())
        raise HTTPException(status_code=500, detail=f"テンプレートのレンダリングに失敗しました: {str(e)}")

# ログイン処理（POST）
@app.post("/login", response_class=HTMLResponse)
async def login_post(
    request: Request,
    username: str = Form(...),
    password: str = Form(...),
    db: Session = Depends(get_db),
):
    try:
        logger.info("Login attempt: username=%s", username)
        company = db.query(CompanyModel).filter(CompanyModel.email == username).first()
        if not company or not pwd_context.verify(password, company.hashed_pw):
            logger.error("Login failed: username=%s", username)
            template_path = os.path.join(TEMPLATE_DIR, "login.html")
            if not os.path.exists(template_path):
                logger.error("Template file not found: %s", template_path)
                raise HTTPException(status_code=500, detail=f"テンプレートファイルが見つかりません: {template_path}")
            return templates.TemplateResponse(
                "login.html",
                {"request": request, "error": "メールアドレスまたはパスワードが正しくありません"},
            )

        access_token_expires = datetime.utcnow() + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
        access_token = jwt.encode(
            {
                "sub": company.email,
                "role": company.role,
                "exp": access_token_expires,
            },
            SECRET_KEY,
            algorithm=ALGORITHM,
        )
        logger.info("Login successful: username=%s, role=%s, token=%s...", username, company.role, access_token[:10])

        shelters = []
        logs = []
        try:
            if company.role == "admin":
                shelters = db.query(ShelterModel).all()
                logs = db.query(AuditLogModel).order_by(AuditLogModel.timestamp.desc()).limit(50).all()
            else:
                shelters = db.query(ShelterModel).filter(ShelterModel.operator == company.name).all()
        except Exception as e:
            logger.error("Error fetching shelters/logs: %s\n%s", str(e), traceback.format_exc())

        template_name = "admin.html" if company.role == "admin" else "company-dashboard.html"
        template_path = os.path.join(TEMPLATE_DIR, template_name)
        if not os.path.exists(template_path):
            logger.error("Template file not found: %s", template_path)
            raise HTTPException(status_code=500, detail=f"テンプレートファイルが見つかりません: {template_path}")
        template_response = templates.TemplateResponse(
            template_name,
            {
                "request": request,
                "company": company,
                "token": access_token,
                "shelters": shelters,
                "logs": logs if company.role == "admin" else [],
                "api_url": "/api",
                "ws_url": "ws://localhost:8000/ws/shelters" if ENV == "local" else "wss://safeshelter.onrender.com/ws/shelters",
                "YAHOO_APPID": YAHOO_APPID,
            },
        )
        template_response.set_cookie(key="token", value=access_token, httponly=True, secure=ENV == "production")
        return template_response
    except Exception as e:
        logger.error("Error in login_post: %s\n%s", str(e), traceback.format_exc())
        template_path = os.path.join(TEMPLATE_DIR, "login.html")
        if not os.path.exists(template_path):
            logger.error("Template file not found: %s", template_path)
            raise HTTPException(status_code=500, detail=f"テンプレートファイルが見つかりません: {template_path}")
        return templates.TemplateResponse(
            "login.html",
            {"request": request, "error": f"ログインに失敗しました: {str(e)}"},
        )

# 登録認証画面（GET）
@app.get("/register", response_class=HTMLResponse)
async def register_page(request: Request):
    if not REG_PASS:
        logger.error("REG_PASS is not set")
        raise HTTPException(status_code=500, detail="認証パスワードが設定されていません")
    template_path = os.path.join(TEMPLATE_DIR, "register_auth.html")
    if not os.path.exists(template_path):
        logger.error("Template file not found: %s", template_path)
        raise HTTPException(status_code=500, detail=f"テンプレートファイルが見つかりません: {template_path}")
    return templates.TemplateResponse("register_auth.html", {"request": request})

# 登録認証処理（POST）
@app.post("/register", response_class=HTMLResponse)
async def register_auth(request: Request, auth_password: str = Form(...)):
    if not REG_PASS:
        logger.error("REG_PASS is not set")
        raise HTTPException(status_code=500, detail="認証パスワードが設定されていません")
    if auth_password != REG_PASS:
        logger.error("Invalid registration password")
        template_path = os.path.join(TEMPLATE_DIR, "register_auth.html")
        if not os.path.exists(template_path):
            logger.error("Template file not found: %s", template_path)
            raise HTTPException(status_code=500, detail=f"テンプレートファイルが見つかりません: {template_path}")
        return templates.TemplateResponse(
            "register_auth.html",
            {"request": request, "error": "パスワードが正しくありません"},
        )
    template_path = os.path.join(TEMPLATE_DIR, "register.html")
    if not os.path.exists(template_path):
        logger.error("Template file not found: %s", template_path)
        raise HTTPException(status_code=500, detail=f"テンプレートファイルが見つかりません: {template_path}")
    return templates.TemplateResponse(
        "register.html",
        {"request": request, "companies": []},
    )

# 避難所一覧取得
@app.get("/api/shelters", response_model=List[ShelterSchema])
async def get_shelters(
    search: Optional[str] = None,
    pets_allowed: Optional[bool] = Query(None),
    barrier_free: Optional[bool] = Query(None),
    toilet_available: Optional[bool] = Query(None),
    food_available: Optional[bool] = Query(None),
    medical_available: Optional[bool] = Query(None),
    wifi_available: Optional[bool] = Query(None),
    charging_available: Optional[bool] = Query(None),
    status: Optional[str] = Query(None, pattern="^(open|closed)?$"),
    distance: Optional[float] = Query(None, ge=0),
    latitude: Optional[float] = Query(None),  # ユーザーの現在地
    longitude: Optional[float] = Query(None),  # ユーザーの現在地
    db: Session = Depends(get_db),
    current_user: CompanyModel = Depends(get_current_user),
):
    try:
        logger.info("Fetching shelters, search=%s, user=%s", search, current_user.email)
        query = db.query(ShelterModel)
        if current_user.role != "admin":
            query = query.filter(ShelterModel.company_id == current_user.id)
        if search:
            query = query.filter(ShelterModel.name.ilike(f"%{search}%") | ShelterModel.address.ilike(f"%{search}%"))
        if status:
            query = query.filter(ShelterModel.status == status)
        if pets_allowed is not None:
            query = query.filter(ShelterModel.pets_allowed == pets_allowed)
        if barrier_free is not None:
            query = query.filter(ShelterModel.barrier_free == barrier_free)
        if toilet_available is not None:
            query = query.filter(ShelterModel.toilet_available == toilet_available)
        if food_available is not None:
            query = query.filter(ShelterModel.food_available == food_available)
        if medical_available is not None:
            query = query.filter(ShelterModel.medical_available == medical_available)
        if wifi_available is not None:
            query = query.filter(ShelterModel.wifi_available == wifi_available)
        if charging_available is not None:
            query = query.filter(ShelterModel.charging_available == charging_available)
        if distance and latitude is not None and longitude is not None:
            # ハバーサイン公式で距離を計算（SQL）
            query = query.filter(
                6371 * func.acos(
                    func.cos(func.radians(latitude)) * func.cos(func.radians(ShelterModel.latitude)) *
                    func.cos(func.radians(ShelterModel.longitude) - func.radians(longitude)) +
                    func.sin(func.radians(latitude)) * func.sin(func.radians(ShelterModel.latitude))
                ) <= distance
            )
        shelters_orm = query.all()
        shelters = []
        for s in shelters_orm:
            shelter_data = {
                "id": s.id,
                "name": s.name,
                "address": s.address,
                "latitude": s.latitude,
                "longitude": s.longitude,
                "capacity": s.capacity,
                "current_occupancy": s.current_occupancy,
                "attributes": {
                    "pets_allowed": s.pets_allowed,
                    "barrier_free": s.barrier_free,
                    "toilet_available": s.toilet_available,
                    "food_available": s.food_available,
                    "medical_available": s.medical_available,
                    "wifi_available": s.wifi_available,
                    "charging_available": s.charging_available,
                    "equipment": s.equipment,
                },
                "photos": s.photos.split(",") if s.photos else [],
                "contact": s.contact,
                "operator": s.operator,
                "opened_at": s.opened_at,
                "status": s.status,
                "updated_at": s.updated_at,
                "company_id": s.company_id,
            }
            shelters.append(shelter_data)
        logger.info("Returning %d shelters", len(shelters))
        return shelters
    except Exception as e:
        logger.error("Error in get_shelters: %s\n%s", str(e), traceback.format_exc())
        raise HTTPException(status_code=500, detail=f"Failed to fetch shelters: {str(e)}")

# 避難所作成
@app.post("/api/shelters", response_model=ShelterSchema)
async def create_shelter(
    shelter: ShelterSchema,
    db: Session = Depends(get_db),
    current_user: CompanyModel = Depends(get_current_user),
):
    try:
        logger.info("Creating shelter: %s, user=%s", shelter.dict(), current_user.email)
        db_shelter = ShelterModel(
            name=shelter.name,
            address=shelter.address,
            latitude=shelter.latitude,
            longitude=shelter.longitude,
            capacity=shelter.capacity,
            current_occupancy=shelter.current_occupancy,
            pets_allowed=shelter.pets_allowed,
            barrier_free=shelter.barrier_free,
            toilet_available=shelter.toilet_available,
            food_available=shelter.food_available,
            medical_available=shelter.medical_available,
            wifi_available=shelter.wifi_available,
            charging_available=shelter.charging_available,
            equipment=shelter.equipment,
            photos=",".join(shelter.photos) if shelter.photos else "",
            contact=shelter.contact,
            operator=shelter.operator,
            opened_at=shelter.opened_at,
            status=shelter.status,
            updated_at=datetime.utcnow(),
            company_id=current_user.id,
        )
        db.add(db_shelter)
        db.commit()
        db.refresh(db_shelter)
        log_action(db, "create_shelter", db_shelter.id, current_user.email)
        logger.info("Shelter created: id=%s, name=%s", db_shelter.id, db_shelter.name)
        await broadcast_shelter_update({"action": "create", "shelter_id": db_shelter.id})
        return {
            "id": db_shelter.id,
            "name": db_shelter.name,
            "address": db_shelter.address,
            "latitude": db_shelter.latitude,
            "longitude": db_shelter.longitude,
            "capacity": db_shelter.capacity,
            "current_occupancy": db_shelter.current_occupancy,
            "pets_allowed": db_shelter.pets_allowed,
            "barrier_free": db_shelter.barrier_free,
            "toilet_available": db_shelter.toilet_available,
            "food_available": db_shelter.food_available,
            "medical_available": db_shelter.medical_available,
            "wifi_available": db_shelter.wifi_available,
            "charging_available": db_shelter.charging_available,
            "equipment": db_shelter.equipment,
            "photos": db_shelter.photos.split(",") if db_shelter.photos else [],
            "contact": db_shelter.contact,
            "operator": db_shelter.operator,
            "opened_at": db_shelter.opened_at,
            "status": db_shelter.status,
            "updated_at": db_shelter.updated_at,
            "company_id": db_shelter.company_id,
        }
    except ValidationError as e:
        logger.error("Validation error in create_shelter: %s", str(e))
        raise HTTPException(status_code=422, detail=f"データ検証エラー: {str(e)}")
    except Exception as e:
        logger.error("Error in create_shelter: %s\n%s", str(e), traceback.format_exc())
        db.rollback()
        raise HTTPException(status_code=400, detail=f"避難所登録に失敗しました: {str(e)}")

# 避難所更新
@app.put("/api/shelters/{shelter_id}", response_model=ShelterSchema)
async def update_shelter(
    shelter_id: int,
    shelter: ShelterUpdateSchema,
    db: Session = Depends(get_db),
    current_user: CompanyModel = Depends(get_current_user),
):
    try:
        logger.info("Updating shelter: id=%s, user=%s", shelter_id, current_user.email)
        db_shelter = db.query(ShelterModel).filter(ShelterModel.id == shelter_id).first()
        if not db_shelter:
            logger.error("Shelter not found: id=%s", shelter_id)
            raise HTTPException(status_code=404, detail="避難所が見つかりません")
        if db_shelter.company_id != current_user.id and current_user.role != "admin":
            logger.error("Permission denied: user=%s, shelter_id=%s", current_user.email, shelter_id)
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="更新権限がありません")
        data = shelter.dict(exclude_unset=True)
        for k, v in data.items():
            setattr(db_shelter, k, v)
        db_shelter.updated_at = datetime.utcnow()
        db.commit()
        db.refresh(db_shelter)
        log_action(db, "update_shelter", shelter_id, current_user.email)
        await broadcast_shelter_update({"action": "update", "shelter_id": shelter_id})
        logger.info("Shelter updated: id=%s", shelter_id)
        return {
            "id": db_shelter.id,
            "name": db_shelter.name,
            "address": db_shelter.address,
            "latitude": db_shelter.latitude,
            "longitude": db_shelter.longitude,
            "capacity": db_shelter.capacity,
            "current_occupancy": db_shelter.current_occupancy,
            "pets_allowed": db_shelter.pets_allowed,
            "barrier_free": db_shelter.barrier_free,
            "toilet_available": db_shelter.toilet_available,
            "food_available": db_shelter.food_available,
            "medical_available": db_shelter.medical_available,
            "wifi_available": db_shelter.wifi_available,
            "charging_available": db_shelter.charging_available,
            "equipment": db_shelter.equipment,
            "photos": db_shelter.photos.split(",") if db_shelter.photos else [],
            "contact": db_shelter.contact,
            "operator": db_shelter.operator,
            "opened_at": db_shelter.opened_at,
            "status": db_shelter.status,
            "updated_at": db_shelter.updated_at,
            "company_id": db_shelter.company_id,
        }
    except Exception as e:
        logger.error("Error in update_shelter: %s\n%s", str(e), traceback.format_exc())
        db.rollback()
        raise HTTPException(status_code=500, detail=f"避難所更新に失敗しました: {str(e)}")

# 避難所削除
@app.delete("/api/shelters/{shelter_id}")
async def delete_shelter(
    shelter_id: int,
    db: Session = Depends(get_db),
    current_user: CompanyModel = Depends(get_current_user),
):
    try:
        logger.info("Deleting shelter: id=%s, user=%s", shelter_id, current_user.email)
        db_shelter = db.query(ShelterModel).filter(ShelterModel.id == shelter_id).first()
        if not db_shelter:
            logger.error("Shelter not found: id=%s", shelter_id)
            raise HTTPException(status_code=404, detail="避難所が見つかりません")
        if db_shelter.company_id != current_user.id and current_user.role != "admin":
            logger.error("Permission denied: user=%s, shelter_id=%s", current_user.email, shelter_id)
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="削除権限がありません")
        log_action(db, "delete_shelter", shelter_id, current_user.email)
        db.delete(db_shelter)
        db.commit()
        await broadcast_shelter_update({"action": "delete", "shelter_id": shelter_id})
        logger.info("Shelter deleted: id=%s", shelter_id)
        return {"message": "避難所を削除しました"}
    except Exception as e:
        logger.error("Error in delete_shelter: %s\n%s", str(e), traceback.format_exc())
        db.rollback()
        raise HTTPException(status_code=500, detail=f"避難所削除に失敗しました: {str(e)}")

# 一括更新
@app.post("/api/shelters/bulk-update")
async def bulk_update_shelters(
    request: BulkUpdateRequest,
    db: Session = Depends(get_db),
    current_user: CompanyModel = Depends(get_current_user),
):
    try:
        logger.info("Bulk updating shelters: ids=%s, user=%s", request.shelter_ids, current_user.email)
        shelters = db.query(ShelterModel).filter(ShelterModel.id.in_(request.shelter_ids)).all()
        if not shelters:
            logger.error("No shelters found: ids=%s", request.shelter_ids)
            raise HTTPException(status_code=404, detail="避難所が見つかりません")
        for shelter in shelters:
            if shelter.company_id != current_user.id and current_user.role != "admin":
                logger.error("Permission denied: user=%s, shelter_id=%s", current_user.email, shelter.id)
                raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="更新権限がありません")
            if request.status is not None:
                shelter.status = request.status
            if request.current_occupancy is not None:
                shelter.current_occupancy = request.current_occupancy
            shelter.updated_at = datetime.utcnow()
            log_action(db, "bulk_update", shelter.id, current_user.email)
        db.commit()
        await broadcast_shelter_update({"action": "bulk_update", "shelter_ids": request.shelter_ids})
        logger.info("Bulk update completed: %d shelters", len(shelters))
        return {"message": "避難所を一括更新しました"}
    except Exception as e:
        logger.error("Error in bulk_update_shelters: %s\n%s", str(e), traceback.format_exc())
        db.rollback()
        raise HTTPException(status_code=500, detail=f"一括更新に失敗しました: {str(e)}")

# 一括削除
@app.post("/api/shelters/bulk-delete")
async def bulk_delete_shelters(
    shelter_ids: List[int],
    db: Session = Depends(get_db),
    current_user: CompanyModel = Depends(get_current_user),
):
    try:
        logger.info("Bulk deleting shelters: ids=%s, user=%s", shelter_ids, current_user.email)
        shelters = db.query(ShelterModel).filter(ShelterModel.id.in_(shelter_ids)).all()
        if not shelters:
            logger.error("No shelters found: ids=%s", shelter_ids)
            raise HTTPException(status_code=404, detail="避難所が見つかりません")
        for shelter in shelters:
            if shelter.company_id != current_user.id and current_user.role != "admin":
                logger.error("Permission denied: user=%s, shelter_id=%s", current_user.email, shelter.id)
                raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="削除権限がありません")
            log_action(db, "bulk_delete", shelter.id, current_user.email)
            db.delete(shelter)
        db.commit()
        await broadcast_shelter_update({"action": "bulk_delete", "shelter_ids": shelter_ids})
        logger.info("Bulk delete completed: %d shelters", len(shelters))
        return {"message": "避難所を一括削除しました"}
    except Exception as e:
        logger.error("Error in bulk_delete_shelters: %s\n%s", str(e), traceback.format_exc())
        db.rollback()
        raise HTTPException(status_code=500, detail=f"一括削除に失敗しました: {str(e)}")

@app.get("/api/shelters")
async def get_shelters(
    db: Session = Depends(get_db),
    search: Optional[str] = Query(None),
    status: Optional[str] = Query(None),
    distance: Optional[float] = Query(None),
    latitude: Optional[float] = Query(None),
    longitude: Optional[float] = Query(None),
    pets_allowed: Optional[bool] = Query(None),
    barrier_free: Optional[bool] = Query(None),
    toilet_available: Optional[bool] = Query(None),
    food_available: Optional[bool] = Query(None),
    medical_available: Optional[bool] = Query(None),
    wifi_available: Optional[bool] = Query(None),
    charging_available: Optional[bool] = Query(None)
):
    query = db.query(ShelterModel)
    
    # 検索フィルタ
    if search:
        search = f"%{search}%"
        query = query.filter(
            (ShelterModel.name.ilike(search)) |
            (ShelterModel.address.ilike(search))
        )
    
    # 状態フィルタ
    if status:
        query = query.filter(ShelterModel.status == status)
    
    # 属性フィルタ
    if pets_allowed:
        query = query.filter(ShelterModel.attributes['pets_allowed'].astext.cast(Boolean) == True)
    if barrier_free:
        query = query.filter(ShelterModel.attributes['barrier_free'].astext.cast(Boolean) == True)
    if toilet_available:
        query = query.filter(ShelterModel.attributes['toilet_available'].astext.cast(Boolean) == True)
    if food_available:
        query = query.filter(ShelterModel.attributes['food_available'].astext.cast(Boolean) == True)
    if medical_available:
        query = query.filter(ShelterModel.attributes['medical_available'].astext.cast(Boolean) == True)
    if wifi_available:
        query = query.filter(ShelterModel.attributes['wifi_available'].astext.cast(Boolean) == True)
    if charging_available:
        query = query.filter(ShelterModel.attributes['charging_available'].astext.cast(Boolean) == True)

    shelters = query.all()

    # 距離フィルタ（サーバーサイドでの計算）
    if distance and latitude and longitude:
        from math import radians, sin, cos, sqrt, atan2
        def haversine(lat1, lon1, lat2, lon2):
            R = 6371  # 地球の半径（km）
            dlat = radians(lat2 - lat1)
            dlon = radians(lon2 - lon1)
            a = sin(dlat/2)**2 + cos(radians(lat1)) * cos(radians(lat2)) * sin(dlon/2)**2
            c = 2 * atan2(sqrt(a), sqrt(1-a))
            return R * c

        filtered_shelters = []
        for shelter in shelters:
            if shelter.latitude and shelter.longitude:
                dist = haversine(latitude, longitude, shelter.latitude, shelter.longitude)
                if dist <= distance:
                    filtered_shelters.append(shelter)
        shelters = filtered_shelters

    # 写真と属性の正規化
    for shelter in shelters:
        if shelter.photos and not isinstance(shelter.photos, list):
            shelter.photos = [shelter.photos] if shelter.photos else []
            for i, photo in enumerate(shelter.photos):
                if not os.path.exists(f"app/data/photos/{photo}"):
                    shelter.photos[i] = "/static/placeholder.jpg"
        shelter.attributes = shelter.attributes or {}

    return shelters

# 写真アップロード（単一）
@app.post("/api/shelters/upload-photo")
async def upload_photo(
    shelter_id: int = Form(...),
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: CompanyModel = Depends(get_current_user),
):
    try:
        logger.info("Uploading photo for shelter_id=%s, user=%s", shelter_id, current_user.email)
        db_shelter = db.query(ShelterModel).filter(ShelterModel.id == shelter_id).first()
        if not db_shelter:
            logger.error("Shelter not found: id=%s", shelter_id)
            raise HTTPException(status_code=404, detail="避難所が見つかりません")
        if db_shelter.company_id != current_user.id and current_user.role != "admin":
            logger.error("Permission denied: user=%s, shelter_id=%s", current_user.email, shelter_id)
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="アップロード権限がありません")
        os.makedirs(os.path.join(DATA_DIR, "photos"), exist_ok=True)
        file_ext = file.filename.split(".")[-1].lower()
        allowed_extensions = ["jpg", "jpeg", "png", "gif", "webp"]  # WebPを追加
        if file_ext not in allowed_extensions:
            logger.error("Invalid file extension: %s for file %s", file_ext, file.filename)
            raise HTTPException(
                status_code=400,
                detail=f"許可されていないファイル形式です: {file.filename} (許可: {', '.join(allowed_extensions)})"
            )
        filename = f"{uuid.uuid4()}.{file_ext}"
        file_path = os.path.join(DATA_DIR, "photos", filename)
        with open(file_path, "wb") as f:
            f.write(await file.read())
        photo_url = f"/data/photos/{filename}"
        photos = db_shelter.photos.split(",") if db_shelter.photos else []
        photos.append(photo_url)
        db_shelter.photos = ",".join([p for p in photos if p])
        db.commit()
        log_action(db, "upload_photo", shelter_id, current_user.email)
        logger.info("Photo uploaded: url=%s", photo_url)
        return {"photo_url": photo_url}
    except HTTPException:
        raise  # HTTPExceptionはそのまま再送
    except Exception as e:
        logger.error("Error in upload_photo: %s\n%s", str(e), traceback.format_exc())
        db.rollback()
        raise HTTPException(status_code=500, detail=f"写真アップロードに失敗しました: {str(e)}")

# 写真アップロード（複数）
@app.post("/api/shelters/upload-photos")
async def upload_photos(
    shelter_id: int = Form(...),
    files: List[UploadFile] = File(...),
    db: Session = Depends(get_db),
    current_user: CompanyModel = Depends(get_current_user),
):
    try:
        logger.info("Uploading %d photos for shelter_id=%s, user=%s", len(files), shelter_id, current_user.email)
        db_shelter = db.query(ShelterModel).filter(ShelterModel.id == shelter_id).first()
        if not db_shelter:
            logger.error("Shelter not found: id=%s", shelter_id)
            raise HTTPException(status_code=404, detail="避難所が見つかりません")
        if db_shelter.company_id != current_user.id and current_user.role != "admin":
            logger.error("Permission denied: user=%s, shelter_id=%s", current_user.email, shelter_id)
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="アップロード権限がありません")
        os.makedirs(os.path.join(DATA_DIR, "photos"), exist_ok=True)
        photo_urls = []
        allowed_extensions = ["jpg", "jpeg", "png", "gif", "webp"]  # WebPを追加
        invalid_files = []
        for file in files:
            file_ext = file.filename.split(".")[-1].lower()
            if file_ext not in allowed_extensions:
                logger.error("Invalid file extension: %s for file %s", file_ext, file.filename)
                invalid_files.append(file.filename)
                continue
            filename = f"{uuid.uuid4()}.{file_ext}"
            file_path = os.path.join(DATA_DIR, "photos", filename)
            with open(file_path, "wb") as f:
                f.write(await file.read())
            photo_url = f"/data/photos/{filename}"
            photo_urls.append(photo_url)
        if invalid_files:
            logger.warning("Invalid files skipped: %s", ", ".join(invalid_files))
        if not photo_urls:
            raise HTTPException(
                status_code=400,
                detail=f"有効な写真がありません。無効なファイル: {', '.join(invalid_files)} (許可: {', '.join(allowed_extensions)})"
            )
        existing_photos = db_shelter.photos.split(",") if db_shelter.photos else []
        db_shelter.photos = ",".join([p for p in existing_photos + photo_urls if p])
        db.commit()
        log_action(db, "upload_photos", shelter_id, current_user.email)
        logger.info("Photos uploaded: urls=%s", photo_urls)
        return {"photo_urls": photo_urls}
    except HTTPException:
        raise  # HTTPExceptionはそのまま再送
    except Exception as e:
        logger.error("Error in upload_photos: %s\n%s", str(e), traceback.format_exc())
        db.rollback()
        raise HTTPException(status_code=500, detail=f"写真アップロードに失敗しました: {str(e)}")

# 写真取得
@app.get("/api/photos/{photo_id}")
async def get_photo(photo_id: int, db: Session = Depends(get_db)):
    try:
        logger.info("Fetching photo: id=%s", photo_id)
        row = db.query(PhotoModel.data, PhotoModel.content_type).filter(PhotoModel.id == photo_id).first()
        if not row:
            logger.error("Photo not found: id=%s", photo_id)
            raise HTTPException(status_code=404, detail="写真が見つかりません")
        data, content_type = row
        return StreamingResponse(io.BytesIO(data), media_type=content_type)
    except Exception as e:
        logger.error("Error in get_photo: %s\n%s", str(e), traceback.format_exc())
        raise HTTPException(status_code=500, detail=f"写真取得に失敗しました: {str(e)}")

# 監査ログ取得
@app.get("/api/audit-logs", response_model=List[AuditLogSchema])
async def get_audit_logs(db: Session = Depends(get_db), current_user: CompanyModel = Depends(get_current_user)):
    try:
        logger.info("Fetching audit logs, user=%s", current_user.email)
        if current_user.role != "admin":
            logger.error("Permission denied: user=%s", current_user.email)
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="ログ閲覧権限がありません")
        logs = db.query(AuditLogModel).order_by(AuditLogModel.timestamp.desc()).all()
        logger.info("Fetched %d audit logs", len(logs))
        return logs
    except Exception as e:
        logger.error("Error in get_audit_logs: %s\n%s", str(e), traceback.format_exc())
        raise HTTPException(status_code=500, detail=f"ログ取得に失敗しました: {str(e)}")

# ジオコーディング
@app.get("/api/geocode")
async def geocode_address_endpoint(address: str):
    try:
        logger.info("Geocoding address: %s", address)
        url = "https://map.yahooapis.jp/geocode/V1/geoCoder"
        params = {
            "appid": YAHOO_APPID,
            "query": address,
            "output": "json",
        }
        async with httpx.AsyncClient() as async_client:
            resp = await async_client.get(url, params=params)
        logger.info("Yahoo Geocode status: %s", resp.status_code)
        logger.debug("Yahoo Geocode response: %s", json.dumps(resp.json(), ensure_ascii=False))
        if resp.status_code != 200:
            logger.error("Yahoo API error: HTTP %s", resp.status_code)
            raise HTTPException(status_code=502, detail=f"Yahoo API エラー: HTTP {resp.status_code}")
        data = resp.json()
        if not data.get("Feature"):
            msg = data.get("Error", [{"Message": "住所が見つかりません"}])[0]["Message"]
            logger.error("Geocode failed: %s", msg)
            raise HTTPException(status_code=404, detail=f"ジオコーディング失敗: {msg}")
        feature = data["Feature"][0]
        if "Geometry" in feature:
            coordinates = feature["Geometry"].get("Coordinates")
        elif "geometry" in feature:
            coordinates = feature["geometry"].get("coordinates")
        else:
            logger.error("Coordinates not found in response")
            raise HTTPException(status_code=500, detail="無効なジオコードレスポンス形式")
        if not coordinates:
            logger.error("Coordinates is empty")
            raise HTTPException(status_code=500, detail="無効なジオコードレスポンス形式")
        lon, lat = map(float, coordinates.split(","))
        logger.info("Geocoded: lat=%s, lon=%s", lat, lon)
        return {"lat": lat, "lon": lon}
    except Exception as e:
        logger.error("Error in geocode_address_endpoint: %s\n%s", str(e), traceback.format_exc())
        raise HTTPException(status_code=500, detail=f"ジオコーディングに失敗しました: {str(e)}")

# プロキシエンドポイント
@app.get("/proxy")
async def proxy(url: str):
    try:
        logger.info("Proxy request: url=%s", url)
        if "jma.go.jp" in url and "warning/00.json" in url:
            url = url.replace("warning/00.json", "forecast/data/warning.json")
        resp = await client.get(url, timeout=10.0)
        resp.raise_for_status()
        return JSONResponse(status_code=200, content=resp.json())
    except httpx.HTTPStatusError as e:
        logger.error("Proxy HTTP error: %s", str(e))
        if e.response.status_code in (404, 502):
            return JSONResponse(status_code=200, content={"areaTypes": []})
        raise HTTPException(status_code=e.response.status_code, detail=str(e))
    except Exception as e:
        logger.error("Error in proxy: %s\n%s", str(e), traceback.format_exc())
        raise HTTPException(status_code=500, detail=f"プロキシリクエストに失敗しました: {str(e)}")

# 災害アラート取得
def fetch_weather_alerts():
    cache_file = os.path.join(DATA_DIR, "alerts_cache.json")
    try:
        os.makedirs(DATA_DIR, exist_ok=True)
        if os.path.exists(cache_file):
            with open(cache_file, "r", encoding="utf-8") as f:
                cache = json.load(f)
                if datetime.fromisoformat(cache["timestamp"]) > datetime.utcnow() - timedelta(hours=1):
                    logger.info("Returning cached weather alerts")
                    return cache["alerts"]
        mock_data = """
        <Report>
            <Head>
                <Title>気象警報・注意報</Title>
                <ReportDateTime>2025-05-26T15:00:00+09:00</ReportDateTime>
            </Head>
            <Body>
                <Warning>
                    <Item>
                        <Kind>
                            <Name>大雨特別警報</Name>
                            <Code>1</Code>
                        </Kind>
                        <Area>
                            <Name>東京都</Name>
                            <Code>13</Code>
                        </Area>
                    </Item>
                    <Item>
                        <Kind>
                            <Name>洪水警報</Name>
                            <Code>2</Code>
                        </Kind>
                        <Area>
                            <Name>神奈川県</Name>
                            <Code>14</Code>
                        </Area>
                    </Item>
                </Warning>
            </Body>
        </Report>
        """
        root = ET.fromstring(mock_data)
        alerts = []
        for item in root.findall(".//Warning/Item"):
            kind = item.find("Kind/Name").text
            area = item.find("Area/Name").text
            level = "特別警報" if "特別警報" in kind else "警報" if "警報" in kind else "注意報"
            alerts.append({
                "area": str(area),
                "warning_type": kind,
                "description": f"{area}における{kind}の発表",
                "issued_at": root.find("Head/ReportDateTime").text,
                "level": level,
                "bounds": get_area_bounds(area),
            })
        with open(cache_file, "w", encoding="utf-8") as f:
            json.dump({"timestamp": datetime.utcnow().isoformat(), "alerts": alerts}, f, ensure_ascii=False)
        logger.info("Fetched and cached %d weather alerts", len(alerts))
        return alerts
    except Exception as e:
        logger.error("Error in fetch_weather_alerts: %s\n%s", str(e), traceback.format_exc())
        if os.path.exists(cache_file):
            with open(cache_file, "r", encoding="utf-8") as f:
                return json.load(f)["alerts"]
        return []

def get_area_bounds(area: str):
    bounds = {
        "東京都": [[35.5, 139.4], [35.9, 139.9]],
        "神奈川県": [[35.1, 139.0], [35.6, 139.7]],
    }
    return bounds.get(area, [[35.6762, 139.6503], [35.6762, 139.6503]])

@app.get("/api/disaster-alerts")
async def get_disaster_alerts():
    try:
        alerts = fetch_weather_alerts()
        return alerts
    except Exception as e:
        logger.error("Error in get_disaster_alerts: %s\n%s", str(e), traceback.format_exc())
        raise HTTPException(status_code=500, detail=f"災害アラート取得に失敗しました: {str(e)}")

# ルートページ
@app.get("/", response_class=HTMLResponse)
async def read_root(request: Request, db: Session = Depends(get_db)):
    try:
        logger.info("Rendering index.html")
        template_path = os.path.join(TEMPLATE_DIR, "index.html")
        if not os.path.exists(template_path):
            logger.error("Template file not found: %s", template_path)
            raise HTTPException(status_code=500, detail=f"テンプレートファイルが見つかりません: {template_path}")
        shelters = []
        shelters_orm = db.query(ShelterModel).all()
        for s in shelters_orm:
            shelters.append({
                "id": s.id,
                "name": s.name,
                "address": s.address,
                "capacity": s.capacity,
                "current_occupancy": s.current_occupancy,
                "latitude": s.latitude,
                "longitude": s.longitude,
                "attributes": {
                    "pets_allowed": s.pets_allowed,
                    "barrier_free": s.barrier_free,
                    "toilet_available": s.toilet_available,
                    "food_available": s.food_available,
                    "medical_available": s.medical_available,
                    "wifi_available": s.wifi_available,
                    "charging_available": s.charging_available,
                    "equipment": s.equipment,
                },
                "photos": s.photos.split(",") if s.photos else [],
                "contact": s.contact,
                "operator": s.operator,
                "opened_at": s.opened_at,
                "status": s.status,
                "updated_at": s.updated_at,
                "company_id": s.company_id,
            })
        alerts = fetch_weather_alerts()
        return templates.TemplateResponse(
            "index.html",
            {
                "request": request,
                "alerts": alerts,
                "shelters": shelters,
                "api_url": "/api",
                "ws_url": "ws://localhost:8000/ws/shelters" if ENV == "local" else "wss://safeshelter.onrender.com/ws/shelters",
                "YAHOO_APPID": YAHOO_APPID,
            },
        )
    except Exception as e:
        logger.error("Error in read_root: %s\n%s", str(e), traceback.format_exc())
        raise HTTPException(status_code=500, detail=f"ページのレンダリングに失敗しました: {str(e)}")

# 企業ダッシュボード
@app.get("/company-dashboard", response_class=HTMLResponse)
async def company_dashboard_page(
    request: Request,
    current_user: CompanyModel = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    try:
        logger.info("Rendering company-dashboard.html for user=%s", current_user.email)
        template_path = os.path.join(TEMPLATE_DIR, "company-dashboard.html")
        if not os.path.exists(template_path):
            logger.error("Template file not found: %s", template_path)
            raise HTTPException(status_code=500, detail=f"テンプレートファイルが見つかりません: {template_path}")
        shelters = db.query(ShelterModel).filter(ShelterModel.operator == current_user.name).all()
        token = request.cookies.get("token")
        if not token:
            logger.error("No token found in cookies")
            raise HTTPException(status_code=401, detail="ログインしてください")
        return templates.TemplateResponse(
            "company-dashboard.html",
            {
                "request": request,
                "company": current_user,
                "shelters": shelters,
                "token": token,
                "api_url": "/api",
                "ws_url": "ws://localhost:8000/ws/shelters" if ENV == "local" else "wss://safeshelter.onrender.com/ws/shelters",
                "YAHOO_APPID": YAHOO_APPID,
            },
        )
    except Exception as e:
        logger.error("Error in company_dashboard_page: %s\n%s", str(e), traceback.format_exc())
        raise HTTPException(status_code=500, detail=f"ダッシュボードのレンダリングに失敗しました: {str(e)}")

# ログアウト
@app.get("/logout", response_class=HTMLResponse)
async def logout_page(request: Request):
    try:
        logger.info("Logging out")
        template_path = os.path.join(TEMPLATE_DIR, "login.html")
        if not os.path.exists(template_path):
            logger.error("Template file not found: %s", template_path)
            raise HTTPException(status_code=500, detail=f"テンプレートファイルが見つかりません: {template_path}")
        response = templates.TemplateResponse("login.html", {"request": request})
        response.delete_cookie("token")
        return response
    except Exception as e:
        logger.error("Error in logout_page: %s\n%s", str(e), traceback.format_exc())
        raise HTTPException(status_code=500, detail=f"ログアウトに失敗しました: {str(e)}")

# 写真アップロード（バイナリ）
@app.post("/api/photos/upload")
async def upload_photo_binary(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
):
    try:
        logger.info("Uploading photo: filename=%s", file.filename)
        content = await file.read()
        photo = PhotoModel(
            filename=file.filename,
            content_type=file.content_type,
            data=content,
        )
        db.add(photo)
        db.commit()
        db.refresh(photo)
        logger.info("Photo uploaded: id=%s", photo.id)
        return {"filename": file.filename, "id": photo.id}
    except Exception as e:
        logger.error("Error in upload_photo_binary: %s\n%s", str(e), traceback.format_exc())
        db.rollback()
        raise HTTPException(status_code=500, detail=f"写真アップロードに失敗しました: {str(e)}")

# WebSocketエンドポイント
@app.websocket("/ws/shelters")
async def websocket_endpoint(websocket: WebSocket, token: Optional[str] = Query(None), db: Session = Depends(get_db)):
    client_id = None
    try:
        logger.info("WebSocket connection attempt, token=%s...", token[:10] if token else None)
        await websocket.accept()
        if not token:
            logger.error("No token provided for WebSocket")
            await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
            return
        try:
            user = await get_current_user(token, db)
            client_id = f"{user.email}_{uuid.uuid4()}"
            connected_clients[client_id] = websocket
            logger.info("WebSocket connected: id=%s, user=%s", client_id, user.email)
            while True:
                data = await websocket.receive_json()
                logger.debug("Received WebSocket message: %s", data)
        except JWTError as e:
            logger.error("WebSocket JWT error: %s", str(e))
            await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
            return
    except Exception as e:
        logger.error("WebSocket error: %s\n%s", str(e), traceback.format_exc())
        await websocket.close(code=status.WS_1011_INTERNAL_ERROR)
    finally:
        if client_id and client_id in connected_clients:
            del connected_clients[client_id]
            logger.info("WebSocket disconnected: id=%s", client_id)

# ファビコン
@app.get("/favicon.ico", response_class=Response)
async def favicon():
    try:
        favicon_path = os.path.join(STATIC_DIR, "favicon.ico")
        if os.path.exists(favicon_path):
            logger.info("Serving favicon: %s", favicon_path)
            return FileResponse(favicon_path)
        logger.warning("Favicon not found at: %s", favicon_path)
        return Response(status_code=204)
    except Exception as e:
        logger.error("Error serving favicon: %s\n%s", str(e), traceback.format_exc())
        raise HTTPException(status_code=500, detail=f"ファビコン取得に失敗しました: {str(e)}")