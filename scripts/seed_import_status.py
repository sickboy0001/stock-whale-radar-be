from app.database import SessionLocal
from app import models
from datetime import datetime, timedelta

def seed_import_status():
    db = SessionLocal()
    try:
        # 管理者ユーザーの確認/作成 (テスト用)
        admin = db.query(models.User).filter(models.User.username == "admin").first()
        if not admin:
            print("Creating test admin user...")
            from app.auth import get_password_hash
            admin = models.User(
                username="admin",
                email="admin@example.com",
                hashed_password=get_password_hash("admin"),
                is_admin=1
            )
            db.add(admin)
            db.commit()

        # サンプルデータの投入
        print("Seeding import_daily_status...")
        today = datetime.now()
        
        statuses = [
            (today - timedelta(days=1), "completed", 15, 15),
            (today - timedelta(days=2), "completed", 20, 20),
            (today - timedelta(days=3), "failed", 5, 12, "EDINET API Timeout"),
            (today - timedelta(days=4), "completed", 10, 10),
            (today - timedelta(days=7), "pending", 0, 0),
        ]

        for date_obj, status, success, target, *error in statuses:
            date_str = date_obj.strftime("%Y-%m-%d")
            existing = db.query(models.ImportDailyStatus).filter(
                models.ImportDailyStatus.target_date == date_str
            ).first()
            
            if not existing:
                row = models.ImportDailyStatus(
                    target_date=date_str,
                    status=status,
                    success_count=success,
                    target_docs_count=target,
                    last_run_start_at=date_obj,
                    error_message=error[0] if error else None
                )
                db.add(row)
        
        db.commit()
        print("Done!")
    except Exception as e:
        print(f"Error: {e}")
        db.rollback()
    finally:
        db.close()

if __name__ == "__main__":
    seed_import_status()
