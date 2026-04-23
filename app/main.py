from fastapi import FastAPI, Depends, HTTPException, status, Request, Form, File, UploadFile
from fastapi.security import OAuth2PasswordRequestForm
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
from sqlalchemy.orm import Session
from sqlalchemy import delete
from datetime import timedelta, datetime
from typing import List, Optional
import os
import secrets
import httpx
from urllib.parse import urlencode
import csv
import io
import asyncio

from . import models, schemas, auth, database, google_auth

# データベースのテーブル作成
models.Base.metadata.create_all(bind=database.engine)

app = FastAPI(title="Stock Whale Radar API")

# ルーターの登録
app.include_router(google_auth.router)

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

@app.get("/edinetcode-dl-info", response_class=HTMLResponse)
async def edinetcode_dl_info_page(
    request: Request,
    db: Session = Depends(database.get_db),
    current_user: Optional[models.User] = Depends(auth.get_current_user_optional),
):
    """EdinetcodeDlInfo ページ"""
    edinet_codes = db.query(models.EdinetCode).all()
    return templates.TemplateResponse(
        request=request, name="edinetcode_dl_info.html", context={
            "edinet_codes": edinet_codes,
            "current_user": current_user,
        }
    )

@app.post("/edinetcode-dl-info/upload")
async def edinetcode_dl_info_upload(
    request: Request,
    file: UploadFile = File(...),
    db: Session = Depends(database.get_db),
    current_user: Optional[models.User] = Depends(auth.get_current_user_optional),
):
    """
    CSV ファイルをアップロードし、edinet_codes テーブルを更新する
    """
    if not file.filename.endswith('.csv'):
        raise HTTPException(status_code=400, detail="CSV ファイルのみ許可されます")

    # ファイル内容をメモリに読み込み（file.file を使用して同期読み取り）
    contents = file.file.read()

    # ブロッキング操作をスレッドプールで実行
    def process_and_save():
        try:
            # cp932 エンコーディングでデコード（BOM ありの場合も対応）
            if contents[:3] == b'\x9c\x5b\x57': # cp932 BOM
                text = contents[3:].decode('cp932')
            else:
                text = contents.decode('cp932', errors='replace')

            # CSV パース
            reader = csv.reader(io.StringIO(text))
            rows = list(reader)

            if len(rows) < 2:
                raise ValueError("CSV ファイルが空、または形式が正しくありません")

            # 1 行目（インデックス 1）が実際のヘッダー、0 行目はメタデータ
            # データは 2 行目（インデックス 2）から開始
            data_rows = rows[2:]

            # 既存のデータを削除
            db.query(models.EdinetCode).delete()

            # 新規データを挿入
            for row in data_rows:
                if len(row) < 13: # 必要なカラム数
                    continue

                # 空の値は None に変換
                def safe_int(val):
                    try:
                        return int(val) if val and val.strip() else None
                    except (ValueError, TypeError):
                        return None

                edinet_code = row[0].strip() if row[0] else None
                if not edinet_code:
                    continue

                edinet_code_obj = models.EdinetCode(
                    edinet_code=edinet_code,
                    submitter_type=row[1].strip() if len(row) > 1 and row[1] else None,
                    listing_status=row[2].strip() if len(row) > 2 and row[2] else None,
                    consolidated=row[3].strip() if len(row) > 3 and row[3] else None,
                    capital=safe_int(row[4]) if len(row) > 4 else None,
                    settlement_date=row[5].strip() if len(row) > 5 and row[5] else None,
                    filer_name=row[6].strip() if len(row) > 6 and row[6] else None,
                    filer_name_en=row[7].strip() if len(row) > 7 and row[7] else None,
                    filer_name_kana=row[8].strip() if len(row) > 8 and row[8] else None,
                    address=row[9].strip() if len(row) > 9 and row[9] else None,
                    industry=row[10].strip() if len(row) > 10 and row[10] else None,
                    sec_code=row[11].strip() if len(row) > 11 and row[11] else None,
                    jcn=row[12].strip() if len(row) > 12 and row[12] else None,
                )
                db.add(edinet_code_obj)

            db.commit()

            # 更新後のデータを取得
            return db.query(models.EdinetCode).all()

        except UnicodeDecodeError:
            db.rollback()
            raise ValueError("ファイルのエンコーディングが正しくありません。cp932 (Shift-JIS) 形式の CSV を使用してください。")
        except Exception as e:
            db.rollback()
            raise e

    try:
        # ブロッキング操作をスレッドプールで実行
        edinet_codes = await asyncio.to_thread(process_and_save)

        # テンプレートレンダリングもスレッドプールで実行
        response = await asyncio.to_thread(
            templates.TemplateResponse,
            request=request,
            name="edinetcode_dl_info.html",
            context={
                "edinet_codes": edinet_codes,
                "current_user": current_user,
                "upload_success": True,
                "upload_count": len(edinet_codes)
            }
        )
        return response

    except ValueError as e:
        if "エンコーディング" in str(e) or "形式が正しくありません" in str(e):
            raise HTTPException(status_code=400, detail=str(e))
        raise HTTPException(status_code=500, detail=f"アップロード中にエラーが発生しました：{str(e)}")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"アップロード中にエラーが発生しました：{str(e)}")

@app.get("/fundcode-dl-info", response_class=HTMLResponse)
async def fundcode_dl_info_page(
    request: Request,
    db: Session = Depends(database.get_db),
    current_user: Optional[models.User] = Depends(auth.get_current_user_optional),
):
    """FundcodeDlInfo ページ"""
    fund_codes = await asyncio.to_thread(lambda: db.query(models.FundCode).all())
    return templates.TemplateResponse(
        request=request, name="fundcode_dl_info.html", context={
            "fund_codes": fund_codes,
            "current_user": current_user,
        }
    )

@app.post("/fundcode-dl-info/upload")
async def fundcode_dl_info_upload(
    request: Request,
    file: UploadFile = File(...),
    db: Session = Depends(database.get_db),
    current_user: Optional[models.User] = Depends(auth.get_current_user_optional),
):
    """
    CSV ファイルをアップロードし、fund_codes テーブルを更新する
    """
    if not file.filename.endswith('.csv'):
        raise HTTPException(status_code=400, detail="CSV ファイルのみ許可されます")

    # ファイル内容をメモリに読み込み（file.file を使用して同期読み取り）
    contents = file.file.read()

    # ブロッキング操作をスレッドプールで実行
    def process_and_save():
        try:
            # cp932 エンコーディングでデコード（BOM ありの場合も対応）
            if contents[:3] == b'\x9c\x5b\x57': # cp932 BOM
                text = contents[3:].decode('cp932')
            else:
                text = contents.decode('cp932', errors='replace')

            # CSV パース
            reader = csv.reader(io.StringIO(text))
            rows = list(reader)

            if len(rows) < 2:
                raise ValueError("CSV ファイルが空、または形式が正しくありません")

            # 1 行目（インデックス 1）が実際のヘッダー、0 行目はメタデータ
            # データは 2 行目（インデックス 2）から開始
            data_rows = rows[2:]

            # 既存のデータを削除
            db.query(models.FundCode).delete()

            # 新規データを挿入
            for row in data_rows:
                if len(row) < 8: # 必要なカラム数
                    continue

                # 空の値は None に変換
                def safe_str(val):
                    return val.strip() if val and val.strip() else None

                fund_code = row[0].strip() if row[0] else None
                if not fund_code:
                    continue

                fund_code_obj = models.FundCode(
                    fund_code=fund_code,
                    sec_code=safe_str(row[1]) if len(row) > 1 else None,
                    fund_name=safe_str(row[2]) if len(row) > 2 else None,
                    fund_name_kana=safe_str(row[3]) if len(row) > 3 else None,
                    security_type=safe_str(row[4]) if len(row) > 4 else None,
                    period_1=safe_str(row[5]) if len(row) > 5 else None,
                    period_2=safe_str(row[6]) if len(row) > 6 else None,
                    edinet_code=safe_str(row[7]) if len(row) > 7 else None,
                    issuer_name=safe_str(row[8]) if len(row) > 8 else None,
                )
                db.add(fund_code_obj)

            db.commit()

            # 更新後のデータを取得
            return db.query(models.FundCode).all()

        except UnicodeDecodeError:
            db.rollback()
            raise ValueError("ファイルのエンコーディングが正しくありません。cp932 (Shift-JIS) 形式の CSV を使用してください。")
        except Exception as e:
            db.rollback()
            raise e

    try:
        # ブロッキング操作をスレッドプールで実行
        fund_codes = await asyncio.to_thread(process_and_save)

        # テンプレートレンダリングもスレッドプールで実行
        response = await asyncio.to_thread(
            templates.TemplateResponse,
            request=request,
            name="fundcode_dl_info.html",
            context={
                "fund_codes": fund_codes,
                "current_user": current_user,
                "upload_success": True,
                "upload_count": len(fund_codes)
            }
        )
        return response

    except ValueError as e:
        if "エンコーディング" in str(e) or "形式が正しくありません" in str(e):
            raise HTTPException(status_code=400, detail=str(e))
        raise HTTPException(status_code=500, detail=f"アップロード中にエラーが発生しました：{str(e)}")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"アップロード中にエラーが発生しました：{str(e)}")
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
