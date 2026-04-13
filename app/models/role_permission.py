from sqlalchemy import Column, Integer, DateTime, ForeignKey, PrimaryKeyConstraint
from sqlalchemy.sql import func
from app.database import Base


class RolePermission(Base):
    """
    角色-權限關聯表（純橋接表）

    一個角色可以有多個權限，一個權限可以給多個角色
    使用複合主鍵（role_id + permission_id），不需要獨立 id
    """
    __tablename__ = "role_permissions"

    # 角色 ID（複合主鍵之一）
    role_id = Column(Integer, ForeignKey("roles.id", ondelete="CASCADE"), nullable=False)

    # 權限 ID（複合主鍵之一）
    permission_id = Column(Integer, ForeignKey("permissions.id", ondelete="CASCADE"), nullable=False)

    # 建立時間
    created_at = Column(DateTime, server_default=func.now(), nullable=False)

    # 複合主鍵：確保同一權限不會重複授予同一角色
    __table_args__ = (
        PrimaryKeyConstraint("role_id", "permission_id"),
    )
