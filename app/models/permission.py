from sqlalchemy import Column, Integer, String, Text, DateTime
from sqlalchemy.sql import func
from app.database import Base

class Permission(Base):
    __tablename__ = "permissions"

    # 權限唯一識別碼
    id = Column(Integer, primary_key=True, autoincrement=True)

    # 權限代碼（格式：resource:action，如 user:create、document:view）
    code = Column(String(100), unique=True, index=True, nullable=False)

    # 權限名稱
    name = Column(String(100), nullable=False)

    # 資源類型（document, user, department, ai, system）
    resource = Column(String(50), index=True, nullable=False)

    # 操作類型（view, create, edit, delete, manage）
    action = Column(String(50), nullable=False)

    # 權限說明
    description = Column(Text, nullable=True)

    # 建立時間
    created_at = Column(DateTime, server_default=func.now(), nullable=False)

    # 更新時間
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now(), nullable=False)
