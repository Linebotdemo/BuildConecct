import sys
import os
import json
import uuid
import io
import asyncio
from starlette.websockets import WebSocketDisconnect
import logging
import traceback
from datetime import datetime, timedelta
import schemas

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
logging.basicConfig(level=logging.DEBUG)
from typing import List, Optional, Dict

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
    ShelterPhoto as ShelterPhotoModel,
)

# --- Pydanticスキーマ ---
from schemas import (
    Shelter as ShelterSchema,
    ShelterUpdate as ShelterUpdateSchema,
    AuditLog as AuditLogSchema,
    BulkUpdateRequest,
    CompanySchema,
    PhotoUploadResponse,
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
    required_templates = ["index.html", "login.html", "admin.html", "register.html", "register_auth.html"]
    for template in required_templates:
        if template not in template_files:
            logger.error(f"Required template {template} not found in {TEMPLATE_DIR}")
            raise FileNotFoundError(f"Template {template} is missing")
except Exception as e:
    logger.error("Error accessing template directory: %s", str(e))
    raise

# 静的ファイル・データディレクトリ設定
STATIC_DIR = os.path.join(BASE_DIR, "static")
DATA_DIR = os.path.join(BASE_DIR, "data")
os.makedirs(STATIC_DIR, exist_ok=True)
os.makedirs(DATA_DIR, exist_ok=True)
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
templates = Jinja2Templates(directory=TEMPLATE_DIR)
connected_clients: Dict[str, WebSocket] = {}

# CORS設定
app.add_middleware(
    CORSMiddleware,
    allow_origins=["https://safeshelter.onrender.com", "http://localhost:8000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# パスワードハッシュ用
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

# 認証方式
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/company-token")

# HTTP クライアント
http_client = httpx.AsyncClient(timeout=10.0)

# --- 都道府県 → コード辞書 ---
PREF_CODE_MAP = {
    "北海道": "01", "青森県": "02", "岩手県": "03", "宮城県": "04", "秋田県": "05", "山形県": "06",
    "福島県": "07", "茨城県": "08", "栃木県": "09", "群馬県": "10", "埼玉県": "11", "千葉県": "12",
    "東京都": "13", "神奈川県": "14", "新潟県": "15", "富山県": "16", "石川県": "17", "福井県": "18",
    "山梨県": "19", "長野県": "20", "岐阜県": "21", "静岡県": "22", "愛知県": "23", "三重県": "24",
    "滋賀県": "25", "京都府": "26", "大阪府": "27", "兵庫県": "28", "奈良県": "29", "和歌山県": "30",
    "鳥取県": "31", "島根県": "32", "岡山県": "33", "広島県": "34", "山口県": "35", "徳島県": "36",
    "香川県": "37", "愛媛県": "38", "高知県": "39", "福岡県": "40", "佐賀県": "41", "長崎県": "42",
    "熊本県": "43", "大分県": "44", "宮崎県": "45", "鹿児島県": "46", "沖縄県": "47"
}





# スタートアップイベント
@app.on_event("startup")
async def on_startup():
    logger.info("Starting database initialization...")
    try:
        Base.metadata.create_all(bind=engine)
        with SessionLocal() as db:
            admin = db.query(CompanyModel).filter(CompanyModel.email == "admin@example.com").first()
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

            if not db.query(ShelterModel).first():
                sample_shelter = ShelterModel(
                    name="テスト避難所",
                    address="東京都新宿区1-1-1",
                    latitude=35.69388716,
                    longitude=139.70341014,
                    capacity=100,
                    current_occupancy=10,
                    pets_allowed=True,
                    barrier_free=True,
                    toilet_available=True,
                    food_available=False,
                    medical_available=False,
                    wifi_available=True,
                    charging_available=False,
                    equipment="",
                    status="open",
                    photos="",  # 旧列、photos_relで管理
                    contact="03-1234-5678",
                    operator="テスト運営",
                    company_id=admin.id,
                    opened_at=datetime.utcnow(),
                    updated_at=datetime.utcnow(),
                )
                db.add(sample_shelter)
                db.commit()
                logger.info("Sample shelter inserted")
    except Exception as e:
        logger.error("Error during startup: %s\n%s", str(e), traceback.format_exc())
        raise

# シャットダウンイベント
@app.on_event("shutdown")
async def on_shutdown():
    await http_client.aclose()
    logger.info("HTTP client closed")

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

        shelters_data = []
        for shelter in shelters:
            photos = [f"/api/photos/{photo.id}" for photo in shelter.photos_rel]
            shelters_data.append({
                "id": shelter.id,
                "name": shelter.name,
                "address": shelter.address,
                "latitude": shelter.latitude,
                "longitude": shelter.longitude,
                "capacity": shelter.capacity,
                "current_occupancy": shelter.current_occupancy,
                "attributes": {
                    "pets_allowed": shelter.pets_allowed,
                    "barrier_free": shelter.barrier_free,
                    "toilet_available": shelter.toilet_available,
                    "food_available": shelter.food_available,
                    "medical_available": shelter.medical_available,
                    "wifi_available": shelter.wifi_available,
                    "charging_available": shelter.charging_available,
                    "equipment": shelter.equipment or "",
                },
                "photos": photos,
                "contact": shelter.contact,
                "operator": shelter.operator,
                "opened_at": shelter.opened_at.isoformat(),
                "status": shelter.status,
                "updated_at": shelter.updated_at.isoformat() if shelter.updated_at else None,
                "company_id": shelter.company_id,
            })

        template_name = "admin.html" if company.role == "admin" else "index.html"
        template_response = templates.TemplateResponse(
            template_name,
            {
                "request": request,
                "company": company,
                "token": access_token,
                "shelters": shelters_data,
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
    return templates.TemplateResponse("register_auth.html", {"request": request})

# 登録認証処理（POST）
@app.post("/register", response_class=HTMLResponse)
async def register_auth(request: Request, auth_password: str = Form(...)):
    if not REG_PASS:
        logger.error("REG_PASS is not set")
        raise HTTPException(status_code=500, detail="認証パスワードが設定されていません")
    if auth_password != REG_PASS:
        logger.error("Invalid registration password")
        return templates.TemplateResponse(
            "register_auth.html",
            {"request": request, "error": "パスワードが正しくありません"},
        )
    return templates.TemplateResponse(
        "register.html",
        {"request": request, "companies": []},
    )

@app.post("/shelters", response_model=schemas.ShelterSchema)
def create_shelter(shelter: schemas.ShelterCreate, db: Session = Depends(get_db)):
    new_shelter = models.ShelterModel(**shelter.dict())
    db.add(new_shelter)
    db.commit()
    db.refresh(new_shelter)
    return new_shelter

# 避難所一覧取得（公開エンドポイント）
@app.get("/api/shelters", response_model=List[ShelterSchema])
async def get_shelters(
    db: Session = Depends(get_db),
    search: Optional[str] = Query(None),
    status: Optional[str] = Query(None, pattern="^(open|closed)?$"),
    distance: Optional[float] = Query(None, ge=0),
    latitude: Optional[float] = Query(None),
    longitude: Optional[float] = Query(None),
    pets_allowed: Optional[bool] = Query(None),
    barrier_free: Optional[bool] = Query(None),
    toilet_available: Optional[bool] = Query(None),
    food_available: Optional[bool] = Query(None),
    medical_available: Optional[bool] = Query(None),
    wifi_available: Optional[bool] = Query(None),
    charging_available: Optional[bool] = Query(None),
):
    try:
        logger.info("Fetching shelters: search=%s, status=%s, distance=%s", search, status, distance)
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

        shelters = query.all()

        # 距離フィルタ
        if distance and latitude is not None and longitude is not None:
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

        # レスポンス生成
        result = []
        for shelter in shelters:
            photos = [f"/api/photos/{photo.id}" for photo in shelter.photos_rel]
            shelter_data = {
                "id": shelter.id,
                "name": shelter.name,
                "address": shelter.address,
                "latitude": shelter.latitude,
                "longitude": shelter.longitude,
                "capacity": shelter.capacity,
                "current_occupancy": shelter.current_occupancy,
                "attributes": {
                    "pets_allowed": shelter.pets_allowed,
                    "barrier_free": shelter.barrier_free,
                    "toilet_available": shelter.toilet_available,
                    "food_available": shelter.food_available,
                    "medical_available": shelter.medical_available,
                    "wifi_available": shelter.wifi_available,
                    "charging_available": shelter.charging_available,
                    "equipment": shelter.equipment or "",
                },
                "photos": photos,
                "contact": shelter.contact,
                "operator": shelter.operator,
                "opened_at": shelter.opened_at,
                "status": shelter.status,
                "updated_at": shelter.updated_at,
                "company_id": shelter.company_id,
            }
            result.append(shelter_data)

        logger.info("Returning %d shelters", len(result))
        return result
    except Exception as e:
        logger.error("Error in get_shelters: %s\n%s", str(e), traceback.format_exc())
        raise HTTPException(status_code=500, detail=f"避難所取得に失敗しました: {str(e)}")

# 避難所作成（認証必要）
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
            pets_allowed=shelter.attributes.pets_allowed,
            barrier_free=shelter.attributes.barrier_free,
            toilet_available=shelter.attributes.toilet_available,
            food_available=shelter.attributes.food_available,
            medical_available=shelter.attributes.medical_available,
            wifi_available=shelter.attributes.wifi_available,
            charging_available=shelter.attributes.charging_available,
            equipment=shelter.attributes.equipment or "",
            photos="",  # 旧列、photos_relで管理
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

        # 写真の関連付け
        if shelter.photos:
            for photo_id in shelter.photos:
                try:
                    photo_id = int(photo_id.split("/")[-1])  # /api/photos/{id} から ID 抽出
                    photo = db.query(PhotoModel).filter(PhotoModel.id == photo_id).first()
                    if photo:
                        shelter_photo = ShelterPhotoModel(
                            shelter_id=db_shelter.id,
                            photo_id=photo_id,
                            created_at=datetime.utcnow(),
                        )
                        db.add(shelter_photo)
                except ValueError:
                    logger.warning("Invalid photo ID format: %s", photo_id)
        db.commit()

        log_action(db, "create_shelter", db_shelter.id, current_user.email)
        await broadcast_shelter_update({"action": "create", "shelter_id": db_shelter.id})
        logger.info("Shelter created: id=%s, name=%s", db_shelter.id, db_shelter.name)
        return {
            "id": db_shelter.id,
            "name": db_shelter.name,
            "address": db_shelter.address,
            "latitude": db_shelter.latitude,
            "longitude": db_shelter.longitude,
            "capacity": db_shelter.capacity,
            "current_occupancy": db_shelter.current_occupancy,
            "attributes": {
                "pets_allowed": db_shelter.pets_allowed,
                "barrier_free": db_shelter.barrier_free,
                "toilet_available": db_shelter.toilet_available,
                "food_available": db_shelter.food_available,
                "medical_available": db_shelter.medical_available,
                "wifi_available": db_shelter.wifi_available,
                "charging_available": db_shelter.charging_available,
                "equipment": db_shelter.equipment,
            },
            "photos": [f"/api/photos/{photo.id}" for photo in db_shelter.photos_rel],
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

# 避難所更新（認証必要）
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
            if k == "attributes" and v:
                if "pets_allowed" in v:
                    db_shelter.pets_allowed = v["pets_allowed"]
                if "barrier_free" in v:
                    db_shelter.barrier_free = v["barrier_free"]
                if "toilet_available" in v:
                    db_shelter.toilet_available = v["toilet_available"]
                if "food_available" in v:
                    db_shelter.food_available = v["food_available"]
                if "medical_available" in v:
                    db_shelter.medical_available = v["medical_available"]
                if "wifi_available" in v:
                    db_shelter.wifi_available = v["wifi_available"]
                if "charging_available" in v:
                    db_shelter.charging_available = v["charging_available"]
                if "equipment" in v:
                    db_shelter.equipment = v["equipment"]
            elif k == "photos":
                # 既存の関連をクリア
                db.query(ShelterPhotoModel).filter(ShelterPhotoModel.shelter_id == shelter_id).delete()
                if v:
                    for photo_id in v:
                        try:
                            photo_id = int(photo_id.split("/")[-1])
                            photo = db.query(PhotoModel).filter(PhotoModel.id == photo_id).first()
                            if photo:
                                shelter_photo = ShelterPhotoModel(
                                    shelter_id=shelter_id,
                                    photo_id=photo_id,
                                    created_at=datetime.utcnow(),
                                )
                                db.add(shelter_photo)
                        except ValueError:
                            logger.warning("Invalid photo ID format: %s", photo_id)
            else:
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
            "attributes": {
                "pets_allowed": db_shelter.pets_allowed,
                "barrier_free": db_shelter.barrier_free,
                "toilet_available": db_shelter.toilet_available,
                "food_available": db_shelter.food_available,
                "medical_available": db_shelter.medical_available,
                "wifi_available": db_shelter.wifi_available,
                "charging_available": db_shelter.charging_available,
                "equipment": db_shelter.equipment,
            },
            "photos": [f"/api/photos/{photo.id}" for photo in db_shelter.photos_rel],
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

# 避難所削除（認証必要）
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
        # 関連写真のリンクを削除
        db.query(ShelterPhotoModel).filter(ShelterPhotoModel.shelter_id == shelter_id).delete()
        db.delete(db_shelter)
        db.commit()
        log_action(db, "delete_shelter", shelter_id, current_user.email)
        await broadcast_shelter_update({"action": "delete", "shelter_id": shelter_id})
        logger.info("Shelter deleted: id=%s", shelter_id)
        return {"message": "避難所を削除しました"}
    except Exception as e:
        logger.error("Error in delete_shelter: %s\n%s", str(e), traceback.format_exc())
        db.rollback()
        raise HTTPException(status_code=500, detail=f"避難所削除に失敗しました: {str(e)}")

# 一括更新（認証必要）
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

# 一括削除（認証必要）
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
            db.query(ShelterPhotoModel).filter(ShelterPhotoModel.shelter_id == shelter.id).delete()
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

@app.get("/api/reverse-geocode")
async def reverse_geocode(lat: float, lon: float):
    try:
        logger.info("Reverse geocoding: lat=%s, lon=%s", lat, lon)
        url = "https://nominatim.openstreetmap.org/reverse"
        params = {
            "lat": lat,
            "lon": lon,
            "format": "json",
            "accept-language": "ja"
        }
        async with httpx.AsyncClient(headers={"User-Agent": "SmartShelter/1.0"}) as client:
            res = await client.get(url, params=params)
        res.raise_for_status()

        data = res.json()
        logger.info("Nominatim raw response: %s", data)  # ← ★ これを追加

        address = data.get("address", {})
        logger.info("Nominatim address fields: %s", list(address.keys()))  # ← ★ これも追加

        # fallback含めて強化
        prefecture = address.get("state") or address.get("region") or address.get("province") or address.get("county")
        if not prefecture:
            raise HTTPException(status_code=404, detail="都道府県が特定できませんでした")
        logger.info("Reverse geocode result: %s", prefecture)
        return {"prefecture": prefecture}
    except Exception as e:
        logger.error("Reverse geocode error: %s", str(e))
        raise HTTPException(status_code=500, detail="逆ジオコーディングに失敗しました")





# 写真アップロード（単一、認証必要）
@app.post("/api/shelters/upload-photo", response_model=PhotoUploadResponse)
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

        file_ext = file.filename.split(".")[-1].lower()
        allowed_extensions = ["jpg", "jpeg", "png", "gif"]
        if file_ext not in allowed_extensions:
            logger.error("Invalid file extension: %s for file %s", file_ext, file.filename)
            raise HTTPException(
                status_code=400,
                detail=f"許可されていないファイル形式です: {file.filename} (許可: {', '.join(allowed_extensions)})"
            )

        content = await file.read()
        photo = PhotoModel(
            filename=file.filename,
            content_type=file.content_type or f"image/{file_ext}",
            data=content,
        )
        db.add(photo)
        db.commit()
        db.refresh(photo)

        shelter_photo = ShelterPhotoModel(
            shelter_id=shelter_id,
            photo_id=photo.id,
            created_at=datetime.utcnow(),
        )
        db.add(shelter_photo)
        db.commit()

        log_action(db, "upload_photo", shelter_id, current_user.email)
        logger.info("Photo uploaded: id=%s, url=/api/photos/%s", photo.id, photo.id)
        return {"ids": [photo.id], "photo_urls": [f"/api/photos/{photo.id}"]}
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Error in upload_photo: %s\n%s", str(e), traceback.format_exc())
        db.rollback()
        raise HTTPException(status_code=500, detail=f"写真アップロードに失敗しました: {str(e)}")

# 写真アップロード（複数、認証必要）
@app.post("/api/shelters/upload-photos", response_model=PhotoUploadResponse)
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

        photo_ids = []
        allowed_extensions = ["jpg", "jpeg", "png", "gif"]
        invalid_files = []
        for file in files:
            file_ext = file.filename.split(".")[-1].lower()
            if file_ext not in allowed_extensions:
                logger.error("Invalid file extension: %s for file %s", file_ext, file.filename)
                invalid_files.append(file.filename)
                continue

            content = await file.read()
            photo = PhotoModel(
                filename=file.filename,
                content_type=file.content_type or f"image/{file_ext}",
                data=content,
            )
            db.add(photo)
            db.commit()
            db.refresh(photo)

            shelter_photo = ShelterPhotoModel(
                shelter_id=shelter_id,
                photo_id=photo.id,
                created_at=datetime.utcnow(),
            )
            db.add(shelter_photo)
            photo_ids.append(photo.id)

        db.commit()
        if invalid_files:
            logger.warning("Invalid files skipped: %s", ", ".join(invalid_files))
        if not photo_ids:
            raise HTTPException(
                status_code=400,
                detail=f"有効な写真がありません。無効なファイル: {', '.join(invalid_files)} (許可: {', '.join(allowed_extensions)})"
            )

        log_action(db, "upload_photos", shelter_id, current_user.email)
        logger.info("Photos uploaded: ids=%s", photo_ids)
        return {"ids": photo_ids, "photo_urls": [f"/api/photos/{id}" for id in photo_ids]}
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Error in upload_photos: %s\n%s", str(e), traceback.format_exc())
        db.rollback()
        raise HTTPException(status_code=500, detail=f"写真アップロードに失敗しました: {str(e)}")

# 写真取得（バイナリ）
@app.get("/api/photos/{photo_id}")
async def get_photo(photo_id: int, db: Session = Depends(get_db)):
    try:
        logger.info("Fetching photo: id=%d", photo_id)
        row = db.query(PhotoModel.data, PhotoModel.content_type).filter(PhotoModel.id == photo_id).first()
        if not row:
            logger.warning("Photo not found: id=%d, serving placeholder", photo_id)
            placeholder_path = os.path.join(STATIC_DIR, "placeholder.jpg")
            if os.path.exists(placeholder_path):
                with open(placeholder_path, "rb") as f:
                    return StreamingResponse(io.BytesIO(f.read()), media_type="image/jpeg")
            raise HTTPException(status_code=404, detail="写真が見つかりません")
        data, content_type = row
        return StreamingResponse(io.BytesIO(data), media_type=content_type)
    except Exception as e:
        logger.error("Error in get_photo: %s\n%s", str(e), traceback.format_exc())
        raise HTTPException(status_code=500, detail=f"写真取得に失敗しました: {str(e)}")

# 監査ログ取得（認証必要）
@app.get("/api/audit-log", response_model=List[AuditLogSchema])
async def get_audit_logs(db: Session = Depends(get_db), current_user: CompanyModel = Depends(get_current_user)):
    try:
        logger.info("Fetching audit logs, user=%s", current_user.email)
        if current_user.role != "admin":
            logger.error("Permission denied: user=%s", current_user.email)
            raise HTTPException(status_code=403, detail="ログ閲覧権限がありません")
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
        async with httpx.AsyncClient() as client:
            resp = await client.get(url, params=params)
        logger.info("Yahoo Geocode status: %d", resp.status_code)
        if resp.status_code != 200:
            logger.error("Yahoo API error: HTTP %d", resp.status_code)
            raise HTTPException(status_code=502, detail=f"Yahoo API エラー: HTTP {resp.status_code}")
        data = resp.json()
        if not data.get("Feature"):
            msg = data.get("Error", [{"Message": "住所が見つかりません"}])[0]["Message"]
            logger.error("Geocode failed: %s", msg)
            raise HTTPException(status_code=404, detail=f"ジオコーディング失敗: {msg}")
        feature = data["Feature"][0]
        coordinates = feature.get("Geometry", {}).get("Coordinates")
        if not coordinates:
            logger.error("Coordinates not found in response")
            raise HTTPException(status_code=400, detail="無効なジオコードレスポンス形式")
        lon, lat = map(float, coordinates.split(","))
        logger.info("Geocoded: lat=%f, lon=%f", lat, lon)
        return {"lat": lat, "lon": lon}
    except Exception as e:
        logger.error("Error in geocode: %s\n%s", str(e), traceback.format_exc())
        raise HTTPException(status_code=500, detail=f"ジオコーディングに失敗しました: {str(e)}")

# プロキシエンドポイント（JMA API）
@app.get("/api/proxy")
async def proxy_endpoint(url: str):
    try:
        logger.info("Proxying request: url=%s", url)
        if "jma.go.jp" in url and "warning/00.json" in url:
            url = "https://www.jma.go.jp/bosai/warning/data/warning.json"
            logger.info("Redirected JMA URL to: %s", url)
        async with httpx.AsyncClient(timeout=15.0) as client:
            response = await client.get(url)
            response.raise_for_status()
            data = response.json()
            logger.info("Proxy response: keys=%s", list(data.keys()))
            return JSONResponse(content=data)
    except httpx.HTTPStatusError as e:
        logger.error("Proxy HTTP error: %s, status=%d", str(e), e.response.status_code)
        if e.response.status_code in (404, 405):
            logger.warning("Returning empty areas for JMA error: %d", e.response.status_code)
            return JSONResponse(content={"areaTypes": []})
        raise HTTPException(status_code=e.response.status_code, detail=f"Proxy error: {str(e)}")
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
                <ReportDateTime>2025-05-30T03:00:00+09:00</ReportDateTime>
            </Head>
            <Body>
                <Warning>
                    <Item>
                        <Kind>
                            <Name>大雨特別警報</Name>
                            <Code>1</Code>
                        </Kind>
                        <Areas>
                            <Area>
                                <Name>東京都</Name>
                                <Code>13</Code>
                            </Area>
                        </Areas>
                    </Item>
                    <Item>
                        <Kind>
                            <Name>洪水警報</Name>
                            <Code>2</Code>
                        </Kind>
                        <Areas>
                            <Area>
                                <Name>神奈川県</Name>
                                <Code>14</Code>
                            </Area>
                        </Areas>
                    </Item>
                </Warning>
            </Body>
        </Report>
        """
        root = ET.fromstring(mock_data)
        alerts = []
        for item in root.findall(".//Warning/Item"):
            kind = item.find("Kind/Name").text
            area = item.find(".//Area/Name").text
            level = "特別警報" if "特別警報" in kind else "警報" if "警報" in kind else "注意報"
            alerts.append({
                "area": area,
                "warning_type": kind,
                "description": f"{area}における{kind}",
                "issued_at": root.find("Head/ReportDateTime").text,
                "level": level,
                "polygon": get_area_bounds(area),
            })
        with open(cache_file, "w", encoding="utf-8") as f:
            json.dump({"timestamp": datetime.utcnow().isoformat(), "alerts": alerts}, f, ensure_ascii=False)
        logger.info("Fetched and cached %d weather alerts", len(alerts))
        return {"alerts": alerts}
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
async def get_disaster_alerts(lat: float = Query(...), lon: float = Query(...)):
    try:
        # 逆ジオコーディングして都道府県名取得
        geocode_res = await reverse_geocode(lat, lon)
        if geocode_res is None:
            raise HTTPException(status_code=502, detail="逆ジオコーディング失敗")
        
        pref_name = geocode_res
        pref_code = PREF_CODE_MAP.get(pref_name)

        if not pref_code:
            raise HTTPException(status_code=404, detail=f"都道府県コードが見つかりませんでした: {pref_name}")

        # 気象庁APIから警報情報取得
        async with httpx.AsyncClient() as client:
            jma_url = f"https://www.jma.go.jp/bosai/warning/data/warning/{pref_code}.json"
            jma_res = await client.get(jma_url, timeout=10)
            jma_res.raise_for_status()
            jma_data = jma_res.json()

        return jma_data

    except httpx.HTTPStatusError as e:
        logging.error(f"JMAエラー: {e}")
        raise HTTPException(status_code=e.response.status_code, detail=f"JMA APIエラー: {e.response.status_code}")
    except Exception as e:
        logging.error(f"災害アラート取得エラー: {e}")
        raise HTTPException(status_code=500, detail="災害アラート取得エラー")

# ルートページ
@app.get("/", response_class=HTMLResponse)
async def read_root(request: Request, db: Session = Depends(get_db)):
    try:
        logger.info("Rendering index.html")
        shelters = db.query(ShelterModel).all()
        shelters_data = []
        for shelter in shelters:
            photos = [f"/api/photos/{photo.id}" for photo in shelter.photos_rel]
            shelters_data.append({
                "id": shelter.id,
                "name": shelter.name,
                "address": shelter.address,
                "latitude": shelter.latitude,
                "longitude": shelter.longitude,
                "capacity": shelter.capacity,
                "current_occupancy": shelter.current_occupancy,
                "attributes": {
                    "pets_allowed": shelter.pets_allowed,
                    "barrier_free": shelter.barrier_free,
                    "toilet_available": shelter.toilet_available,
                    "food_available": shelter.food_available,
                    "medical_available": shelter.medical_available,
                    "wifi_available": shelter.wifi_available,
                    "charging_available": shelter.charging_available,
                    "equipment": shelter.equipment or "",
                },
                "photos": photos,
                "contact": shelter.contact,
                "operator": shelter.operator,
                "opened_at": shelter.opened_at.isoformat(),
                "status": shelter.status,
                "updated_at": shelter.updated_at.isoformat() if shelter.updated_at else None,
                "company_id": shelter.company_id,
            })
        alerts = fetch_weather_alerts()
        return templates.TemplateResponse(
            "index.html",
            {
                "request": request,
                "alerts": alerts,
                "shelters": shelters_data,
                "api_url": "/api",
                "ws_url": "ws://localhost:8000/ws/shelters" if ENV == "local" else "wss://safeshelter.onrender.com/ws/shelters",
                "YAHOO_APPID": YAHOO_APPID,
            },
        )
    except Exception as e:
        logger.error("Error in read_root: %s\n%s", str(e), traceback.format_exc())
        raise HTTPException(status_code=500, detail=f"ページのレンダリングに失敗しました: {str(e)}")

# ダッシュボード
@app.get("/dashboard", response_class=HTMLResponse)
async def get_dashboard(
    request: Request,
    db: Session = Depends(get_db),
    current_user: CompanyModel = Depends(get_current_user),
):
    try:
        logger.info("Rendering dashboard for user=%s", current_user.email)
        shelters = db.query(ShelterModel).filter(ShelterModel.company_id == current_user.id).all()
        token = request.cookies.get("token")
        if not token:
            logger.error("No token found in cookies")
            raise HTTPException(status_code=401, detail="ログインしてください")
        shelters_data = []
        for shelter in shelters:
            photos = [f"/api/photos/{photo.id}" for photo in shelter.photos_rel]
            shelters_data.append({
                "id": shelter.id,
                "name": shelter.name,
                "address": shelter.address,
                "latitude": shelter.latitude,
                "longitude": shelter.longitude,
                "capacity": shelter.capacity,
                "current_occupancy": shelter.current_occupancy,
                "attributes": {
                    "pets_allowed": shelter.pets_allowed,
                    "barrier_free": shelter.barrier_free,
                    "toilet_available": shelter.toilet_available,
                    "food_available": shelter.food_available,
                    "medical_available": shelter.medical_available,
                    "wifi_available": shelter.wifi_available,
                    "charging_available": shelter.charging_available,
                    "equipment": shelter.equipment or "",
                },
                "photos": photos,
                "contact": shelter.contact,
                "operator": shelter.operator,
                "opened_at": shelter.opened_at.isoformat(),
                "status": shelter.status,
                "updated_at": shelter.updated_at.isoformat() if shelter.updated_at else None,
                "company_id": shelter.company_id,
            })
        return templates.TemplateResponse(
            "index.html",
            {
                "request": request,
                "company": current_user,
                "shelters": shelters_data,
                "token": token,
                "api_url": "/api",
                "ws_url": "ws://localhost:8000/ws/shelters" if ENV == "local" else "wss://safeshelter.onrender.com/ws/shelters",
                "YAHOO_APPID": YAHOO_APPID,
            },
        )
    except Exception as e:
        logger.error("Error in get_dashboard: %s\n%s", str(e), traceback.format_exc())
        raise HTTPException(status_code=500, detail=f"ダッシュボードのレンダリングに失敗しました: {str(e)}")

# ログアウト
@app.get("/logout", response_class=HTMLResponse)
async def logout_page(request: Request):
    try:
        logger.info("Logging out")
        response = templates.TemplateResponse("login.html", {"request": request, "error": None})
        response.delete_cookie("token")
        return response
    except Exception as e:
        logger.error("Error in logout_page: %s\n%s", str(e), traceback.format_exc())
        raise HTTPException(status_code=500, detail=f"ログアウトに失敗しました: {str(e)}")

# 写真アップロード（バイナリ、認証必要）
@app.post("/api/photos/upload", response_model=PhotoUploadResponse)
async def upload_photo_binary(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: CompanyModel = Depends(get_current_user),
):
    try:
        logger.info("Uploading photo: filename=%s", file.filename)
        file_ext = file.filename.split(".")[-1].lower()
        if file_ext not in ["jpg", "jpeg", "png", "gif"]:
            logger.error("Invalid file extension: %s", file_ext)
            raise HTTPException(status_code=400, detail="無効な画像形式です")
        content = await file.read()
        photo = PhotoModel(
            filename=file.filename,
            content_type=file.content_type or f"image/{file_ext}",
            data=content,
        )
        db.add(photo)
        db.commit()
        db.refresh(photo)
        logger.info("Photo uploaded: id=%s", photo.id)
        return {"ids": [photo.id], "photo_urls": [f"/api/photos/{photo.id}"]}
    except Exception as e:
        logger.error("Error in upload_photo_binary: %s\n%s", str(e), traceback.format_exc())
        db.rollback()
        raise HTTPException(status_code=500, detail=f"写真アップロードに失敗しました: {str(e)}")

# WebSocketエンドポイント
@app.websocket("/ws/shelters")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    try:
        while True:
            await asyncio.sleep(60)  # keep-alive or dummy wait
    except WebSocketDisconnect:
        logger.info("WebSocket disconnected")

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

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=10000)