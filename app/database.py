from sqlalchemy import create_engine, event
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
import os
from typing import Optional, Any
from pydantic_settings import BaseSettings
import libsql

class Settings(BaseSettings):
    DATABASE_URL: str = "sqlite:///./sql_app.db"
    DATABASE_AUTH_TOKEN: Optional[str] = None
    SECRET_KEY: str = "YOUR_SECRET_KEY"
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30

    # Google OAuth
    AUTH_GOOGLE_ID: Optional[str] = None
    AUTH_GOOGLE_SECRET: Optional[str] = None
    AUTH_SECRET: Optional[str] = None
    REDIRECT_URI: str = "http://localhost:8000/auth/google/callback"

    # External API
    EXTERNAL_API_URL: Optional[str] = None

    class Config:
        env_file = ".env"
        extra = "ignore"

settings = Settings()

# データベース接続 URL の構築
raw_db_url = settings.DATABASE_URL
db_url = ""

# Turso (libsql) の設定がある場合、接続プロトコルを https:// に変換
if raw_db_url:
    if raw_db_url.startswith("libsql://"):
        db_url = raw_db_url.replace("libsql://", "https://", 1)
    elif raw_db_url.startswith("wss://"):
        db_url = raw_db_url.replace("wss://", "https://", 1)
    else:
        db_url = raw_db_url
elif raw_db_url == "":
    db_url = "file:local.db"
else:
    db_url = "file:local.db"


class LibsqlConnectionWrapper:
    """
    libsql 接続オブジェクトをラップし、sqlite3 互換のメソッド (create_function など) を追加する。
    SQLAlchemy の SQLite ドライバが期待するインターフェースを提供する。
    """
    def __init__(self, conn: Any):
        self._conn = conn

    def __getattr__(self, name: str):
        # 存在しないメソッドはラップされた接続オブジェクトから取得
        return getattr(self._conn, name)

    def create_function(self, name: str, num_params: int, func: Any, deterministic: bool = False):
        """
        ダミー実装：SQLAlchemy が regexp などの関数を登録しようとするのを防ぐ。
        libsql はこのメソッドをサポートしていないため、何もしない。
        """
        pass

    def close(self):
        self._conn.close()

    def commit(self):
        self._conn.commit()

    def rollback(self):
        self._conn.rollback()

    def cursor(self):
        return self._conn.cursor()

    def execute(self, sql: str, parameters: Any = None):
        if parameters is not None:
            return self._conn.execute(sql, parameters)
        return self._conn.execute(sql)

    def executemany(self, sql: str, parameters: list):
        return self._conn.executemany(sql, parameters)


def get_libsql_connection():
    """libsql を使用した接続関数、ラッパーを返す"""
    if db_url.startswith("https://"):
        conn = libsql.connect(
            db_url,
            auth_token=settings.DATABASE_AUTH_TOKEN
        )
    elif db_url.startswith("file:") or "sqlite" in db_url:
        path = db_url.replace("file:", "").replace("sqlite:///", "./")
        conn = libsql.connect(path)
    else:
        conn = libsql.connect("file:local.db")
    
    return LibsqlConnectionWrapper(conn)


# SQLAlchemy エンジンの作成
engine = create_engine(
    "sqlite://",
    creator=get_libsql_connection,
    poolclass=StaticPool,
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
