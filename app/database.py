from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker, declarative_base
from app.config import settings


is_sqlite = settings.DATABASE_URL.startswith("sqlite")
connect_args = {"check_same_thread": False} if is_sqlite else {}

engine = create_engine(settings.DATABASE_URL, connect_args=connect_args)

if is_sqlite:
    @event.listens_for(engine, "connect")
    def enable_sqlite_fk(dbapi_connection, connection_record):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


def get_db():
    """依賴注入：提供資料庫 Session，請求結束後自動關閉"""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
