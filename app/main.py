from fastapi import FastAPI, HTTPException, Depends, File, UploadFile, WebSocket, Request, Form
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from fastapi.responses import HTMLResponse, Response, FileResponse
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from typing import List, Optional
from sqlalchemy.orm import Session
from database import SessionLocal, engine, Base
from models import Shelter as ShelterModel, AuditLog as AuditLogModel
from schemas import Shelter, ShelterUpdate, ShelterAttributes, AuditLog
from fastapi.middleware.cors import CORSMiddleware
import json
from datetime import datetime, timedelta
from websockets.exceptions import ConnectionClosed
import os
import aiohttp
import xml.etree.ElementTree as ET
import uuid

app = FastAPI()

app.mount("/static", StaticFiles(directory="static"), name="static")
app.mount("/data", StaticFiles(directory="app/data"), name="data")
templates = Jinja2Templates(directory="templates")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:8000", "https://<your-service>.onrender.com"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

Base.metadata.create_all(bind=engine)

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="api/token")

connected_clients = set()

@app.websocket("/ws/shelters")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    connected_clients.add(websocket)
    try:
        while True:
            await websocket.receive_text()
    except ConnectionClosed:
        connected_clients.remove(websocket)

async def broadcast_shelter_update(shelter: dict):
    # connected_clients のコピーを使ってループ
    for client in list(connected_clients):
        try:
            await client.send_text(json.dumps(shelter))
        except Exception:
            # remove ではなく discard() で安全に消す
            connected_clients.discard(client)

async def log_action(db: Session, action: str, shelter_id: Optional[int], user: str = "admin"):
    audit_log = AuditLogModel(
        action=action,
        shelter_id=shelter_id,
        user=user,
        timestamp=datetime.utcnow()
    )
    db.add(audit_log)
    db.commit()

@app.post("/api/token")
async def create_access_token(form_data: OAuth2PasswordRequestForm = Depends()):
    if form_data.username == "admin" and form_data.password == "admin123":
        return {"access_token": "dummy-token", "token_type": "bearer"}
    raise HTTPException(status_code=401, detail="ユーザー名またはパスワードが正しくありません")

@app.get("/api/shelters", response_model=List[Shelter])
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
        # --- 既存のフィルタ処理 ---
        if search:
            search = f"%{search.lower()}%"
            query = query.filter(
                (ShelterModel.name.ilike(search)) |
                (ShelterModel.address.ilike(search))
            )
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

        # --- ORMオブジェクトをPydantic期待形式のdictに変換 ---
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
                    "pets_allowed":      s.pets_allowed,
                    "barrier_free":      s.barrier_free,
                    "toilet_available":  s.toilet_available,
                    "food_available":    s.food_available,
                    "medical_available": s.medical_available,
                    "wifi_available":    s.wifi_available,
                    "charging_available":s.charging_available,
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


@app.post("/api/shelters", response_model=Shelter)
async def create_shelter(
    shelter: Shelter,
    token: str = Depends(oauth2_scheme),
    db: Session = Depends(get_db)
):
    # 1) 登録
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
        photos=",".join(shelter.photos),
        contact=shelter.contact,
        operator=shelter.operator,
        opened_at=shelter.opened_at,
        status=shelter.status,
        updated_at=datetime.utcnow()
    )
    db.add(db_shelter)
    db.commit()
    db.refresh(db_shelter)
    await log_action(db, "create", db_shelter.id)

    # 2) レスポンス用に dict を組み立て
    result = {
        "id":                 db_shelter.id,
        "name":               db_shelter.name,
        "address":            db_shelter.address,
        "latitude":           db_shelter.latitude,
        "longitude":          db_shelter.longitude,
        "capacity":           db_shelter.capacity,
        "current_occupancy":  db_shelter.current_occupancy,
        "attributes": {
            "pets_allowed":       db_shelter.pets_allowed,
            "barrier_free":       db_shelter.barrier_free,
            "toilet_available":   db_shelter.toilet_available,
            "food_available":     db_shelter.food_available,
            "medical_available":  db_shelter.medical_available,
            "wifi_available":     db_shelter.wifi_available,
            "charging_available": db_shelter.charging_available,
        },
        "photos": db_shelter.photos.split(",") if db_shelter.photos else [],    # ← ここで文字列をリスト化
        "contact":   db_shelter.contact,
        "operator":  db_shelter.operator,
        "opened_at": db_shelter.opened_at,
        "status":    db_shelter.status,
        "updated_at":db_shelter.updated_at
    }

    await broadcast_shelter_update(result)
    return result


@app.put("/api/shelters/{shelter_id}", response_model=Shelter)
async def update_shelter(shelter_id: int, shelter: ShelterUpdate, token: str = Depends(oauth2_scheme), db: Session = Depends(get_db)):
    try:
        db_shelter = db.query(ShelterModel).filter(ShelterModel.id == shelter_id).first()
        if not db_shelter:
            raise HTTPException(status_code=404, detail="避難所が見つかりません")
        update_data = shelter.dict(exclude_unset=True)
        if "attributes" in update_data:
            for key, value in update_data["attributes"].items():
                setattr(db_shelter, key, value)
            del update_data["attributes"]
        if "photos" in update_data:
            update_data["photos"] = ",".join(update_data["photos"])
        for key, value in update_data.items():
            setattr(db_shelter, key, value)
        db_shelter.updated_at = datetime.utcnow()
        db.commit()
        db.refresh(db_shelter)
        await log_action(db, "update", shelter_id)
        shelter_dict = db_shelter.__dict__
        shelter_dict["photos"] = shelter_dict["photos"].split(",") if shelter_dict["photos"] else []
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
        return shelter_dict
    except Exception as e:
        print(f"Error in update_shelter: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Internal Server Error: {str(e)}")

@app.delete("/api/shelters/{shelter_id}")
async def delete_shelter(shelter_id: int, token: str = Depends(oauth2_scheme), db: Session = Depends(get_db)):
    try:
        db_shelter = db.query(ShelterModel).filter(ShelterModel.id == shelter_id).first()
        if not db_shelter:
            raise HTTPException(status_code=404, detail="避難所が見つかりません")
        db.delete(db_shelter)
        db.commit()
        await log_action(db, "delete", shelter_id)
        await broadcast_shelter_update({"id": shelter_id, "deleted": True})
        return {"message": "避難所を削除しました"}
    except Exception as e:
        print(f"Error in delete_shelter: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Internal Server Error: {str(e)}")

class BulkUpdateRequest(BaseModel):
    shelter_ids: List[int]
    status: Optional[str] = None
    current_occupancy: Optional[int] = None

@app.post("/api/shelters/bulk-update")
async def bulk_update_shelters(request: BulkUpdateRequest, token: str = Depends(oauth2_scheme), db: Session = Depends(get_db)):
    try:
        shelters = db.query(ShelterModel).filter(ShelterModel.id.in_(request.shelter_ids)).all()
        if not shelters:
            raise HTTPException(status_code=404, detail="避難所が見つかりません")
        for shelter in shelters:
            if request.status:
                shelter.status = request.status
            if request.current_occupancy is not None:
                shelter.current_occupancy = request.current_occupancy
            shelter.updated_at = datetime.utcnow()
            await log_action(db, "bulk_update", shelter.id)
        db.commit()
        for shelter in shelters:
            shelter_dict = shelter.__dict__
            shelter_dict["photos"] = shelter_dict["photos"].split(",") if shelter_dict["photos"] else []
            shelter_dict["attributes"] = {
                "pets_allowed": shelter.pets_allowed,
                "barrier_free": shelter.barrier_free,
                "toilet_available": shelter.toilet_available,
                "food_available": shelter.food_available,
                "medical_available": shelter.medical_available,
                "wifi_available": shelter.wifi_available,
                "charging_available": shelter.charging_available
            }
            await broadcast_shelter_update(shelter_dict)
        return {"message": "避難所を一括更新しました"}
    except Exception as e:
        print(f"Error in bulk_update_shelters: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Internal Server Error: {str(e)}")

@app.post("/api/shelters/bulk-delete")
async def bulk_delete_shelters(shelter_ids: List[int], token: str = Depends(oauth2_scheme), db: Session = Depends(get_db)):
    try:
        shelters = db.query(ShelterModel).filter(ShelterModel.id.in_(shelter_ids)).all()
        if not shelters:
            raise HTTPException(status_code=404, detail="避難所が見つかりません")
        for shelter in shelters:
            db.delete(shelter)
            await log_action(db, "bulk_delete", shelter.id)
        db.commit()
        for shelter in shelters:
            await broadcast_shelter_update({"id": shelter.id, "deleted": True})
        return {"message": "避難所を一括削除しました"}
    except Exception as e:
        print(f"Error in bulk_delete_shelters: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Internal Server Error: {str(e)}")

@app.post("/api/shelters/upload-photo")
async def upload_photo(shelter_id: int = Form(...), file: UploadFile = File(...), token: str = Depends(oauth2_scheme), db: Session = Depends(get_db)):
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
        await log_action(db, "upload_photo", shelter_id)
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

@app.get("/api/audit-logs", response_model=List[AuditLog])
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
    cache_file = "app/data/alerts_cache.json"
    try:
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
    # ORM から生のオブジェクトを取ってくる
    shelters_orm = db.query(ShelterModel).all()

    # テンプレートに渡す前に dict のリストに変換
    shelters = []
    for s in shelters_orm:
        shelters.append({
            "id":               s.id,
            "name":             s.name,
            "address":          s.address,
            "capacity":         s.capacity,
            "current_occupancy":s.current_occupancy,
            "latitude":         s.latitude,
            "longitude":        s.longitude,
            "pets_allowed":     s.pets_allowed,
            "barrier_free":     s.barrier_free,
            "toilet_available": s.toilet_available,
            "food_available":   s.food_available,
            "medical_available":s.medical_available,
            "wifi_available":   s.wifi_available,
            "charging_available": s.charging_available,
            # ← ここで文字列を split して必ずリストに
            "photos":           s.photos.split(",") if s.photos else [],  
            "contact":          s.contact,
            "operator":         s.operator,
            "opened_at":        s.opened_at,
            "status":           s.status,
            "updated_at":       s.updated_at
        })

    alerts = await get_disaster_alerts()
    return templates.TemplateResponse(
        "index.html",
        {
            "request": request,
            "alerts":  alerts,
            "shelters":shelters,
            "api_url": "/api",
            "ws_url":  "ws://localhost:8000/ws/shelters"
        }
    )


@app.get("/login", response_class=HTMLResponse)
async def login_page(request: Request):
    return templates.TemplateResponse("login.html", {"request": request})

@app.post("/login", response_class=HTMLResponse)
async def login_post(request: Request, username: str = Form(...), password: str = Form(...)):
    try:
        response = await create_access_token(OAuth2PasswordRequestForm(username=username, password=password))
        token = response["access_token"]
        template_response = templates.TemplateResponse(
            "admin.html",
            {
                "request": request,
                "token": token,
                "api_url": "/api",
                "ws_url": "ws://localhost:8000/ws/shelters" if os.getenv("ENV") == "local" else "wss://<your-service>.onrender.com/ws/shelters"
            }
        )
        template_response.set_cookie(key="token", value=token)
        return template_response
    except HTTPException as e:
        return templates.TemplateResponse(
            "login.html",
            {"request": request, "error": f"ログインに失敗しました: {e.detail}"}
        )

@app.get("/admin", response_class=HTMLResponse)
async def admin_page(request: Request, db: Session = Depends(get_db)):
    try:
        token = request.cookies.get("token")
        if not token:
            return templates.TemplateResponse(
                "login.html",
                {"request": request, "error": "ログインしてください"}
            )
        shelters = db.query(ShelterModel).all()
        logs = db.query(AuditLogModel).order_by(AuditLogModel.timestamp.desc()).limit(50).all()
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

@app.get("/favicon.ico", response_class=FileResponse)
async def favicon():
    favicon_path = os.path.join("static", "favicon.ico")
    if os.path.exists(favicon_path):
        return FileResponse(favicon_path)
    return Response(status_code=204)