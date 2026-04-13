from sqlalchemy import Column, Integer, String, DateTime, ForeignKey, Enum
from sqlalchemy.sql import func
import enum
from app.database import Base
from sqlalchemy.orm import relationship


class UserStatus(str, enum.Enum):
    active = "active"
    inactive = "inactive"
    suspended = "suspended"


class User(Base):
    __tablename__ = "users"

    # 基本資訊
    id = Column(Integer, primary_key=True, autoincrement=True)
    employee_id = Column(String(20), unique=True, nullable=True)
    email = Column(String(255), unique=True, index=True, nullable=False)
    password_hash = Column(String(60), nullable=False)
    name = Column(String(100), nullable=False)
    avatar_url = Column(String(500), nullable=True)

    # 組織資訊
    department_id = Column(
        Integer,
        ForeignKey("departments.id", ondelete="SET NULL"),
        index=True,
        nullable=True,
    )
    job_title = Column(String(100), nullable=True)
    phone = Column(String(20), nullable=True)

    # 帳號狀態
    status = Column(Enum(UserStatus), default=UserStatus.active, nullable=False)
    failed_login_count = Column(Integer, default=0, nullable=False)
    locked_until = Column(DateTime, nullable=True)

    # 登入紀錄
    last_login_at = Column(DateTime, nullable=True)
    last_login_ip = Column(String(45), nullable=True)
    password_changed_at = Column(DateTime, nullable=True)

    # 審計資訊
    created_by = Column(
        Integer,
        ForeignKey("users.id", ondelete="SET NULL"),
        index=True,
        nullable=True
    )
    created_at = Column(DateTime, server_default=func.now(), nullable=False)
    updated_at = Column(
        DateTime, server_default=func.now(), onupdate=func.now(), nullable=False
    )
    
    # ==================== 關聯設定 ====================
    documents = relationship(
        "Document", 
        back_populates="uploader", 
        foreign_keys="Document.uploader_id"
    )
    
    created_tags = relationship(
        "Tag", 
        back_populates="creator"
    )
    
    search_history = relationship(
        "SearchHistory", 
        back_populates="user",
        cascade="all, delete-orphan"
    )