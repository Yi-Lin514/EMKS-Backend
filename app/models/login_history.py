from sqlalchemy import Column, Integer, String, DateTime, ForeignKey, Enum as SQLEnum
from sqlalchemy.sql import func
from app.database import Base
import enum


class LoginStatus(str, enum.Enum):
    """登入狀態的列舉"""
    SUCCESS = "success"
    FAILED = "failed"


class LoginHistory(Base):
    """
    登入歷史記錄表

    每次登入嘗試（無論成功或失敗）都會寫入一筆記錄
    用於安全稽核和使用者行為追蹤
    """
    __tablename__ = "login_history"

    # 記錄唯一識別碼
    id = Column(Integer, primary_key=True, autoincrement=True)

    # 使用者 ID（帳號不存在時為 NULL）
    user_id = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)

    # 嘗試登入的 Email（即使帳號不存在也會記錄）
    attempted_email = Column(String(255), nullable=False)

    # 來源 IP 位址
    ip_address = Column(String(45), nullable=True)

    # 瀏覽器 User-Agent 字串
    user_agent = Column(String(500), nullable=True)

    # 裝置類型（desktop, mobile, tablet 等）
    device_type = Column(String(20), nullable=True)

    # 登入狀態：success 或 failed
    # values_callable 讓 SQLAlchemy 用 Enum 的 .value（小寫）對應 DB，而非預設的 .name（大寫）
    login_status = Column(
        SQLEnum(LoginStatus, values_callable=lambda enum_class: [e.value for e in enum_class]),
        nullable=False,
    )

    # 失敗原因（成功時為 NULL）
    failure_reason = Column(String(100), nullable=True)

    # 記錄建立時間
    created_at = Column(DateTime, server_default=func.now(), nullable=False)
