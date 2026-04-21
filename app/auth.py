from datetime import datetime, timedelta
from typing import Optional
from jose import JWTError, jwt
from passlib.context import CryptContext
from fastapi import Depends, HTTPException, status, Request
from fastapi.security import OAuth2PasswordBearer
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session
from . import models, schemas, database

# パスワードハッシュ化設定
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="auth/login", auto_error=False)

def verify_password(plain_password, hashed_password):
    return pwd_context.verify(plain_password, hashed_password)

def get_password_hash(password):
    return pwd_context.hash(password)

def create_access_token(data: dict, expires_delta: Optional[timedelta] = None):
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.utcnow() + expires_delta
    else:
        expire = datetime.utcnow() + timedelta(minutes=15)
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, database.settings.SECRET_KEY, algorithm=database.settings.ALGORITHM)
    return encoded_jwt

async def get_current_user(
    db: Session = Depends(database.get_db),
    token: Optional[str] = Depends(oauth2_scheme)
) -> models.User:
    """必須認証：トークンがない場合は 401 エラー"""
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    if token is None:
        raise credentials_exception
    try:
        payload = jwt.decode(token, database.settings.SECRET_KEY, algorithms=[database.settings.ALGORITHM])
        username: str = payload.get("sub")
        if username is None:
            raise credentials_exception
        token_data = schemas.TokenData(username=username)
    except JWTError:
        raise credentials_exception
    user = db.query(models.User).filter(models.User.username == token_data.username).first()
    if user is None:
        raise credentials_exception
    return user

async def get_current_user_optional(
    db: Session = Depends(database.get_db),
    request: Request = None
) -> Optional[models.User]:
    """任意認証：トークンがない場合は None を返す（ゲストモード）"""
    token = None
    
    # クッキーからトークンを取得
    if request and "access_token" in request.cookies:
        token = request.cookies["access_token"]
    
    # ヘッダーからトークンを取得（Bearer トークン）
    if not token and request:
        auth_header = request.headers.get("Authorization")
        if auth_header and auth_header.startswith("Bearer "):
            token = auth_header.split(" ")[1]
    
    # トークンがない場合はゲスト
    if token is None:
        return None
    
    try:
        payload = jwt.decode(token, database.settings.SECRET_KEY, algorithms=[database.settings.ALGORITHM])
        username: str = payload.get("sub")
        if username is None:
            return None
        token_data = schemas.TokenData(username=username)
    except JWTError:
        return None
    
    user = db.query(models.User).filter(models.User.username == token_data.username).first()
    if user is None:
        return None
    
    return user
