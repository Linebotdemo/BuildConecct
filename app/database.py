import os
from sqlalchemy import create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker

# データベースURL
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./dev.db")
if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql+psycopg2://")
elif DATABASE_URL.startswith("postgresql://"):
    DATABASE_URL = DATABASE_URL.replace("postgresql://", "postgresql+psycopg2://")
print(f"→ Using DATABASE_URL = {DATABASE_URL!r}")

# SQLiteの場合の設定
connect_args = {"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {}

# 同期エンジン
engine = create_engine(
    DATABASE_URL,
    connect_args=connect_args,
    pool_pre_ping=True,
    echo=True  # デバッグ用
)

# 同期セッション
SessionLocal = sessionmaker(
    autocommit=False,
    autoflush=False,
    bind=engine
)

Base = declarative_base()

# 同期依存性
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()