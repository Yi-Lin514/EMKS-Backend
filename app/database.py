from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base
from app.config import settings


engine = create_engine(settings.DATABASE_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


def get_db():
    """依賴注入：提供資料庫 Session，請求結束後自動關閉"""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
