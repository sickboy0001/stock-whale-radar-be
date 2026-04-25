from fastapi import FastAPI, Depends, status, Request
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.responses import HTMLResponse, RedirectResponse
from typing import Optional

from . import models, auth, database, google_auth
from .routers import admin_import, api, edinet_code

# データベースのテーブル作成
models.Base.metadata.create_all(bind=database.engine)

app = FastAPI(title="Stock Whale Radar API")

# ルーターの登録
app.include_router(google_auth.router)
app.include_router(admin_import.router)
app.include_router(admin_import.test_router)
app.include_router(api.router)
app.include_router(edinet_code.router)

# 静的ファイルとテンプレートの設定
app.mount("/static", StaticFiles(directory="app/static"), name="static")
templates = Jinja2Templates(directory="app/templates")

# --- HTML Routes (SSR) ---
@app.get("/", response_class=HTMLResponse)
async def index_page(
    request: Request,
    current_user: Optional[models.User] = Depends(auth.get_current_user_optional),
):
    """スタートページ（サインアウト後に表示）"""
    return templates.TemplateResponse(
        request=request,
        name="index.html",
        context={"current_user": current_user},
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
