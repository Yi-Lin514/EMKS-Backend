from sqlalchemy import Column, Integer,String, DateTime, ForeignKey, Enum, Boolean
from sqlalchemy.sql import func
import enum
from app.database import Base

class UserTokenType(str, enum.Enum):
    refresh = "refresh"
    reset_password = "reset_password"
    email_verify = "email_verify"
    activation = "activation"

class UserToken(Base):
    __tablename__ = "user_tokens"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    
    # 關聯使用者
    user_id = Column(
        Integer,
        ForeignKey("users.id", ondelete="CASCADE"),
        index=True,
        nullable=False
        )
    
    # token 類型
    token_type = Column(Enum(UserTokenType),nullable=False)
    
    # token的 SHA-256 雜湊
    token_hash = Column(String(64), index=True, nullable=False)
    
    # 過期時間
    expires_at = Column(DateTime, nullable=False)
    
    # 是否已撤銷
    is_revoked = Column(Boolean, default=False, nullable=False)
    
    # 撤銷時間
    revoked_at = Column(DateTime, nullable=True)
    
    # 建立時間
    created_at = Column(DateTime, server_default=func.now(), nullable=False)