from sqlalchemy import Column, Integer, String, Enum, DateTime, ForeignKey
from sqlalchemy.sql import func
from app.database import Base
import enum

# 權限範圍類型
class ScopeType(str, enum.Enum):
    GLOBAL = "global"           # 全域權限
    DEPARTMENT = "department"   # 限定部門


class UserRole(Base):
    """
    使用者-角色關聯表

    一個使用者可以有多個角色，一個角色可以給多個使用者
    這是多對多關係的中間表
    """
    __tablename__ = "user_roles"

    # 記錄唯一識別碼
    id = Column(Integer, primary_key=True, autoincrement=True)

    # 使用者 ID（外鍵）
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False)

    # 角色 ID（外鍵）
    role_id = Column(Integer, ForeignKey("roles.id", ondelete="CASCADE"), index=True, nullable=False)

    # 權限範圍類型（global=全域, department=限定部門）
    scope_type = Column(Enum(ScopeType), default=ScopeType.GLOBAL, nullable=False)

    # 限定部門 ID（0 表示全域，不限定部門）
    scope_department_id = Column(Integer, index=True, nullable=False, default=0)

    # 指派者（誰給這個使用者這個角色的）
    assigned_by = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), index=True, nullable=True)

    # 建立時間
    created_at = Column(DateTime, server_default=func.now(), nullable=False)
