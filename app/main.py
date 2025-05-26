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
from sqlalchemy.orm import Session  # 同期セッション用
from datetime import datetime, timedelta
import xml.etree.ElementTree as ET
import os, json, uuid, traceback, aiohttp, httpx, io
from pydantic import ValidationError

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
    BulkUpdateRequest,
    CompanySchema
)

# --- 企業周りのRouter ---
from utils import router as company_router

app = FastAPI()

# スタートアップイベント
@app.on_event("startup")
def on_startup():
    print("Starting database initialization...")
    Base.metadata.create_all(bind=engine)  # テーブル作成
    with SessionLocal() as db:
        try:
            admin = db.query(CompanyModel).filter(CompanyModel.email == "admin@example.com").first()
            print(f"Admin check: {admin}")
            if not admin:
                hashed_pw = pwd_context.hash("admin123")
                admin = CompanyModel(
                    email="admin@example.com",
                    name="管理者",
                    hashed_pw=hashed_pw,
                    role="admin",
                    created_at=datetime.utcnow()
                )
                db.add(admin)
                db.commit()
                print("Admin account created successfully")
            else:
                print(f"Admin account exists: email={admin.email}, role={admin.role}")
        except Exception as e:
            print(f"Error creating admin account: {str(e)}")
            raise

# 企業登録／一覧 用 API をマウント
app.include_router(company_router)

# HTTP クライアント
client = httpx.Client()  # 同期クライアントに変更

# 環境変数から取得
YAHOO_APPID = os.getenv("YAHOO_APPID")
REG_PASS = os.getenv("REG_PASS")  # 認証パスワード
print(f"YAHOO_APPID: {YAHOO_APPID}")  # デバッグ: 環境変数確認
print(f"REG_PASS: {REG_PASS}")  # デバッグ: 環境変数確認
print(f"JWT_SECRET_KEY: {os.getenv('JWT_SECRET_KEY')[:10]}...")

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
SECRET_KEY = os.getenv("JWT_SECRET_KEY", "your-secure-secret-key")
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 30

# パスワードハッシュ用
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

# 認証方式
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="api/company-token")

# WebSocket接続管理
connected_clients: set[WebSocket] = set()

# トークン検証（企業または管理者）
def get_current_user(token: str = Depends(oauth2_scheme), db: Session = Depends(get_db)):
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="トークンが無効です",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        print(f"Received token: {token[:10]}...")  # デバッグ: トークンの先頭10文字
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        email: str = payload.get("sub")
        role: str = payload.get("role")
        exp: int = payload.get("exp")
        print(f"Decoded payload: sub={email}, role={role}, exp={exp}")  # デバッグ: ペイロード詳細
        print(f"Checking conditions: email={email}, role in ['company', 'admin']={role in ['company', 'admin']}")  # デバッグ: 条件チェック
        if email is None or role not in ["company", "admin"]:
            print(f"Invalid email or role: email={email}, role={role}")
            raise credentials_exception
        if exp is None or datetime.utcnow().timestamp() > exp:
            print(f"Token expired: exp={exp}, current={datetime.utcnow().timestamp()}")
            raise credentials_exception
        company = db.query(CompanyModel).filter(CompanyModel.email == email).first()
        print(f"Company query result: {company}")  # デバッグ: クエリ結果
        if company is None:
            print(f"No company found for email: {email}")
            raise credentials_exception
        print(f"Authenticated user: email={company.email}, role={company.role}, id={company.id}")  # デバッグ: 認証成功
        return company
    except JWTError as e:
        print(f"JWT decode error: {str(e)}")
        raise credentials_exception

# 企業トークン生成エンドポイント（管理者も対応）
@app.post("/api/company-token")
def create_company_access_token(
    form_data: OAuth2PasswordRequestForm = Depends(),
    db: Session = Depends(get_db)
):
    print(f"Token request: username={form_data.username}")  # デバッグ: リクエスト情報
    company = db.query(CompanyModel).filter(CompanyModel.email == form_data.username).first()
    if not company:
        print(f"No company found for username: {form_data.username}")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="メールアドレスまたはパスワードが正しくありません",
            headers={"WWW-Authenticate": "Bearer"},
        )
    if not pwd_context.verify(form_data.password, company.hashed_pw):
        print(f"Password verification failed for username: {form_data.username}")
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
            "exp": access_token_expires
        },
        SECRET_KEY,
        algorithm=ALGORITHM
    )
    print(f"Token generated: sub={company.email}, role={company.role}, token={access_token[:10]}...")  # デバッグ: トークン生成
    return {"access_token": access_token, "token_type": "bearer"}

# ログアクション関数
def log_action(db: Session, action: str, shelter_id: Optional[int] = None, user: str = "system"):
    db_log = AuditLogModel(
        action=action,
        shelter_id=shelter_id,
        user=user,
        timestamp=datetime.utcnow()
    )
    db.add(db_log)
    db.commit()

# WebSocketブロードキャスト（非同期のまま）
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
def register_page(request: Request):
    if not REG_PASS:
        raise HTTPException(status_code=500, detail="認証パスワードが設定されていません")
    return templates.TemplateResponse("register_auth.html", {"request": request})

@app.post("/register", response_class=HTMLResponse)
def register_auth(request: Request, auth_password: str = Form(...)):
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

# ログインエンドポイント
@app.post("/login", response_class=HTMLResponse)
def login_post(
    request: Request,
    username: str = Form(...),
    password: str = Form(...),
    db: Session = Depends(get_db)
):
    try:
        print(f"Login attempt: username={username}")  # デバッグ: ログイン試行
        shelters = []
        logs = []
        try:
            shelters = db.query(ShelterModel).all()
            logs = db.query(AuditLogModel).order_by(AuditLogModel.timestamp.desc()).limit(50).all()
        except Exception as e:
            print(f"Error fetching shelters/logs in login_post: {str(e)}")

        company = db.query(CompanyModel).filter(CompanyModel.email == username).first()
        if company and pwd_context.verify(password, company.hashed_pw):
            access_token_expires = datetime.utcnow() + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
            access_token = jwt.encode(
                {
                    "sub": company.email,
                    "role": company.role,
                    "exp": access_token_expires
                },
                SECRET_KEY,
                algorithm=ALGORITHM
            )
            print(f"Login successful: username={username}, role={company.role}, token={access_token[:10]}...")  # デバッグ: ログイン成功
            template_name = "admin.html" if company.role == "admin" else "company-dashboard.html"
            shelters_to_show = shelters if company.role == "admin" else [
                s for s in shelters if s.operator == company.name
            ]
            template_response = templates.TemplateResponse(
                template_name,
                {
                    "request": request,
                    "company": company,
                    "token": access_token,
                    "shelters": shelters_to_show,
                    "logs": logs if company.role == "admin" else [],
                    "api_url": "/api",
                    "ws_url": "ws://localhost:8000/ws/shelters" if os.getenv("ENV") == "local" else "wss://safeshelter.onrender.com/ws/shelters",
                    "YAHOO_APPID": os.getenv("YAHOO_APPID")
                }
            )
            template_response.set_cookie(key="token", value=access_token)
            return template_response

        print(f"Login failed: username={username}, company={company}")  # デバッグ: ログイン失敗
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

# 標準エンドポイント群
@app.get("/api/shelters", response_model=List[ShelterSchema])
def get_shelters(
    search: Optional[str] = None,
    db: Session = Depends(get_db)
):
    try:
        query = db.query(ShelterModel)
        if search:
            query = query.filter(ShelterModel.name.ilike(f"%{search}%"))
        shelters = query.all()
        return shelters
    except Exception as e:
        print(f"Error in get_shelters: {str(e)}")
        raise HTTPException(status_code=500, detail=f"避難所の取得に失敗しました: {str(e)}")

@app.post("/api/shelters", response_model=ShelterSchema)
def create_shelter(
    shelter: ShelterSchema,
    token: str = Depends(oauth2_scheme),
    db: Session = Depends(get_db)
):
    try:
        print(f"Shelter POST request: token={token[:10]}...")  # デバッグ: リクエスト情報
        print(f"Shelter data: {shelter.dict()}")  # デバッグ: 送信データ
        current_user = get_current_user(token, db)
        print(f"Creating shelter for user: email={current_user.email}, role={current_user.role}, id={current_user.id}")  # デバッグ: ユーザー情報
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
            company_id=current_user.id
        )
        db.add(db_s)
        db.commit()
        db.refresh(db_s)
        log_action(db, "create_shelter", db_s.id, current_user.email)
        print(f"Shelter created: id={db_s.id}, name={db_s.name}")  # デバッグ: 作成成功
        return db_s
    except Exception as e:
        print(f"Error creating shelter: {str(e)}")
        raise HTTPException(status_code=400, detail=f"避難所登録に失敗しました: {str(e)}")

@app.put("/api/shelters/{shelter_id}", response_model=ShelterSchema)
def update_shelter(
    shelter_id: int,
    shelter: ShelterUpdateSchema,
    token: str = Depends(oauth2_scheme),
    db: Session = Depends(get_db)
):
    try:
        db_s = db.query(ShelterModel).filter_by(id=shelter_id).first()
        if not db_s:
            raise HTTPException(404, "避難所が見つかりません")
        current_user = get_current_user(token, db)
        if db_s.company_id != current_user.id and current_user.role != "admin":
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="更新権限がありません")
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
        log_action(db, "update_shelter", shelter_id, current_user.email)
        return db_s
    except Exception as e:
        print(f"Error in update_shelter: {str(e)}")
        raise HTTPException(status_code=400, detail=f"避難所更新に失敗しました: {str(e)}")

@app.delete("/api/shelters/{shelter_id}")
def delete_shelter(
    shelter_id: int,
    token: str = Depends(oauth2_scheme),
    db: Session = Depends(get_db)
):
    try:
        db_shelter = db.query(ShelterModel).filter_by(id=shelter_id).first()
        if not db_shelter:
            raise HTTPException(status_code=404, detail="避難所が見つかりません")
        current_user = get_current_user(token, db)
        if db_shelter.company_id != current_user.id and current_user.role != "admin":
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="削除権限がありません")
        log_action(db, "delete", shelter_id, current_user.email)
        db.delete(db_shelter)
        db.commit()
        return {"message": "避難所を削除しました"}
    except Exception as e:
        print(f"Error in delete_shelter: {str(e)}")
        raise HTTPException(status_code=400, detail=f"避難所削除に失敗しました: {str(e)}")

@app.post("/api/shelters/bulk-update")
def bulk_update_shelters(
    request: BulkUpdateRequest,
    token: str = Depends(oauth2_scheme),
    db: Session = Depends(get_db)
):
    try:
        current_user = get_current_user(token, db)
        shelters = db.query(ShelterModel).filter(ShelterModel.id.in_(request.shelter_ids)).all()
        if not shelters:
            raise HTTPException(status_code=404, detail="避難所が見つかりません")
        for shelter in shelters:
            if shelter.company_id != current_user.id and current_user.role != "admin":
                raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="更新権限がありません")
            if request.status is not None:
                shelter.status = request.status
            if request.current_occupancy is not None:
                shelter.current_occupancy = request.current_occupancy
            shelter.updated_at = datetime.utcnow()
            log_action(db, "bulk_update", shelter.id, current_user.email)
        db.commit()
        return {"message": "避難所を一括更新しました"}
    except Exception as e:
        print(f"Error in bulk_update_shelters: {str(e)}")
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Internal Server Error: {str(e)}")

@app.post("/api/shelters/bulk-delete")
def bulk_delete_shelters(
    shelter_ids: List[int],
    token: str = Depends(oauth2_scheme),
    db: Session = Depends(get_db)
):
    try:
        current_user = get_current_user(token, db)
        shelters = db.query(ShelterModel).filter(ShelterModel.id.in_(shelter_ids)).all()
        if not shelters:
            raise HTTPException(status_code=404, detail="避難所が見つかりません")
        for shelter in shelters:
            if shelter.company_id != current_user.id and current_user.role != "admin":
                raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="削除権限がありません")
            log_action(db, "bulk_delete", shelter.id, current_user.email)
            db.delete(shelter)
        db.commit()
        return {"message": "避難所を一括削除しました"}
    except Exception as e:
        print(f"Error in bulk_delete_shelters: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Internal Server Error: {str(e)}")

@app.post("/api/shelters/upload-photo")
def upload_photo(
    shelter_id: int = Form(...),
    file: UploadFile = File(...),
    token: str = Depends(oauth2_scheme),
    db: Session = Depends(get_db)
):
    try:
        db_shelter = db.query(ShelterModel).filter(ShelterModel.id == shelter_id).first()
        if not db_shelter:
            raise HTTPException(status_code=404, detail="避難所が見つかりません")
        current_user = get_current_user(token, db)
        if db_shelter.company_id != current_user.id and current_user.role != "admin":
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="アップロード権限がありません")
        os.makedirs("app/data/photos", exist_ok=True)
        file_ext = file.filename.split(".")[-1]
        filename = f"{uuid.uuid4()}.{file_ext}"
        file_path = os.path.join("app/data/photos", filename)
        with open(file_path, "wb") as f:
            f.write(file.file.read())
        photo_url = f"/data/photos/{filename}"
        photos = db_shelter.photos.split(",") if db_shelter.photos else []
        photos.append(photo_url)
        db_shelter.photos = ",".join(photos)
        db.commit()
        log_action(db, "upload_photo", shelter_id, current_user.email)
        return {"photo_url": photo_url}
    except Exception as e:
        print(f"Error in upload_photo: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Internal Server Error: {str(e)}")

@app.post("/api/shelters/upload-photos")
def upload_photos(
    shelter_id: int = Form(...),
    files: List[UploadFile] = File(...),
    token: str = Depends(oauth2_scheme),
    db: Session = Depends(get_db),
):
    try:
        db_shelter = db.query(ShelterModel).filter(ShelterModel.id == shelter_id).first()
        if not db_shelter:
            raise HTTPException(404, "避難所が見つかりません")
        current_user = get_current_user(token, db)
        if db_shelter.company_id != current_user.id and current_user.role != "admin":
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="アップロード権限がありません")
        os.makedirs("app/data/photos", exist_ok=True)
        photo_urls = []
        for file in files:
            ext = file.filename.split(".")[-1]
            filename = f"{uuid.uuid4()}.{ext}"
            path = os.path.join("app/data/photos", filename)
            with open(path, "wb") as f:
                f.write(file.file.read())
            url = f"/data/photos/{filename}"
            photo_urls.append(url)
        existing = db_shelter.photos.split(",") if db_shelter.photos else []
        db_shelter.photos = ",".join(existing + photo_urls)
        db.commit()
        log_action(db, "upload_photos", shelter_id, current_user.email)
        return {"photo_urls": photo_urls}
    except Exception as e:
        print(f"Error in upload_photos: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Internal Server Error: {str(e)}")

@app.get("/api/photos/{photo_id}")
def get_photo(photo_id: int, db: Session = Depends(get_db)):
    row = db.query(PhotoModel.data, PhotoModel.content_type).filter(PhotoModel.id == photo_id).first()
    if not row:
        raise HTTPException(status_code=404, detail="Photo not found")
    data, content_type = row
    return StreamingResponse(io.BytesIO(data), media_type=content_type)

@app.get("/api/audit-logs", response_model=List[AuditLogSchema])
def get_audit_logs(db: Session = Depends(get_db)):
    try:
        logs = db.query(AuditLogModel).order_by(AuditLogModel.timestamp.desc()).all()
        return logs
    except Exception as e:
        print(f"Error in get_audit_logs: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Internal Server Error: {str(e)}")

def geocode_address(address: str):
    import requests
    response = requests.get(f"https://nominatim.openstreetmap.org/search?q={address}&format=json")
    if response.status_code == 200:
        data = response.json()
        if data:
            return float(data[0]["lat"]), float(data[0]["lon"])
    return 35.6762, 139.6503  # デフォルト: 東京

def fetch_weather_alerts():
    from datetime import datetime, timedelta
    cache_file = "app/data/alerts_cache.json"
    try:
        os.makedirs("app/data", exist_ok=True)
        if os.path.exists(cache_file):
            with open(cache_file, "r", encoding="utf-8") as f:
                cache = json.load(f)
                if datetime.fromisoformat(cache["timestamp"]) > datetime.utcnow() - timedelta(hours=1):
                    return cache["alerts"]
        import requests
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
                "area": str(area),
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

def get_area_bounds(area: str):
    bounds = {
        "東京都": [[35.5, 139.4], [35.9, 139.9]],
        "神奈川県": [[35.1, 139.0], [35.6, 139.7]]
    }
    return bounds.get(area, [[35.6762, 139.6503], [35.6762, 139.6503]])

@app.get("/api/disaster-alerts")
def get_disaster_alerts():
    return fetch_weather_alerts()

@app.get("/", response_class=HTMLResponse)
def read_root(request: Request, db: Session = Depends(get_db)):
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
        shelters = []
    alerts = fetch_weather_alerts()
    return templates.TemplateResponse(
        "index.html",
        {
            "request": request,
            "alerts": alerts,
            "shelters": shelters,
            "api_url": "/api",
            "ws_url": "ws://localhost:8000/ws/shelters" if os.getenv("ENV") == "local" else "wss://safeshelter.onrender.com/ws/shelters",
            "YAHOO_APPID": os.getenv("YAHOO_APPID")
        }
    )

@app.get("/login", response_class=HTMLResponse)
def login_page(request: Request):
    return templates.TemplateResponse("login.html", {"request": request})

@app.get("/admin")
def admin_page(
    request: Request,
    current_user: CompanyModel = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    try:
        if current_user.role != "admin":
            raise HTTPException(status_code=403, detail="管理者権限が必要です")
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
                "ws_url": "ws://localhost:8000/ws/shelters" if os.getenv("ENV") == "local" else "wss://safeshelter.onrender.com/ws/shelters",
                "YAHOO_APPID": os.getenv("YAHOO_APPID")
            }
        )
    except Exception as e:
        print(f"Error in admin_page: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Internal Server Error: {str(e)}")

@app.get("/company-dashboard")
def company_dashboard_page(
    request: Request,
    current_user: CompanyModel = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    try:
        shelters = db.query(ShelterModel).filter(ShelterModel.operator == current_user.name).all()
        token = request.cookies.get("token")
        if not token:
            return templates.TemplateResponse(
                "login.html",
                {"request": request, "error": "ログインしてください"}
            )
        return templates.TemplateResponse(
            "company-dashboard.html",
            {
                "request": request,
                "company": current_user,
                "shelters": shelters,
                "token": token,
                "api_url": "/api",
                "ws_url": "ws://localhost:8000/ws/shelters" if os.getenv("ENV") == "local" else "wss://safeshelter.onrender.com/ws/shelters",
                "YAHOO_APPID": os.getenv("YAHOO_APPID")
            }
        )
    except Exception as e:
        print(f"Error in company_dashboard_page: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Internal Server Error: {str(e)}")

@app.get("/logout", response_class=HTMLResponse)
def logout_page(request: Request):
    response = templates.TemplateResponse("login.html", {"request": request})
    response.delete_cookie("token")
    return response

@app.get("/api/geocode")
def geocode_address_endpoint(address: str):
    import requests
    url = "https://map.yahooapis.jp/geocode/V1/geoCoder"
    params = {
        "appid": YAHOO_APPID,
        "query": address,
        "output": "json"
    }
    resp = requests.get(url, params=params)
    print("Yahoo Geocode status:", resp.status_code)
    print("Yahoo Geocode body:", resp.text)
    if resp.status_code != 200:
        raise HTTPException(status_code=502, detail=f"Yahoo API error: HTTP {resp.status_code}")
    data = resp.json()
    if data.get("Feature") is None or not data["Feature"]:
        msg = data.get("Error", [{"Message": "住所が見つかりません"}])[0]["Message"]
        raise HTTPException(status_code=404, detail=f"Geocode failed: {msg}")
    lon, lat = map(float, data["Feature"][0]["Geometry"]["Coordinates"].split(","))
    return {"lat": lat, "lon": lon}

@app.get("/proxy")
def proxy(url: str):
    try:
        resp = client.get(url, timeout=10.0)
        resp.raise_for_status()
        return JSONResponse(status_code=200, content=resp.json())
    except httpx.HTTPStatusError as e:
        if e.response.status_code in (404, 502):
            return JSONResponse(status_code=200, content={"areaTypes": []})
        raise

@app.post("/api/photos/upload")
def upload_photo_binary(
    file: UploadFile = File(...),
    db: Session = Depends(get_db)
):
    from sqlalchemy import insert
    content = file.file.read()
    stmt = insert(PhotoModel).values(
        filename=file.filename,
        content_type=file.content_type,
        data=content
    )
    result = db.execute(stmt)
    db.commit()
    return {"filename": file.filename, "id": result.inserted_primary_key[0]}

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
def favicon():
    favicon_path = os.path.join("static", "favicon.ico")
    if os.path.exists(favicon_path):
        return FileResponse(favicon_path)
    return Response(status_code=204)