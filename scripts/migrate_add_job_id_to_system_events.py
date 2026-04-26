"""
SystemEvent テーブルに job_id 列を追加するマイグレーションスクリプト
Turso (libSQL) 環境用 - ALTER TABLE を使用
"""
import os
import asyncio
from dotenv import load_dotenv
from libsql_client import create_client

load_dotenv()

DB_URL = os.getenv("DATABASE_URL")
AUTH_TOKEN = os.getenv("DATABASE_AUTH_TOKEN")

async def migrate_async():
    print("Starting migration: Adding job_id column to system_events table...")
    
    if not DB_URL or not AUTH_TOKEN:
        print("Error: DATABASE_URL or DATABASE_AUTH_TOKEN not found in .env")
        return
    
    client = create_client(url=DB_URL, auth_token=AUTH_TOKEN)
    
    try:
        # 1. 既存のカラム情報を取得
        result = await client.execute("PRAGMA table_info(system_events)")
        columns = result.rows
        column_names = [col[1] for col in columns]
        
        print(f"Existing columns: {column_names}")
        
        if 'job_id' in column_names:
            print("job_id column already exists. Migration not needed.")
            return
        
        # 2. ALTER TABLE で job_id 列を追加
        alter_sql = "ALTER TABLE system_events ADD COLUMN job_id TEXT"
        await client.execute(alter_sql)
        print("Added job_id column to system_events table")
        
        print("Migration completed successfully!")
        
    except Exception as e:
        print(f"Migration failed: {e}")
        raise
    finally:
        await client.close()

def migrate():
    asyncio.run(migrate_async())

if __name__ == "__main__":
    migrate()
