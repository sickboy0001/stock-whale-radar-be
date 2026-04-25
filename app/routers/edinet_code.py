from fastapi import APIRouter, Depends, HTTPException, Request, Form, File, UploadFile
from fastapi.templating import Jinja2Templates
from fastapi.responses import HTMLResponse
from sqlalchemy.orm import Session
import csv
import io
import asyncio
import logging
from typing import Optional

from .. import models, auth, database

router = APIRouter(tags=["edinet_code"])
templates = Jinja2Templates(directory="app/templates")
logger = logging.getLogger(__name__)

@router.get("/edinetcode-dl-info", response_class=HTMLResponse)
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

@router.post("/edinetcode-dl-info/upload")
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

    contents = await file.read()

    def process_and_save():
        try:
            logger.info("Starting CSV processing...")
            if contents[:3] == b'\x9c\x5b\x57': # cp932 BOM
                text = contents[3:].decode('cp932')
            else:
                text = contents.decode('cp932', errors='replace')

            reader = csv.reader(io.StringIO(text))
            rows = list(reader)
            logger.info(f"CSV read complete. Total rows: {len(rows)}")

            if len(rows) < 2:
                raise ValueError("CSV ファイルが空、または形式が正しくありません")

            data_rows = rows[2:]

            logger.info("Deleting existing EdinetCode records...")
            db.query(models.EdinetCode).delete()

            logger.info(f"Inserting {len(data_rows)} new records...")
            count = 0
            for row in data_rows:
                if len(row) < 13:
                    continue

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
                count += 1
                if count % 1000 == 0:
                    logger.info(f"Added {count} records...")

            logger.info("Committing transaction...")
            db.commit()
            logger.info("Transaction committed. Fetching all records...")
            all_records = db.query(models.EdinetCode).all()
            logger.info(f"Fetch complete. Returning {len(all_records)} records.")
            return all_records

        except UnicodeDecodeError as e:
            logger.error(f"UnicodeDecodeError: {str(e)}")
            db.rollback()
            raise ValueError("ファイルのエンコーディングが正しくありません。cp932 (Shift-JIS) 形式の CSV を使用してください。")
        except Exception as e:
            logger.error(f"Error in process_and_save: {str(e)}")
            db.rollback()
            raise e

    try:
        logger.info("Starting upload thread...")
        edinet_codes = await asyncio.to_thread(process_and_save)
        logger.info("Thread complete. Preparing response...")
        response = templates.TemplateResponse(
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
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"アップロード中にエラーが発生しました：{str(e)}")

@router.get("/fundcode-dl-info", response_class=HTMLResponse)
async def fundcode_dl_info_page(
    request: Request,
    db: Session = Depends(database.get_db),
    current_user: Optional[models.User] = Depends(auth.get_current_user_optional),
):
    """FundcodeDlInfo ページ"""
    fund_codes = db.query(models.FundCode).all()
    return templates.TemplateResponse(
        request=request, name="fundcode_dl_info.html", context={
            "fund_codes": fund_codes,
            "current_user": current_user,
        }
    )

@router.post("/fundcode-dl-info/upload")
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

    contents = await file.read()

    def process_and_save():
        try:
            if contents[:3] == b'\x9c\x5b\x57': # cp932 BOM
                text = contents[3:].decode('cp932')
            else:
                text = contents.decode('cp932', errors='replace')

            reader = csv.reader(io.StringIO(text))
            rows = list(reader)

            if len(rows) < 2:
                raise ValueError("CSV ファイルが空、または形式が正しくありません")

            data_rows = rows[2:]

            db.query(models.FundCode).delete()

            for row in data_rows:
                if len(row) < 8:
                    continue

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
            return db.query(models.FundCode).all()

        except UnicodeDecodeError:
            db.rollback()
            raise ValueError("ファイルのエンコーディングが正しくありません。cp932 (Shift-JIS) 形式の CSV を使用してください。")
        except Exception as e:
            db.rollback()
            raise e

    try:
        fund_codes = await asyncio.to_thread(process_and_save)
        response = templates.TemplateResponse(
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
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"アップロード中にエラーが発生しました：{str(e)}")
