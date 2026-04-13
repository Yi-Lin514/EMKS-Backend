from sqlalchemy import Column, Integer, String, Text, DateTime, ForeignKey
from sqlalchemy.sql import func
from app.database import Base


class Department(Base):
    __tablename__ = "departments"
    
    # 部門唯一識別碼
    id = Column(Integer, primary_key=True, autoincrement=True)
    
    # 部門代碼
    code = Column(String(20), unique=True, index=True, nullable=False)
    
    # 部門名稱
    name = Column(String(100), nullable=False)
    
    # 部門職責說明
    description = Column(Text, nullable=True)
    
    # 上層部門(自我參照)
    parent_id = Column(
        Integer, 
        ForeignKey("departments.id", ondelete="SET NULL"),
        index=True,
        nullable=True
        )
    
    # 部門主管
    manager_id = Column(
        Integer,
        ForeignKey("users.id", ondelete="SET NULL"),
        index=True,
        nullable=True
        )
    
    # 部門層級(1=頂層)
    level = Column(Integer, nullable=False, default=1)
    
    # 同層排序順序
    sort_order = Column(Integer, default=0)
    
    # 建立時間
    created_at = Column(DateTime, server_default=func.now(), nullable=False)
    
    # 更新時間
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now(), nullable=False)