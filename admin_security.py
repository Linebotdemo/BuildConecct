from config import settings
from fastapi import HTTPException
from fastapi.responses import JSONResponse
from database import SessionLocal
from models import Company
from auth import create_access_token

# ※admin_keyはフォーム等から渡される変数と仮定

def process_admin_security(admin_key: str):
    admin_key = admin_key.strip()
    admin_api_key = settings.ADMIN_API_KEY.strip()

    print("【DEBUG】入力されたadmin_key:", repr(admin_key))
    print("【DEBUG】設定値のADMIN_API_KEY:", repr(admin_api_key))

    if admin_key == admin_api_key:
        # 管理者の場合
        token = create_access_token(data={"sub": "admin", "company_id": None, "role": "admin"})
        print("【DEBUG】管理者トークン生成:", token)
        return JSONResponse(content={
            "access_token": token,
            "token_type": "bearer",
            "redirect_url": "/static/pages/admin_dashboard.html"
        })
    else:
        # 企業用APIキーとして照合
        db = SessionLocal()
        company = db.query(Company).filter(Company.api_key == admin_key).first()
        db.close()
        if company:
            # 企業の場合：subに企業名、company_id に企業のID、role を"admin"とする（※必要に応じ調整）
            token = create_access_token(data={"sub": company.company_name, "company_id": company.id, "role": "admin"})
            print("【DEBUG】企業トークン生成:", token)
            return JSONResponse(content={
                "access_token": token,
                "token_type": "bearer",
                "redirect_url": "/static/pages/project_management.html"
            })
        else:
            print("【DEBUG】無効なAPIキー:", admin_key)
            raise HTTPException(status_code=401, detail="無効な管理者APIキーです")
