import os
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker

# データベースURL
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite+aiosqlite:///./dev.db").replace("postgres://", "postgresql+asyncpg://")
print(f"→ Using DATABASE_URL = {DATABASE_URL!r}")

# SQLiteの場合の設定
connect_args = {"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {}

# 非同期エンジン
engine = create_async_engine(
    DATABASE_URL,
    connect_args=connect_args,
    pool_pre_ping=True,
    echo=True  # デバッグ用
)

# 非同期セッション
AsyncSessionLocal = sessionmaker(
    autocommit=False,
    autoflush=False,
    bind=engine,
    class_=AsyncSession
)

Base = declarative_base()

# 非同期依存性
async def get_db():
    async with AsyncSessionLocal() as db:
        yield db