from datetime import datetime, timedelta
import logging
from typing import Optional
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from jose import JWTError, jwt
from passlib.context import CryptContext
from pydantic import BaseModel
from crud_user import get_user_by_email
from database import SessionLocal

logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)

ACCESS_TOKEN_EXPIRE_MINUTES = 180  # 3時間
SECRET_KEY = "your_super_secret_key_here"
ALGORITHM = "HS256"

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="token")

class Token(BaseModel):
    access_token: str
    token_type: str

class TokenData(BaseModel):
    email: Optional[str] = None
    company_id: Optional[int] = None
    role: Optional[str] = None

def verify_password(plain_password: str, hashed_password: str) -> bool:
    return pwd_context.verify(plain_password, hashed_password)

def get_password_hash(password: str) -> str:
    hashed = pwd_context.hash(password)
    logger.debug("Generated hash: %r", hashed)
    return hashed

def create_access_token(data: dict, expires_delta: Optional[timedelta] = None):
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.utcnow() + expires_delta
    else:
        expire = datetime.utcnow() + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    logger.debug("JWT generated with expiration=%s", expire)
    return encoded_jwt

async def get_current_user(token: str = Depends(oauth2_scheme)):
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="トークンの検証に失敗しました (期限切れなど)",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        email: str = payload.get("sub")
        company_id = payload.get("company_id")
        role = payload.get("role")
        if email is None:
            raise credentials_exception
        token_data = TokenData(email=email, company_id=company_id, role=role)
    except JWTError as e:
        logger.debug("JWT decoding error: %s", e)
        raise credentials_exception

    if token_data.email == "admin":
        return {"username": token_data.email, "company_id": token_data.company_id, "role": token_data.role}

    if token_data.role == "admin" and token_data.company_id is not None:
        return {"username": token_data.email, "company_id": token_data.company_id, "role": token_data.role}

    db = SessionLocal()
    try:
        user = get_user_by_email(db, token_data.email)
        if not user:
            logger.debug("User not found for token email: %s", token_data.email)
            raise credentials_exception
        return {"username": user.email, "company_id": user.company_id, "role": user.role}
    finally:
        db.close()
