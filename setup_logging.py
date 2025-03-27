# setup_logging.py
import logging
from database import SessionLocal, engine, Base
import models
import schemas
import crud_user
from auth import get_password_hash
import sys

logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)
handler = logging.StreamHandler()
handler.setFormatter(logging.Formatter("%(asctime)s - %(levelname)s - %(message)s"))
logger.addHandler(handler)

db = SessionLocal()

try:
    Base.metadata.create_all(bind=engine)
    existing = crud_user.get_user_by_email(db, "k.inose0902@gmail.com")
    if existing:
        logger.info("既にSuperadmin アカウントが存在します: %s", existing.email)
        sys.exit(0)
    superadmin_data = schemas.UserCreate(
        email="k.inose0902@gmail.com",
        password="Suramudankui4",
        role="superadmin",
        company_id=None
    )
    superadmin_data.password = get_password_hash(superadmin_data.password)
    superadmin = crud_user.create_user(db, superadmin_data)
    logger.info("Superadmin アカウントが作成されました: %s", superadmin.email)
    logger.debug("登録されたユーザー情報: id=%s, email=%s, role=%s", superadmin.id, superadmin.email, superadmin.role)
except Exception as e:
    logger.error("エラーが発生しました: %s", e)
finally:
    db.close()
