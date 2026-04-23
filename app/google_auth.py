import secrets
import httpx
from urllib.parse import urlencode
from datetime import timedelta
from fastapi import APIRouter, Depends, HTTPException, status, Request
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

from . import models, auth, database

router = APIRouter(prefix="/auth", tags=["auth"])

# Google OAuth 設定
GOOGLE_CLIENT_ID = database.settings.AUTH_GOOGLE_ID
GOOGLE_CLIENT_SECRET = database.settings.AUTH_GOOGLE_SECRET
GOOGLE_AUTH_URL = "https://accounts.google.com/o/oauth2/auth"
GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token"
GOOGLE_USERINFO_URL = "https://www.googleapis.com/oauth2/v2/userinfo"

@router.get("/google")
async def google_login(request: Request):
    """Google OAuth ログイン開始"""
    if not GOOGLE_CLIENT_ID or not GOOGLE_CLIENT_SECRET:
        raise HTTPException(status_code=500, detail="Google OAuth is not configured")
    
    state = secrets.token_urlsafe(32)
    # redirect_uri は固定値を使うか、request から動的に生成
    redirect_uri = database.settings.REDIRECT_URI
    
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

@router.get("/google/callback")
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
                    "redirect_uri": database.settings.REDIRECT_URI
                }
            )
            token_data = token_response.json()
            
            if "access_token" not in token_data:
                raise HTTPException(status_code=400, detail=f"Failed to get access token: {token_data.get('error_description', token_data.get('error', 'Unknown error'))}")
            
            access_token = token_data["access_token"]
            
            # ユーザー情報取得
            user_info_response = await client.get(
                GOOGLE_USERINFO_URL,
                headers={"Authorization": f"Bearer {access_token}"}
            )
            user_info = user_info_response.json()
            
            email = user_info.get("email")
            name = user_info.get("name", email.split("@")[0] if email else "google_user")
            
            if not email:
                raise HTTPException(status_code=400, detail="Failed to get email from Google")

            # ユーザーが存在するか確認
            user = db.query(models.User).filter(models.User.email == email).first()
            
            if not user:
                # 新規ユーザー作成
                # username が重複しないように調整
                base_username = name.replace(" ", "_").lower()
                username = base_username
                counter = 1
                while db.query(models.User).filter(models.User.username == username).first():
                    username = f"{base_username}_{counter}"
                    counter += 1
                
                hashed_password = auth.get_password_hash(secrets.token_urlsafe(32))
                user = models.User(
                    username=username,
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
                max_age=int(access_token_expires.total_seconds()),
                path="/"
            )
            return response
            
    except Exception as e:
        if isinstance(e, HTTPException):
            raise e
        raise HTTPException(status_code=500, detail=f"Google OAuth error: {str(e)}")
