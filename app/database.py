import os
from typing import Generator, Optional
from sqlalchemy import create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, Session
from pydantic_settings import BaseSettings
from dotenv import load_dotenv

load_dotenv()

class Settings(BaseSettings):
    DATABASE_URL: Optional[str] = "sqlite:///./test.db"
    DATABASE_AUTH_TOKEN: Optional[str] = None
    SECRET_KEY: str = "your-secret-key"
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30
    
    # Google OAuth
    AUTH_GOOGLE_ID: Optional[str] = None
    AUTH_GOOGLE_SECRET: Optional[str] = None
    REDIRECT_URI: str = "http://localhost:8000/auth/google/callback"

    class Config:
        env_file = ".env"
        extra = "ignore"

settings = Settings()

# SQLAlchemy engine setup
db_url = settings.DATABASE_URL

if db_url.startswith("libsql://"):
    # Turso (libSQL) handling
    import libsql
    
    class LibsqlConnectionWrapper:
        def __init__(self, conn):
            self.conn = conn
        def __getattr__(self, name):
            return getattr(self.conn, name)
        def create_function(self, *args, **kwargs):
            # SQLAlchemy's sqlite dialect calls this, but libsql doesn't support it.
            # We just ignore it.
            pass

    def create_libsql_conn():
        conn = libsql.connect(
            db_url, 
            auth_token=settings.DATABASE_AUTH_TOKEN
        )
        return LibsqlConnectionWrapper(conn)

    engine = create_engine(
        "sqlite://", 
        creator=create_libsql_conn
    )
elif not db_url:
    engine_url = "sqlite:///./local.db"
    engine = create_engine(
        engine_url,
        connect_args={"check_same_thread": False}
    )
else:
    engine = create_engine(
        db_url,
        connect_args={"check_same_thread": False} if db_url.startswith("sqlite") else {}
    )

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()

def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
