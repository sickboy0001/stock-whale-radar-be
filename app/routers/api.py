from fastapi import APIRouter, Depends, HTTPException, status, Request
from fastapi.security import OAuth2PasswordRequestForm
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session
from datetime import timedelta
from typing import List, Optional

from .. import models, schemas, auth, database

router = APIRouter(tags=["api"])

# --- API Routes ---
@router.get("/api")
def read_api_root():
    return {"message": "Welcome to Stock Whale Radar API"}

# --- Authentication ---
@router.post("/auth/signup", response_model=schemas.User)
def signup(user: schemas.UserCreate, db: Session = Depends(database.get_db)):
    db_user = db.query(models.User).filter(models.User.username == user.username).first()
    if db_user:
        raise HTTPException(status_code=400, detail="Username already registered")

    hashed_password = auth.get_password_hash(user.password)
    new_user = models.User(
        username=user.username,
        email=user.email,
        hashed_password=hashed_password
    )
    db.add(new_user)
    db.commit()
    db.refresh(new_user)
    return new_user

@router.post("/auth/login", response_model=schemas.Token)
def login(
    form_data: OAuth2PasswordRequestForm = Depends(),
    db: Session = Depends(database.get_db),
    request: Request = None
):
    user = db.query(models.User).filter(models.User.username == form_data.username).first()
    if not user or not auth.verify_password(form_data.password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    access_token_expires = timedelta(minutes=database.settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = auth.create_access_token(
        data={"sub": user.username}, expires_delta=access_token_expires
    )
    
    redirect_url = "/dashboard"
    
    if request:
        response = RedirectResponse(url=redirect_url, status_code=status.HTTP_302_FOUND)
        response.set_cookie(
            key="access_token",
            value=access_token,
            httponly=True,
            max_age=access_token_expires.total_seconds(),
            path="/"
        )
        return response
    
    return {"access_token": access_token, "token_type": "bearer"}

@router.post("/auth/logout")
async def api_logout():
    """API 用のサインアウト（トークン無効化はセッションベースのため簡易実装）"""
    return {"message": "Logged out successfully"}

# --- Users ---
@router.get("/users/me", response_model=schemas.User)
def read_users_me(current_user: models.User = Depends(auth.get_current_user)):
    return current_user

# --- Buckets ---
@router.get("/buckets", response_model=List[schemas.Bucket])
def read_buckets(
    db: Session = Depends(database.get_db),
    current_user: Optional[models.User] = Depends(auth.get_current_user_optional)
):
    if current_user is None:
        return []
    return db.query(models.Bucket).filter(models.Bucket.user_id == current_user.id).all()

@router.post("/buckets", response_model=schemas.Bucket)
def create_bucket(
    bucket: schemas.BucketCreate,
    db: Session = Depends(database.get_db),
    current_user: models.User = Depends(auth.get_current_user)
):
    new_bucket = models.Bucket(**bucket.dict(), user_id=current_user.id)
    db.add(new_bucket)
    db.commit()
    db.refresh(new_bucket)
    return new_bucket
