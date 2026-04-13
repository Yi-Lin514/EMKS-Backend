from passlib.context import CryptContext
from datetime import datetime, timedelta
from jose import jwt, JWTError
from typing import Optional
from app.config import settings
import hashlib
from sqlalchemy.orm import Session
from app.models import UserToken, UserTokenType
import secrets
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from app.database import get_db
from app.models import User


pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

# OAuth2 設定:告訴fastapi從哪裡讀取token
oauth2_schema = OAuth2PasswordBearer(tokenUrl="/auth/login")


def hash_password(password: str) -> str:
    """將明文密碼加密成 hash"""
    return pwd_context.hash(password)


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """驗證密碼是否正確"""
    return pwd_context.verify(plain_password, hashed_password)


def create_access_token(user_id: int) -> str:
    """產生 Access Token"""
    expire = datetime.utcnow() + timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    payload = {"sub": str(user_id), "exp": expire}
    return jwt.encode(
        payload, settings.JWT_SECRET_KEY, algorithm=settings.JWT_ALGORITHM
    )


def create_refresh_token(user_id: int) -> str:
    """產生 Refresh Token"""
    expire = datetime.utcnow() + timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS)
    payload = {"sub": str(user_id), "exp": expire}
    return jwt.encode(
        payload, settings.JWT_SECRET_KEY, algorithm=settings.JWT_ALGORITHM
    )


def verify_token(token: str) -> Optional[int]:
    """驗證 Token，成功回傳 user_id，失敗回傳 None"""
    try:
        payload = jwt.decode(
            token, settings.JWT_SECRET_KEY, algorithms=[settings.JWT_ALGORITHM]
        )
        user_id = payload.get("sub")
        if user_id is None:
            return None
        return int(user_id)
    except JWTError:
        return None


def hash_token(token: str) -> str:
    """將 Token 做 SHA-256 雜湊"""
    return hashlib.sha256(token.encode()).hexdigest()


def save_refresh_token(db: Session, user_id, token: str) -> None:
    """將 refresh token 儲存到資料庫"""
    # 計算過期時間
    expires_at = datetime.utcnow() + timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS)

    # 建立 UserToken 紀錄
    user_token = UserToken(
        user_id=user_id,
        token_type=UserTokenType.refresh,
        token_hash=hash_token(token),
        expires_at=expires_at,
    )

    # 存入資料庫
    db.add(user_token)
    db.commit()


def revoke_token(db: Session, token: str) -> bool:
    """撤銷 token ，成功回傳True，找不到回傳False"""
    token_hash = hash_token(token)

    # 查詢這個 token
    user_token = (
        db.query(UserToken)
        .filter(UserToken.token_hash == token_hash, UserToken.is_revoked == False)
        .first()
    )

    if not user_token:
        return False

    # 標記為已撤銷
    user_token.is_revoked = True
    user_token.revoked_at = datetime.utcnow()
    db.commit()

    return True


def is_token_revoked(db: Session, token: str) -> bool:
    """檢查 token 是否已被撤銷或不存在"""
    token_hash = hash_token(token)

    user_token = db.query(UserToken).filter(UserToken.token_hash == token_hash).first()

    # 找不到或已撤銷都視為無效
    if not user_token or user_token.is_revoked:
        return True
    return False


def create_password_reset_token(db: Session, user_id: int, token_type: UserTokenType = UserTokenType.reset_password) -> str:
    """產生密碼重設 token ，存到資料庫，回傳原始 token"""
    # 產生隨機token(32 bytes = 256 bits，URL安全格式)
    token = secrets.token_urlsafe(32)

    # 計算過期時間(1小時後)
    expires_at = datetime.utcnow() + timedelta(hours=1)

    # 建立 UserToken 紀錄
    user_token = UserToken(
        user_id=user_id,
        token_type=token_type,
        token_hash=hash_token(token),
        expires_at=expires_at,
    )

    # 存入資料庫
    db.add(user_token)
    db.commit()

    # 回傳原始token (寄給使用者)
    return token


def verify_password_reset_token(db: Session, token: str, token_type: UserTokenType = UserTokenType.reset_password) -> int | None:    
    """
    驗證密碼重設 token
    成功回傳 user_id，失敗回傳 None
    """

    token_hash = hash_token(token)

    # 查詢 token
    user_token = (
        db.query(UserToken)
        .filter(
            UserToken.token_hash == token_hash,
            UserToken.token_type == token_type,
            UserToken.is_revoked == False,
        )
        .first()
    )

    # token 不存在
    if not user_token:
        return None

    # token 已過期
    if user_token.expires_at < datetime.utcnow():
        return None

    # 標記為已使用（一次性）
    user_token.is_revoked = True
    user_token.revoked_at = datetime.utcnow()
    db.commit()

    return user_token.user_id


def get_current_user(
    token: str = Depends(oauth2_schema), db: Session = Depends(get_db)
) -> User:
    """從 JWT Token 取得目前登入的使用者"""
    # 1. 驗證 token 取得 user_id
    user_id = verify_token(token)
    if user_id is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="無效的認證憑證",
            headers={"WWW-Authenticate": "Bearer"},
        )
    # 2. 用 user_id 查詢資料庫
    user = db.query(User).filter(User.id == user_id).first()
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="使用者不存在"
        )
    # 3. 回傳使用者物件
    return user
