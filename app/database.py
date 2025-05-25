# database.py

import os
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./dev.db")
print(f"→ Using DATABASE_URL = {DATABASE_URL!r}")
from sqlalchemy import create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker

# 1️⃣ Read the URL from env, or default to a local SQLite file for dev.
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./dev.db")

# For SQLite only:
connect_args = {"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {}

engine = create_engine(
    DATABASE_URL,
    connect_args=connect_args,
    pool_pre_ping=True,
)

SessionLocal = sessionmaker(
    autocommit=False,
    autoflush=False,
    bind=engine,
)

Base = declarative_base()

# 2️⃣ Dependency you import elsewhere for DB sessions
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
