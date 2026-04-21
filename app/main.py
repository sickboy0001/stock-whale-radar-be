from fastapi import FastAPI, Depends, HTTPException, status, Request, Form
from fastapi.security import OAuth2PasswordRequestForm
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
from sqlalchemy.orm import Session
from datetime import timedelta, datetime
from typing import List, Optional
import os
import secrets
import httpx
from urllib.parse import urlencode

from . import models, schemas, auth, database

# データベースのテーブル作成
models.Base.metadata.create_all(bind=database.engine)

app = FastAPI(title="Stock Whale Radar API")

# 静的ファイルとテンプレートの設定
app.mount("/static", StaticFiles(directory="app/static"), name="static")
templates = Jinja2Templates(directory="app/templates")

# Google OAuth 設定
GOOGLE_CLIENT_ID = database.settings.AUTH_GOOGLE_ID
GOOGLE_CLIENT_SECRET = database.settings.AUTH_GOOGLE_SECRET
GOOGLE_AUTH_URL = "https://accounts.google.com/o/oauth2/auth"
GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token"
GOOGLE_USERINFO_URL = "https://www.googleapis.com/oauth2/v2/userinfo"
REDIRECT_URI = "http://localhost:8000/auth/google/callback"  # 本番環境では適切な URL に変更

# --- HTML Routes (SSR) ---
@app.get("/", response_class=HTMLResponse)
async def index_page(request: Request):
    """スタートページ（サインアウト後に表示）"""
    return templates.TemplateResponse(
        request=request, name="index.html", context={}
    )

@app.get("/dashboard", response_class=HTMLResponse)
async def dashboard(
    request: Request,
    current_user: Optional[models.User] = Depends(auth.get_current_user_optional),
):
    """ダッシュボードページ（ゲスト/ログインユーザー対応）"""
    return templates.TemplateResponse(
        request=request,
        name="dashboard.html",
        context={
            "request": request,
            "current_user": current_user,
            "is_guest": current_user is None,
        }
    )

@app.get("/login", response_class=HTMLResponse)
async def login_page(request: Request):
    """ログインページ"""
    return templates.TemplateResponse(
        request=request, name="login.html", context={}
    )

@app.get("/logout")
async def logout(request: Request):
    """サインアウト（セッションをクリアしてスタートページへ）"""
    response = RedirectResponse(url="/", status_code=status.HTTP_302_FOUND)
    response.delete_cookie("access_token")
    return response

# --- API Routes ---
@app.get("/api")
def read_api_root():
    return {"message": "Welcome to Stock Whale Radar API"}

# --- Authentication ---
@app.post("/auth/signup", response_model=schemas.User)
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

@app.post("/auth/login", response_model=schemas.Token)
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

@app.get("/auth/google")
async def google_login(request: Request):
    """Google OAuth ログイン開始"""
    if not GOOGLE_CLIENT_ID or not GOOGLE_CLIENT_SECRET:
        raise HTTPException(status_code=500, detail="Google OAuth is not configured")
    
    state = secrets.token_urlsafe(32)
    redirect_uri = str(request.url_for("google_callback"))
    
    # Google 認証 URL を構築
    params = {
        "client_id": GOOGLE_CLIENT_ID,
        "redirect_uri": redirect_uri,
        "response_type": "code",
        "scope": "openid email profile",
        "state": state,
        "access_type": "offline",
        "prompt": "consent"
    }
    
    auth_url = f"{GOOGLE_AUTH_URL}?{urlencode(params)}"
    return RedirectResponse(url=auth_url)

@app.get("/auth/google/callback")
async def google_callback(request: Request, code: str = None, state: str = None, db: Session = Depends(database.get_db)):
    """Google OAuth コールバック処理"""
    if not code:
        raise HTTPException(status_code=400, detail="Authorization code not provided")
    
    try:
        # トークン取得
        async with httpx.AsyncClient() as client:
            token_response = await client.post(
                GOOGLE_TOKEN_URL,
                data={
                    "client_id": GOOGLE_CLIENT_ID,
                    "client_secret": GOOGLE_CLIENT_SECRET,
                    "code": code,
                    "grant_type": "authorization_code",
                    "redirect_uri": str(request.url_for("google_callback"))
                }
            )
            token_data = token_response.json()
            
            if "access_token" not in token_data:
                raise HTTPException(status_code=400, detail="Failed to get access token")
            
            access_token = token_data["access_token"]
            
            # ユーザー情報取得
            user_info_response = await client.get(
                GOOGLE_USERINFO_URL,
                headers={"Authorization": f"Bearer {access_token}"}
            )
            user_info = user_info_response.json()
            
            email = user_info.get("email")
            name = user_info.get("name", email.split("@")[0])
            
            # ユーザーが存在するか確認
            user = db.query(models.User).filter(models.User.email == email).first()
            
            if not user:
                # 新規ユーザー作成
                hashed_password = auth.get_password_hash(secrets.token_urlsafe(32))
                user = models.User(
                    username=name.replace(" ", "_").lower(),
                    email=email,
                    hashed_password=hashed_password
                )
                db.add(user)
                db.commit()
                db.refresh(user)
            
            # アクセストークン発行
            access_token_expires = timedelta(minutes=database.settings.ACCESS_TOKEN_EXPIRE_MINUTES)
            jwt_token = auth.create_access_token(
                data={"sub": user.username}, expires_delta=access_token_expires
            )
            
            # ログイン後にリダイレクト
            response = RedirectResponse(url="/dashboard", status_code=status.HTTP_302_FOUND)
            response.set_cookie(
                key="access_token",
                value=jwt_token,
                httponly=True,
                max_age=access_token_expires.total_seconds(),
                path="/"
            )
            return response
            
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Google OAuth error: {str(e)}")

@app.post("/auth/logout")
async def api_logout():
    """API 用のサインアウト（トークン無効化はセッションベースのため簡易実装）"""
    return {"message": "Logged out successfully"}

# --- Users ---
@app.get("/users/me", response_model=schemas.User)
def read_users_me(current_user: models.User = Depends(auth.get_current_user)):
    return current_user

# --- Buckets ---
@app.get("/buckets", response_model=List[schemas.Bucket])
def read_buckets(
    db: Session = Depends(database.get_db),
    current_user: Optional[models.User] = Depends(auth.get_current_user_optional)
):
    if current_user is None:
        return []
    return db.query(models.Bucket).filter(models.Bucket.user_id == current_user.id).all()

@app.post("/buckets", response_model=schemas.Bucket)
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
