from fastapi import APIRouter, Request, BackgroundTasks, Depends, Form, HTTPException, status
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from datetime import datetime, timedelta
import logging
import os
import httpx
import zipfile
import io
import time
import asyncio
import calendar
import traceback

from .. import models, schemas, database, auth
from ..utils import edinet_importer

router = APIRouter(prefix="/admin/import_daily_status", tags=["admin"])
test_router = APIRouter(prefix="/admin/test_import", tags=["admin_test"])
templates = Jinja2Templates(directory="app/templates")

logger = logging.getLogger(__name__)

EDINET_API_KEY = os.getenv("EDINET_API_KEY")

# --- 内部用ヘルパー：システムイベントの記録 ---
def log_system_event(db: Session, level: str, category: str, message: str, doc_id: str = None, error_details: str = None):
    try:
        event = models.SystemEvent(
            event_level=level,
            event_category=category,
            doc_id=doc_id,
            message=message,
            error_details=error_details
        )
        db.add(event)
        db.commit()
    except Exception as e:
        logger.error(f"Failed to log system event: {e}")

# --- 内部用：単一書類の取得と登録 ---
async def process_single_document(db: Session, doc_id: str, metadata: dict, job_id: str = None):
    """
    EDINET API から書類を取得し、インポーターを実行する
    """
    # タスクの作成または更新
    task = db.query(models.DocumentTask).filter(models.DocumentTask.doc_id == doc_id).first()
    if not task:
        task = models.DocumentTask(doc_id=doc_id, job_id=job_id, status='processing')
        db.add(task)
    else:
        task.job_id = job_id
        task.status = 'processing'
    db.commit()

    url = f"https://api.edinet-fsa.go.jp/api/v2/documents/{doc_id}"
    params = {"type": 1, "Subscription-Key": EDINET_API_KEY}
    
    try:
        async with httpx.AsyncClient() as client:
            headers = {"User-Agent": "Mozilla/5.0"}
            response = await client.get(url, params=params, headers=headers, timeout=60.0)
            
            if response.status_code != 200:
                error_msg = f"Failed to fetch document {doc_id}: HTTP {response.status_code}"
                logger.error(error_msg)
                task.status = 'failed'
                db.commit()
                log_system_event(db, "ERROR", "api_fetch", error_msg, doc_id=doc_id)
                return False
            
            content_type = response.headers.get("Content-Type", "")
            if "application/json" in content_type:
                error_data = response.json()
                logger.error(f"API Error for {doc_id}: {error_data}")
                task.status = 'failed'
                db.commit()
                log_system_event(db, "ERROR", "api_fetch", f"API Error: {error_data}", doc_id=doc_id)
                return False
            
            if "application/octet-stream" in content_type or "zip" in content_type:
                with zipfile.ZipFile(io.BytesIO(response.content)) as z:
                    xbrl_files = [f for f in z.namelist() if f.endswith('.xbrl')]
                    if xbrl_files:
                        with z.open(xbrl_files[0]) as f:
                            xbrl_content = f.read()
                            # インポーター呼び出し (edinet_importer 側でも task.status = 'completed' になる)
                            result = edinet_importer.import_document_to_db(
                                db, doc_id, xbrl_content, metadata, job_id
                            )
                            if result:
                                return True
            
            task.status = 'failed'
            db.commit()
            return False
    except Exception as e:
        logger.error(f"Error processing document {doc_id}: {e}")
        task.status = 'failed'
        db.commit()
        log_system_event(db, "ERROR", "xbrl_parse", str(e), doc_id=doc_id, error_details=traceback.format_exc())
        return False

# --- 裏で回す取り込み処理 ---
async def background_import_task(start_date: str, end_date: str, db_session_factory, include_completed: bool = False):
    """
    指定期間のインポートを実行するバックグラウンドタスク
    """
    db = db_session_factory()
    job_id = f"batch_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    
    # SyncJob の作成
    job = models.SyncJob(
        job_id=job_id,
        job_type="batch_sync",
        status="running",
        started_at=datetime.now()
    )
    db.add(job)
    db.commit()

    log_system_event(db, "INFO", "batch_sync", f"Batch sync started: {start_date} to {end_date}")

    try:
        # 日付リストの生成
        start = datetime.strptime(start_date, "%Y-%m-%d")
        end = datetime.strptime(end_date, "%Y-%m-%d")
        delta = end - start
        
        for i in range(delta.days + 1):
            target_date_obj = start + timedelta(days=i)
            target_date_str = target_date_obj.strftime("%Y-%m-%d")
            
            # ステータス行の取得・作成
            status_row = db.query(models.ImportDailyStatus).filter(
                models.ImportDailyStatus.target_date == target_date_str
            ).first()
            
            # すでに完了している場合のスキップ処理 (フラグがOFFの場合のみ)
            if not include_completed and status_row and status_row.status == 'completed':
                logger.info(f"Skip {target_date_str} as it is already completed")
                continue

            if not status_row:
                status_row = models.ImportDailyStatus(target_date=target_date_str)
                db.add(status_row)
            
            status_row.status = 'processing'
            status_row.last_run_start_at = datetime.now()
            db.commit()
            
            try:
                # 1. 書類一覧の取得
                list_url = "https://api.edinet-fsa.go.jp/api/v2/documents.json"
                params = {"date": target_date_str, "type": 2, "Subscription-Key": EDINET_API_KEY}
                
                async with httpx.AsyncClient() as client:
                    headers = {"User-Agent": "Mozilla/5.0"}
                    list_res = await client.get(list_url, params=params, headers=headers, timeout=30.0)
                    if list_res.status_code != 200:
                        raise Exception(f"List API Error: {list_res.status_code}")
                    
                    list_data = list_res.json()
                    all_docs = list_data.get("results", [])
                    
                    # 2. フィルタリング (大量保有報告書等)
                    target_docs = [
                        d for d in all_docs 
                        if d.get("ordinanceCode") == "060" or 
                        (d.get("docDescription") and "大量保有" in d.get("docDescription"))
                    ]
                    
                    status_row.total_docs_count = len(all_docs)
                    status_row.target_docs_count = len(target_docs)
                    status_row.success_count = 0
                    db.commit()
                    
                    job.total_docs_found += len(all_docs)
                    job.target_docs_count += len(target_docs)
                    db.commit()
                    
                    # 3. 順次取得・解析
                    for doc in target_docs:
                        doc_id = doc.get("docID")
                        success = await process_single_document(db, doc_id, doc, job_id)
                        if success:
                            status_row.success_count += 1
                            job.success_count += 1
                        else:
                            job.error_count += 1
                        db.commit()
                        # API 負荷軽減
                        await asyncio.sleep(0.5)
                
                status_row.status = 'completed'
                status_row.last_run_end_at = datetime.now()
                db.commit()
                
            except Exception as e:
                logger.error(f"Error processing {target_date_str}: {e}")
                status_row.status = 'failed'
                status_row.error_message = str(e)
                status_row.last_run_end_at = datetime.now()
                db.commit()
                log_system_event(db, "ERROR", "batch_sync", f"Error on {target_date_str}: {e}", error_details=traceback.format_exc())

        job.status = "success"
        job.finished_at = datetime.now()
        db.commit()
        log_system_event(db, "INFO", "batch_sync", f"Batch sync completed: {job_id}")

    except Exception as e:
        logger.error(f"Fatal error in background task: {e}")
        job.status = "failed"
        job.finished_at = datetime.now()
        db.commit()
        log_system_event(db, "FATAL", "system", f"Fatal error in background sync: {e}", error_details=traceback.format_exc())
    finally:
        db.close()

# 管理者認証（クッキーからの認証に対応）
async def verify_admin(
    current_user: models.User = Depends(auth.get_current_user_optional)
):
    if not current_user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="ログインが必要です"
        )
    if not current_user.is_admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="管理者権限が必要です"
        )
    return current_user

# =========================================================
# 1. ダッシュボード画面表示 (Daily Status)
# =========================================================
@router.get("/", response_class=HTMLResponse)
async def admin_dashboard(
    request: Request, 
    db: Session = Depends(database.get_db),
    current_user: models.User = Depends(verify_admin)
):
    # 直近のログを取得
    recent_logs = db.query(models.ImportDailyStatus).order_by(
        models.ImportDailyStatus.target_date.desc()
    ).limit(30).all()
    
    # 今月の全ステータスを取得 (カレンダー表示用)
    today = datetime.now()
    first_day_of_month = today.replace(day=1).strftime("%Y-%m-%d")
    month_status_rows = db.query(models.ImportDailyStatus).filter(
        models.ImportDailyStatus.target_date >= first_day_of_month
    ).all()
    
    # テンプレートで使いやすいように辞書化
    month_status = {row.target_date: row.status for row in month_status_rows}
    
    # カレンダー描画用の日付リスト (1日〜末日)
    _, last_day = calendar.monthrange(today.year, today.month)
    days_in_month = []
    for i in range(1, last_day + 1):
        date_str = today.replace(day=i).strftime("%Y-%m-%d")
        days_in_month.append({
            "day": i,
            "date": date_str,
            "status": month_status.get(date_str, "pending")
        })
    
    return templates.TemplateResponse(
        request=request,
        name="admin_dashboard.html",
        context={
            "recent_logs": recent_logs,
            "days_in_month": days_in_month,
            "current_month": today.strftime("%Y年 %m月"),
            "current_user": current_user,
            "now": today,
            "timedelta": timedelta
        }
    )

@router.post("/import")
async def execute_import(
    background_tasks: BackgroundTasks,
    start_date: str = Form(...),
    end_date: str = Form(...),
    include_completed: str = Form(None),
    db: Session = Depends(database.get_db),
    current_user: models.User = Depends(verify_admin)
):
    # バックグラウンドタスクの追加
    is_include = include_completed == "on"
    background_tasks.add_task(
        background_import_task, 
        start_date, 
        end_date, 
        database.SessionLocal,
        is_include
    )
    
    msg = f"{start_date} から {end_date} のインポートを開始しました。"
    if is_include:
        msg += "（完了済みの日付も再取得します）"
    else:
        msg += "（未実施またはエラーの日付のみを対象にします）"
        
    return {"status": "success", "message": msg}

@router.post("/retry/{target_date}")
async def retry_import(
    target_date: str,
    background_tasks: BackgroundTasks,
    db: Session = Depends(database.get_db),
    current_user: models.User = Depends(verify_admin)
):
    # 個別再取得の場合は常に上書き(include_completed=True)扱いで実行
    background_tasks.add_task(
        background_import_task, 
        target_date, 
        target_date, 
        database.SessionLocal,
        True
    )
    return {"status": "success", "message": f"{target_date} の再取得を開始しました。"}

# =========================================================
# 2. 取り込みテスト画面 (統合版)
# =========================================================
@test_router.get("/", response_class=HTMLResponse)
async def test_import_page(
    request: Request,
    current_user: models.User = Depends(verify_admin)
):
    return templates.TemplateResponse(
        request=request,
        name="admin_test_import.html",
        context={
            "current_user": current_user,
            "today": datetime.now().strftime("%Y-%m-%d")
        }
    )

@test_router.get("/list_documents")
async def list_documents(
    date: str,
    current_user: models.User = Depends(verify_admin)
):
    url = f"https://api.edinet-fsa.go.jp/api/v2/documents.json"
    params = {
        "date": date,
        "type": 2, 
        "Subscription-Key": EDINET_API_KEY
    }
    
    try:
        async with httpx.AsyncClient() as client:
            headers = {"User-Agent": "Mozilla/5.0"}
            response = await client.get(url, params=params, headers=headers, timeout=30.0)
            if response.status_code != 200:
                return JSONResponse(status_code=response.status_code, content={"status": "error", "message": f"EDINET API Error ({response.status_code})"})
            data = response.json()
            results = data.get("results", [])
            return {"status": "success", "count": len(results), "documents": results}
    except Exception as e:
        return JSONResponse(status_code=500, content={"status": "error", "message": f"通信エラー: {str(e)}"})

@test_router.post("/import_document/{doc_id}")
async def import_document(
    doc_id: str,
    request: Request,
    db: Session = Depends(database.get_db),
    current_user: models.User = Depends(verify_admin)
):
    try:
        metadata = await request.json()
    except:
        metadata = {}

    url = f"https://api.edinet-fsa.go.jp/api/v2/documents/{doc_id}"
    params = {"type": 1, "Subscription-Key": EDINET_API_KEY}
    
    try:
        async with httpx.AsyncClient() as client:
            headers = {"User-Agent": "Mozilla/5.0"}
            response = await client.get(url, params=params, headers=headers, timeout=60.0)
            
            if response.status_code != 200:
                return JSONResponse(status_code=500, content={"status": "error", "message": f"書類取得失敗 (HTTP {response.status_code})"})
            
            content_type = response.headers.get("Content-Type", "")
            if "application/json" in content_type:
                return JSONResponse(status_code=500, content={"status": "error", "message": "APIエラー"})
            
            if "application/octet-stream" in content_type or "zip" in content_type:
                with zipfile.ZipFile(io.BytesIO(response.content)) as z:
                    xbrl_files = [f for f in z.namelist() if f.endswith('.xbrl')]
                    if xbrl_files:
                        with z.open(xbrl_files[0]) as f:
                            xbrl_content = f.read()
                            result = edinet_importer.import_document_to_db(
                                db, doc_id, xbrl_content, metadata, f"manual_{int(time.time())}"
                            )
                            
                            if result:
                                return {
                                    "status": "success",
                                    "steps": ["バイナリデータを取得しました", "XBRL ファイルを解析しました", "データベースへの登録・更新が成功しました。"],
                                    "preview": {
                                        "document": {
                                            "doc_id": result["document"].doc_id,
                                            "submitter_name": result["document"].submitter_name,
                                            "issuer_name": result["document"].issuer_name,
                                            "sec_code": result["document"].sec_code,
                                            "doc_description": result["document"].doc_description
                                        },
                                        "report": {
                                            "obligation_date": str(result["report"].obligation_date),
                                            "holding_ratio": result["report"].holding_ratio,
                                            "prev_holding_ratio": result["report"].prev_holding_ratio,
                                            "holding_purpose": result["report"].holding_purpose,
                                            "is_joint_holding": result["parsed"].get("is_joint_holding", 0)
                                        }
                                    },
                                    "debug": {"files": z.namelist()}
                                }
        return JSONResponse(status_code=500, content={"status": "error", "message": "解析失敗"})
    except Exception as e:
        return JSONResponse(status_code=500, content={"status": "error", "message": str(e)})

@test_router.post("/import_all")
async def import_all_for_date(
    background_tasks: BackgroundTasks,
    date: str = Form(...),
    current_user: models.User = Depends(verify_admin)
):
    """
    指定日の全書類（対象のみ）を一括インポートする（バックグラウンド実行）
    ※この操作は常に上書き（強制再取得）扱いで実行します
    """
    background_tasks.add_task(
        background_import_task, 
        date, 
        date, 
        database.SessionLocal,
        True
    )
    return {"status": "success", "message": f"{date} の一括インポートを開始しました。"}
