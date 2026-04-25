import sys
import os
import logging
import asyncio
import io
import csv

# アプリケーションのパスを通す
sys.path.append(os.getcwd())

from app import models, database
from sqlalchemy.orm import Session
from sqlalchemy import text

# ロギング設定
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

async def debug_process():
    db = next(database.get_db())
    
    # EDINETコードのインポート
    edinet_csv_path = "docs/edinet_data/EdinetcodeDlInfo.csv"
    # ファンドコードのインポート
    fund_csv_path = "docs/edinet_data/FundcodeDlInfo.csv"
    
    def safe_int(val):
        try:
            return int(val) if val and val.strip() else None
        except (ValueError, TypeError):
            return None

    def process_csv_contents(contents):
        encoding = "unknown"
        if contents[:3] == b'\xef\xbb\xbf': # UTF-8 BOM
            text = contents[3:].decode('utf-8')
            encoding = "utf-8-bom"
        elif contents[:3] == b'\x9c\x5b\x57': 
            text = contents[3:].decode('cp932')
            encoding = "cp932-bom"
        else:
            try:
                text = contents.decode('cp932')
                encoding = "cp932"
            except UnicodeDecodeError:
                text = contents.decode('utf-8', errors='replace')
                encoding = "utf-8-replaced"
        
        logger.info(f"Detected encoding: {encoding}")
        reader = csv.reader(io.StringIO(text))
        return list(reader)

    def import_edinet_codes():
        if not os.path.exists(edinet_csv_path):
            logger.warning(f"File not found: {edinet_csv_path}")
            return 0

        with open(edinet_csv_path, "rb") as f:
            contents = f.read()
        
        rows = process_csv_contents(contents)
        logger.info(f"Edinet CSV read complete. Total rows: {len(rows)}")
        if len(rows) < 2:
            return 0

        data_rows = rows[2:]
        logger.info("Deleting existing EdinetCode records...")
        db.execute(text("DELETE FROM edinet_codes"))
        db.commit()

        count = 0
        objects = []
        for row in data_rows:
            if len(row) < 13: continue
            edinet_code = row[0].strip() if row[0] else None
            if not edinet_code: continue

            objects.append({
                "edinet_code": edinet_code,
                "submitter_type": row[1].strip() if len(row) > 1 and row[1] else None,
                "listing_status": row[2].strip() if len(row) > 2 and row[2] else None,
                "consolidated": row[3].strip() if len(row) > 3 and row[3] else None,
                "capital": safe_int(row[4]) if len(row) > 4 else None,
                "settlement_date": row[5].strip() if len(row) > 5 and row[5] else None,
                "filer_name": row[6].strip() if len(row) > 6 and row[6] else None,
                "filer_name_en": row[7].strip() if len(row) > 7 and row[7] else None,
                "filer_name_kana": row[8].strip() if len(row) > 8 and row[8] else None,
                "address": row[9].strip() if len(row) > 9 and row[9] else None,
                "industry": row[10].strip() if len(row) > 10 and row[10] else None,
                "sec_code": row[11].strip() if len(row) > 11 and row[11] else None,
                "jcn": row[12].strip() if len(row) > 12 and row[12] else None,
            })
            count += 1
            if count % 1000 == 0:
                db.bulk_insert_mappings(models.EdinetCode, objects)
                db.commit()
                objects = []
                logger.info(f"Inserted {count} EdinetCode records...")
        
        if objects:
            db.bulk_insert_mappings(models.EdinetCode, objects)
            db.commit()
        
        return count

    def import_fund_codes():
        if not os.path.exists(fund_csv_path):
            logger.warning(f"File not found: {fund_csv_path}")
            return 0

        with open(fund_csv_path, "rb") as f:
            contents = f.read()
        
        rows = process_csv_contents(contents)
        logger.info(f"Fund CSV read complete. Total rows: {len(rows)}")
        if len(rows) < 2:
            return 0

        data_rows = rows[2:]
        logger.info(f"First data row preview: {data_rows[0] if data_rows else 'EMPTY'}")
        logger.info("Deleting existing FundCode records...")
        db.execute(text("DELETE FROM fund_codes"))
        db.commit()

        count = 0
        objects = []
        for row in data_rows:
            if len(row) < 8: continue
            fund_code = row[0].strip() if row[0] else None
            if not fund_code: continue

            objects.append({
                "fund_code": fund_code,
                "sec_code": row[1].strip() if len(row) > 1 and row[1] else None,
                "fund_name": row[2].strip() if len(row) > 2 and row[2] else None,
                "fund_name_kana": row[3].strip() if len(row) > 3 and row[3] else None,
                "security_type": row[4].strip() if len(row) > 4 and row[4] else None,
                "period_1": row[5].strip() if len(row) > 5 and row[5] else None,
                "period_2": row[6].strip() if len(row) > 6 and row[6] else None,
                "edinet_code": row[7].strip() if len(row) > 7 and row[7] else None,
                "issuer_name": row[8].strip() if len(row) > 8 and row[8] else None,
            })
            count += 1
            if count % 1000 == 0:
                db.bulk_insert_mappings(models.FundCode, objects)
                db.commit()
                objects = []
                logger.info(f"Inserted {count} FundCode records...")
        
        if objects:
            db.bulk_insert_mappings(models.FundCode, objects)
            db.commit()
        
        return count

    def run_all():
        try:
            logger.info("DEBUG: Starting run_all execution")
            # EdinetCodeの処理は不要
            edinet_count = 0

            logger.info("Starting FundCode import...")
            fund_count = import_fund_codes()
            logger.info(f"FundCode import finished: {fund_count} records")

            logger.info("Committing final transaction...")
            db.commit()
            logger.info("Success!")
            return edinet_count, fund_count
        except Exception as e:
            logger.error(f"Error during import: {str(e)}")
            db.rollback()
            raise e

    try:
        results = await asyncio.to_thread(run_all)
        print(f"Import Summary: EdinetCodes={results[0]}, FundCodes={results[1]}")
    except Exception as e:
        print(f"Failed: {str(e)}")
    finally:
        db.close()

if __name__ == "__main__":
    asyncio.run(debug_process())
