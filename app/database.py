import os
import logging
from sqlalchemy import create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker

# ロギング設定
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)

# データベースURL
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./dev.db")
if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql+psycopg2://")
elif DATABASE_URL.startswith("postgresql://"):
    DATABASE_URL = DATABASE_URL.replace("postgresql://", "postgresql+psycopg2://")
logger.info("Using DATABASE_URL: %s", DATABASE_URL)

# SQLiteの場合の設定
connect_args = {"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {}

# 同期エンジン
engine = create_engine(
    DATABASE_URL,
    connect_args=connect_args,
    pool_size=10,  # 接続プールサイズ
    max_overflow=20,  # 超過時の追加接続数
    pool_timeout=30,  # 接続待機時間
    pool_pre_ping=True,  # 接続の健全性チェック
    echo=False,  # SQLログ（本番ではFalse）
)

# 同期セッション
SessionLocal = sessionmaker(
    autocommit=False,
    autoflush=False,
    bind=engine,
)

Base = declarative_base()

# 同期依存性
def get_db():
    db = SessionLocal()
    try:
        logger.debug("Database session opened")
        yield db
    except Exception as e:
        logger.error("Database session error: %s", str(e))
        raise
    finally:
        db.close()
        logger.debug("Database session closed")