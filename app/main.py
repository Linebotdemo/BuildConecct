from fastapi import (
    FastAPI, HTTPException, Depends,
    File, UploadFile, WebSocket, Request, Form, status
)
from fastapi.responses import HTMLResponse, Response, FileResponse, JSONResponse, StreamingResponse
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from passlib.context import CryptContext
from jose import JWTError, jwt
from typing import List, Optional
from sqlalchemy.orm import Session
from datetime import datetime, timedelta
import xml.etree.ElementTree as ET
import os, json, uuid, traceback, aiohttp, httpx, io
from sqlalchemy.sql import insert, select
import sys

# デバッグ用ログ
print("cwd =", os.getcwd())
print("sys.path =", sys.path)

# --- DB周り ---
from database import SessionLocal, engine, Base, get_db

# --- ORMモデル ---
from models import (
    Shelter as ShelterModel,
    AuditLog as AuditLogModel,
    Company as CompanyModel,
    Photo as PhotoModel
)

# --- Pydanticスキーマ ---
from schemas import (
    Shelter as ShelterSchema,
    ShelterUpdate as ShelterUpdateSchema,
    AuditLog as AuditLogSchema,
    BulkUpdateRequest
)

# --- 企業周りのRouter ---
from utils import router as company_router

app = FastAPI()

# スタートアップイベント
@app.on_event("startup")
async def on_startup():
    print("→ Startup creating tables with:", os.getenv("DATABASE_URL"))
    Base.metadata.create_all(bind=engine)

# 企業登録／一覧 用 API をマウント
app.include_router(company_router)

# HTTP クライアント
client = httpx.AsyncClient()

# 環境変数から取得
YAHOO_APPID = os.getenv("YAHOO_APPID")
REG_PASS = os.getenv("REG_PASS")  # 認証パスワード

# 静的ファイル・テンプレート設定
app.mount("/static", StaticFiles(directory="static"), name="static")
app.mount("/data", StaticFiles(directory="app/data"), name="data")
templates = Jinja2Templates(directory="templates")

# CORS設定
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# JWT設定
SECRET_KEY = os.getenv("JWT_SECRET_KEY", "your-secret-key")
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 30

# パスワードハッシュ用
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

# 認証方式
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="api/company-token")

# WebSocket接続管理
connected_clients: set[WebSocket] = set()

# トークン検証（企業）
async def get_current_company(token: str = Depends(oauth2_scheme), db: Session = Depends(get_db)):
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="トークンが無効です",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        email: str = payload.get("sub")
        role: str = payload.get("role")
        if email is None or role != "company":
            raise credentials_exception
    except JWTError:
        raise credentials_exception
    company = db.query(CompanyModel).filter(CompanyModel.email == email).first()
    if company is None:
        raise credentials_exception
    return company

# トークン検証（管理者）
async def get_current_admin(token: str = Depends(oauth2_scheme)):
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="トークンが無効です",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        username: str = payload.get("sub")
        role: str = payload.get("role")
        if username is None or role != "admin":
            raise credentials_exception
    except JWTError:
        raise credentials_exception
    if username != "admin":
        raise credentials_exception
    return {"username": username, "role": "admin"}

# 管理者トークン生成エンドポイント
@app.post("/api/token")
async def create_access_token(form_data: OAuth2PasswordRequestForm = Depends()):
    if form_data.username == "admin" and form_data.password == "admin123":
        access_token = jwt.encode(
            {"sub": "admin", "role": "admin"},
            SECRET_KEY,
            algorithm=ALGORITHM
        )
        return {"access_token": access_token, "token_type": "bearer"}
    raise HTTPException(status_code=401, detail="ユーザー名またはパスワードが正しくありません")

# 企業トークン生成エンドポイント
@app.post("/api/company-token")
async def create_company_access_token(
    form_data: OAuth2PasswordRequestForm = Depends(),
    db: Session = Depends(get_db)
):
    company = db.query(CompanyModel).filter(CompanyModel.email == form_data.username).first()
    if not company or not pwd_context.verify(form_data.password, company.hashed_pw):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="メールアドレスまたはパスワードが正しくありません",
            headers={"WWW-Authenticate": "Bearer"},
        )
    access_token_expires = datetime.utcnow() + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = jwt.encode(
        {"sub": company.email, "role": "company"},
        SECRET_KEY,
        algorithm=ALGORITHM
    )
    return {"access_token": access_token, "token_type": "bearer"}

# ログアクション関数
async def log_action(db: Session, action: str, shelter_id: Optional[int] = None, user: str = "system"):
    db_log = AuditLogModel(
        action=action,
        shelter_id=shelter_id,
        user=user,
        timestamp=datetime.utcnow()
    )
    db.add(db_log)
    db.commit()

# WebSocketブロードキャスト
async def broadcast_shelter_update(data: dict):
    disconnected = []
    for ws in connected_clients:
        try:
            await ws.send_json(data)
        except:
            disconnected.append(ws)
    for ws in disconnected:
        connected_clients.discard(ws)

# /register エンドポイント（GET: 認証フォーム表示, POST: パスワード検証）
@app.get("/register", response_class=HTMLResponse)
async def register_page(request: Request):
    if not REG_PASS:
        raise HTTPException(status_code=500, detail="認証パスワードが設定されていません")
    return templates.TemplateResponse("register_auth.html", {"request": request})

@app.post("/register", response_class=HTMLResponse)
async def register_auth(request: Request, auth_password: str = Form(...)):
    if not REG_PASS:
        raise HTTPException(status_code=500, detail="認証パスワードが設定されていません")
    if auth_password != REG_PASS:
        return templates.TemplateResponse(
            "register_auth.html",
            {"request": request, "error": "パスワードが正しくありません"}
        )
    return templates.TemplateResponse(
        "register.html",
        {
            "request": request,
            "companies": []
        }
    )

# 標準エンドポイント群
@app.get("/api/shelters", response_model=List[ShelterSchema])
async def get_shelters(
    search: Optional[str] = None,
    pets_allowed: Optional[bool] = None,
    barrier_free: Optional[bool] = None,
    toilet_available: Optional[bool] = None,
    food_available: Optional[bool] = None,
    medical_available: Optional[bool] = None,
    wifi_available: Optional[bool] = None,
    charging_available: Optional[bool] = None,
    db: Session = Depends(get_db)
):
    try:
        query = db.query(ShelterModel)
        shelters = query.all()
        result = []
        for s in shelters:
            result.append({
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
                },
                "photos": s.photos.split(",") if s.photos else [],
                "contact": s.contact,
                "operator": s.operator,
                "opened_at": s.opened_at,
                "status": s.status,
                "updated_at": s.updated_at
            })
        return result
    except Exception as e:
        print(f"Error in get_shelters: {e}")
        raise HTTPException(status_code=500, detail="避難所の取得に失敗しました")


@app.post("/api/shelters", response_model=ShelterSchema)
async def create_shelter(
    shelter: ShelterSchema,
    token: str = Depends(oauth2_scheme),
    db: Session = Depends(get_db)
):
    current_company = await get_current_company(token, db)
    db_s = ShelterModel(
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
        photos=",".join(shelter.photos),
        contact=shelter.contact,
        operator=shelter.operator,
        opened_at=shelter.opened_at,
        status=shelter.status,
        updated_at=datetime.utcnow(),
    )
    db.add(db_s)
    db.commit()
    db.refresh(db_s)
    await log_action(db, "create_shelter", db_s.id, current_company.email)
    return db_s

@app.put("/api/shelters/{shelter_id}", response_model=ShelterSchema)
async def update_shelter(
    shelter_id: int,
    shelter: ShelterUpdateSchema,
    token: str = Depends(oauth2_scheme),
    db: Session = Depends(get_db)
):
    db_s = db.query(ShelterModel).filter_by(id=shelter_id).first()
    if not db_s:
        raise HTTPException(404, "避難所が見つかりません")
    data = shelter.dict(exclude_unset=True)
    if "attributes" in data:
        for k, v in data["attributes"].items():
            setattr(db_s, k, v)
        del data["attributes"]
    if "photos" in data:
        data["photos"] = ",".join(data["photos"])
    for k, v in data.items():
        setattr(db_s, k, v)
    db_s.updated_at = datetime.utcnow()
    db.commit()
    db.refresh(db_s)
    await log_action(db, "update_shelter", shelter_id, token)
    return db_s

@app.delete("/api/shelters/{shelter_id}")
async def delete_shelter(
    shelter_id: int,
    token: str = Depends(oauth2_scheme),
    db: Session = Depends(get_db)
):
    db_shelter = db.query(ShelterModel).get(shelter_id)
    if not db_shelter:
        raise HTTPException(status_code=404, detail="避難所が見つかりません")
    if db_shelter.created_by != token:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="削除権限がありません")
    await log_action(db, "delete", shelter_id, token)
    db.delete(db_shelter)
    db.commit()
    await broadcast_shelter_update({"id": shelter_id, "deleted": True})
    return {"message": "避難所を削除しました"}

@app.post("/api/shelters/bulk-update")
async def bulk_update_shelters(
    request: BulkUpdateRequest,
    token: str = Depends(oauth2_scheme),
    db: Session = Depends(get_db)
):
    try:
        shelters = db.query(ShelterModel).filter(
            ShelterModel.id.in_(request.shelter_ids)
        ).all()
        if not shelters:
            raise HTTPException(status_code=404, detail="避難所が見つかりません")
        for shelter in shelters:
            if request.status is not None:
                shelter.status = request.status
            if request.current_occupancy is not None:
                shelter.current_occupancy = request.current_occupancy
            shelter.updated_at = datetime.utcnow()
            await log_action(db, "bulk_update", shelter.id, token)
        db.commit()
        for shelter in shelters:
            shelter_dict = {
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
                },
                "photos": shelter.photos.split(",") if shelter.photos else [],
                "contact": shelter.contact,
                "operator": shelter.operator,
                "opened_at": shelter.opened_at,
                "status": shelter.status,
                "updated_at": shelter.updated_at
            }
            await broadcast_shelter_update(shelter_dict)
        return {"message": "避難所を一括更新しました"}
    except Exception as e:
        print(f"Error in bulk_update_shelters: {e}")
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Internal Server Error: {e}")

@app.post("/api/shelters/bulk-delete")
async def bulk_delete_shelters(
    shelter_ids: List[int],
    token: str = Depends(oauth2_scheme),
    db: Session = Depends(get_db)
):
    shelters = db.query(ShelterModel).filter(ShelterModel.id.in_(shelter_ids)).all()
    if not shelters:
        raise HTTPException(status_code=404, detail="避難所が見つかりません")
    for shelter in shelters:
        await log_action(db, "bulk_delete", shelter.id, token)
    for shelter in shelters:
        db.delete(shelter)
    db.commit()
    for shelter in shelters:
        await broadcast_shelter_update({"id": shelter.id, "deleted": True})
    return {"message": "避難所を一括削除しました"}

@app.post("/api/shelters/upload-photo")
async def upload_photo(
    shelter_id: int = Form(...),
    file: UploadFile = File(...),
    token: str = Depends(oauth2_scheme),
    db: Session = Depends(get_db)
):
    try:
        db_shelter = db.query(ShelterModel).filter(ShelterModel.id == shelter_id).first()
        if not db_shelter:
            raise HTTPException(status_code=404, detail="避難所が見つかりません")
        os.makedirs("app/data/photos", exist_ok=True)
        file_ext = file.filename.split(".")[-1]
        filename = f"{uuid.uuid4()}.{file_ext}"
        file_path = os.path.join("app/data/photos", filename)
        with open(file_path, "wb") as f:
            f.write(await file.read())
        photo_url = f"/data/photos/{filename}"
        photos = db_shelter.photos.split(",") if db_shelter.photos else []
        photos.append(photo_url)
        db_shelter.photos = ",".join(photos)
        db.commit()
        await log_action(db, "upload_photo", shelter_id, token)
        shelter_dict = db_shelter.__dict__
        shelter_dict["photos"] = photos
        shelter_dict["attributes"] = {
            "pets_allowed": db_shelter.pets_allowed,
            "barrier_free": db_shelter.barrier_free,
            "toilet_available": db_shelter.toilet_available,
            "food_available": db_shelter.food_available,
            "medical_available": db_shelter.medical_available,
            "wifi_available": db_shelter.wifi_available,
            "charging_available": db_shelter.charging_available
        }
        await broadcast_shelter_update(shelter_dict)
        return {"photo_url": photo_url}
    except Exception as e:
        print(f"Error in upload_photo: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Internal Server Error: {str(e)}")

@app.post("/api/shelters/upload-photos")
async def upload_photos(
    shelter_id: int = Form(...),
    files: List[UploadFile] = File(...),
    token: str = Depends(oauth2_scheme),
    db: Session = Depends(get_db),
):
    db_shelter = db.query(ShelterModel).get(shelter_id)
    if not db_shelter:
        raise HTTPException(404, "避難所が見つかりません")
    os.makedirs("app/data/photos", exist_ok=True)
    photo_urls = []
    for file in files:
        ext = file.filename.split(".")[-1]
        filename = f"{uuid.uuid4()}.{ext}"
        path = os.path.join("app/data/photos", filename)
        with open(path, "wb") as f:
            f.write(await file.read())
        url = f"/data/photos/{filename}"
        photo_urls.append(url)
    existing = db_shelter.photos.split(",") if db_shelter.photos else []
    db_shelter.photos = ",".join(existing + photo_urls)
    db.commit()
    await log_action(db, "upload_photos", shelter_id, token)
    shelter_dict = {
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
        },
        "photos": db_shelter.photos.split(",") if db_shelter.photos else [],
        "contact": db_shelter.contact,
        "operator": db_shelter.operator,
        "opened_at": db_shelter.opened_at,
        "status": db_shelter.status,
        "updated_at": db_shelter.updated_at
    }
    await broadcast_shelter_update(shelter_dict)
    return {"photo_urls": photo_urls}

@app.get("/api/photos/{photo_id}")
async def get_photo(photo_id: int, db: Session = Depends(get_db)):
    row = db.execute(
        select(PhotoModel.data, PhotoModel.content_type)
        .where(PhotoModel.id == photo_id)
    ).one_or_none()
    if not row:
        raise HTTPException(status_code=404, detail="Photo not found")
    data, content_type = row
    return StreamingResponse(io.BytesIO(data), media_type=content_type)

@app.get("/api/audit-logs", response_model=List[AuditLogSchema])
async def get_audit_logs(db: Session = Depends(get_db)):
    try:
        logs = db.query(AuditLogModel).order_by(AuditLogModel.timestamp.desc()).all()
        return logs
    except Exception as e:
        print(f"Error in get_audit_logs: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Internal Server Error: {str(e)}")

async def geocode_address(address: str):
    async with aiohttp.ClientSession() as session:
        async with session.get(f"https://nominatim.openstreetmap.org/search?q={address}&format=json") as response:
            if response.status == 200:
                data = await response.json()
                if data:
                    return float(data[0]["lat"]), float(data[0]["lon"])
            return 35.6762, 139.6503  # デフォルト: 東京

async def fetch_weather_alerts():
    from datetime import datetime, timedelta  # 関数内でインポート
    cache_file = "app/data/alerts_cache.json"
    try:
        os.makedirs("app/data", exist_ok=True)
        if os.path.exists(cache_file):
            with open(cache_file, "r", encoding="utf-8") as f:
                cache = json.load(f)
                if datetime.fromisoformat(cache["timestamp"]) > datetime.utcnow() - timedelta(hours=1):
                    return cache["alerts"]
        async with aiohttp.ClientSession() as session:
            mock_data = """
            <Report>
                <Head>
                    <Title>気象警報・注意報</Title>
                    <ReportDateTime>2025-05-22T11:00:00+09:00</ReportDateTime>
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
                    "area": area,
                    "warning_type": kind,
                    "description": f"{area}における{kind}の発表",
                    "issued_at": root.find("Head/ReportDateTime").text,
                    "level": level,
                    "bounds": get_area_bounds(area)
                })
            with open(cache_file, "w", encoding="utf-8") as f:
                json.dump({"timestamp": datetime.utcnow().isoformat(), "alerts": alerts}, f, ensure_ascii=False)
            return alerts
    except Exception as e:
        print(f"Error in fetch_weather_alerts: {str(e)}")
        if os.path.exists(cache_file):
            with open(cache_file, "r", encoding="utf-8") as f:
                return json.load(f)["alerts"]
        return []


def get_area_bounds(area):
    bounds = {
        "東京都": [[35.5, 139.4], [35.9, 139.9]],
        "神奈川県": [[35.1, 139.0], [35.6, 139.7]]
    }
    return bounds.get(area, [[35.6762, 139.6503], [35.6762, 139.6503]])

@app.get("/api/disaster-alerts")
async def get_disaster_alerts():
    return await fetch_weather_alerts()

@app.get("/", response_class=HTMLResponse)
async def index(request: Request, db: Session = Depends(get_db)):
    shelters = []
    try:
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
                "pets_allowed": s.pets_allowed,
                "barrier_free": s.barrier_free,
                "toilet_available": s.toilet_available,
                "food_available": s.food_available,
                "medical_available": s.medical_available,
                "wifi_available": s.wifi_available,
                "charging_available": s.charging_available,
                "photos": s.photos.split(",") if s.photos else [],
                "contact": s.contact,
                "operator": s.operator,
                "opened_at": s.opened_at,
                "status": s.status,
                "updated_at": s.updated_at
            })
    except Exception as e:
        print(f"Error fetching shelters: {str(e)}")
        shelters = []  # エラー時は空リストを返す
    alerts = await get_disaster_alerts()
    return templates.TemplateResponse(
        "index.html",
        {
            "request": request,
            "alerts": alerts,
            "shelters": shelters,
            "api_url": "/api",
            "ws_url": "ws://localhost:8000/ws/shelters" if os.getenv("ENV") == "local" else "wss://safeshelter.onrender.com/ws/shelters"
        }
    )

@app.get("/login", response_class=HTMLResponse)
async def login_page(request: Request):
    return templates.TemplateResponse("login.html", {"request": request})

@app.post("/login", response_class=HTMLResponse)
async def login_post(
    request: Request,
    username: str = Form(...),
    password: str = Form(...),
    db: Session = Depends(get_db)
):
    try:
        shelters = []
        logs = []
        try:
            shelters = db.query(ShelterModel).all()
            logs = db.query(AuditLogModel).order_by(AuditLogModel.timestamp.desc()).limit(50).all()
        except Exception as e:
            print(f"Error fetching shelters/logs in login_post: {str(e)}")
        if username == "admin":
            form_data = OAuth2PasswordRequestForm(username=username, password=password, scope="")
            response = await create_access_token(form_data)
            token = response["access_token"]
            template_response = templates.TemplateResponse(
                "admin.html",
                {
                    "request": request,
                    "token": token,
                    "shelters": shelters,
                    "logs": logs,
                    "api_url": "/api",
                    "ws_url": "ws://localhost:8000/ws/shelters" if os.getenv("ENV") == "local" else "wss://safeshelter.onrender.com/ws/shelters"
                }
            )
            template_response.set_cookie(key="token", value=token)
            return template_response

        company = db.query(CompanyModel).filter(CompanyModel.email == username).first()
        if company and pwd_context.verify(password, company.hashed_pw):
            access_token = jwt.encode(
                {"sub": company.email, "role": "company"},
                SECRET_KEY,
                algorithm=ALGORITHM
            )
            template_response = templates.TemplateResponse(
                "company-dashboard.html",
                {
                    "request": request,
                    "company": company,
                    "shelters": db.query(ShelterModel).filter(ShelterModel.operator == company.name).all(),
                    "api_url": "/api",
                    "ws_url": "ws://localhost:8000/ws/shelters" if os.getenv("ENV") == "local" else "wss://safeshelter.onrender.com/ws/shelters"
                }
            )
            template_response.set_cookie(key="company_token", value=access_token)
            return template_response

        return templates.TemplateResponse(
            "login.html",
            {"request": request, "error": "メールアドレスまたはパスワードが正しくありません"}
        )

    except Exception as e:
        print(f"Error in login_post: {str(e)}")
        return templates.TemplateResponse(
            "login.html",
            {"request": request, "error": f"ログインに失敗しました: {str(e)}"}
        )

@app.get("/admin", response_class=HTMLResponse)
async def admin_page(
    request: Request,
    admin: dict = Depends(get_current_admin),
    db: Session = Depends(get_db)
):
    try:
        shelters = db.query(ShelterModel).all()
        logs = db.query(AuditLogModel).order_by(AuditLogModel.timestamp.desc()).limit(50).all()
        token = request.cookies.get("token")
        if not token:
            return templates.TemplateResponse(
                "login.html",
                {"request": request, "error": "ログインしてください"}
            )
        return templates.TemplateResponse(
            "admin.html",
            {
                "request": request,
                "token": token,
                "shelters": shelters,
                "logs": logs,
                "api_url": "/api",
                "ws_url": "ws://localhost:8000/ws/shelters" if os.getenv("ENV") == "local" else "wss://<your-service>.onrender.com/ws/shelters"
            }
        )
    except Exception as e:
        print(f"Error in admin_page: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Internal Server Error: {str(e)}")

@app.get("/company-dashboard", response_class=HTMLResponse)
async def company_dashboard_page(
    request: Request,
    company: CompanyModel = Depends(get_current_company),
    db: Session = Depends(get_db)
):
    try:
        shelters = db.query(ShelterModel).filter(ShelterModel.operator == company.name).all()
        return templates.TemplateResponse(
            "company-dashboard.html",
            {
                "request": request,
                "company": company,
                "shelters": shelters,
                "api_url": "/api",
                "ws_url": "ws://localhost:8000/ws/shelters" if os.getenv("ENV") == "local" else "wss://<your-service>.onrender.com/ws/shelters"
            }
        )
    except Exception as e:
        print(f"Error in company_dashboard_page: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Internal Server Error: {str(e)}")

@app.get("/logout", response_class=HTMLResponse)
async def logout_page(request: Request):
    response = templates.TemplateResponse("login.html", {"request": request})
    response.delete_cookie("token")
    response.delete_cookie("company_token")
    return response

@app.get("/api/geocode")
async def geocode_address(address: str):
    url = "https://map.yahooapis.jp/geocode/V1/geoCoder"
    params = {
        "appid": YAHOO_APPID,
        "query": address,
        "output": "json"
    }
    async with aiohttp.ClientSession() as session:
        async with session.get(url, params=params) as resp:
            text = await resp.text()
            print("Yahoo Geocode status:", resp.status)
            print("Yahoo Geocode body:", text)
            if resp.status != 200:
                raise HTTPException(status_code=502, detail=f"Yahoo API error: HTTP {resp.status}")
            data = await resp.json()
    if data.get("Feature") is None or not data["Feature"]:
        msg = data.get("Error", [{"Message": "住所が見つかりません"}])[0]["Message"]
        raise HTTPException(status_code=404, detail=f"Geocode failed: {msg}")
    lon, lat = map(float, data["Feature"][0]["Geometry"]["Coordinates"].split(","))
    return {"lat": lat, "lon": lon}

@app.get("/proxy")
async def proxy(url: str):
    try:
        resp = await client.get(url, timeout=10.0)
        resp.raise_for_status()
        return JSONResponse(status_code=200, content=resp.json())
    except httpx.HTTPStatusError as e:
        if e.response.status_code in (404, 502):
            return JSONResponse(status_code=200, content={"areaTypes": []})
        raise

@app.post("/api/photos/upload")
async def upload_photo_binary(
    file: UploadFile = File(...),
    db: Session = Depends(get_db)
):
    content = await file.read()
    stmt = insert(PhotoModel).values(
        filename=file.filename,
        content_type=file.content_type,
        data=content
    )
    db.execute(stmt)
    db.commit()
    return {"filename": file.filename, "id": stmt.inserted_primary_key}

@app.websocket("/ws/shelters")
async def websocket_endpoint(ws: WebSocket):
    await ws.accept()
    connected_clients.add(ws)
    try:
        while True:
            await ws.receive_text()
    except:
        connected_clients.discard(ws)

@app.get("/favicon.ico", response_class=FileResponse)
async def favicon():
    favicon_path = os.path.join("static", "favicon.ico")
    if os.path.exists(favicon_path):
        return FileResponse(favicon_path)
    return Response(status_code=204)