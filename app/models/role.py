from sqlalchemy import Column, Integer, String, Text, Boolean, DateTime
from sqlalchemy.sql import func
from app.database import Base

class Role(Base):
    __tablename__ = "roles"
    
    # 角色唯一識別碼
    id = Column(Integer, primary_key=True, autoincrement=True)
    
    # 角色代碼
    code = Column(String(50), unique=True, index=True, nullable=False)
    
    # 角色名稱
    name = Column(String(100), nullable=False)
    
    # 角色說明
    description = Column(Text, nullable=True)
    
    # 是否為系統內建角色(不可刪除)
    is_system = Column(Boolean, default=False)
    
    # 建立時間
    created_at = Column(DateTime, server_default=func.now(), nullable=False)
    
    # 更新時間
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now(), nullable=False)