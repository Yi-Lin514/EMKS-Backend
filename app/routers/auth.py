from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response, status
from sqlalchemy.orm import Session
from app.schemas import (
    LoginRequest,
    TokenResponse,
    RefreshTokenRequest,
    UserInfo,
    LogoutRequest,
    ForgotPasswordRequest,
    ResetPasswordRequest,
)
from app.schemas.login_history import LoginHistoryListResponse
from app.database import get_db
from app.models import User, UserToken, UserTokenType, LoginHistory, LoginStatus
from app.services import (
    verify_password,
    create_access_token,
    create_refresh_token,
    verify_token,
    save_refresh_token,
    revoke_token,
    is_token_revoked,
    create_password_reset_token,
    send_password_reset_email,
    verify_password_reset_token,
    hash_password,
)
from app.dependencies import get_user_permissions, require_permission
from app.rate_limit import limiter

# 帳號鎖定設定
MAX_FAILED_ATTEMPTS = 5
LOCKOUT_MINUTES = 15


router = APIRouter(prefix="/auth", tags=["auth"])


# ========== 登入歷史記錄輔助函式 ==========

def _detect_device_type(user_agent: str) -> str:
    """從 User-Agent 字串簡單判斷裝置類型"""
    ua_lower = user_agent.lower()
    if any(kw in ua_lower for kw in ["mobile", "android", "iphone", "ipad"]):
        return "mobile"
    return "desktop"


def _record_login(
    db: Session,
    request: Request,
    email: str,
    user_id: int | None,
    login_status: LoginStatus,
    failure_reason: str | None = None,
):
    """
    記錄一筆登入歷史到 login_history 表

    參數：
    - request: FastAPI 的 Request 物件，用來取 IP 和 User-Agent
    - email: 嘗試登入的 email
    - user_id: 使用者 ID（帳號不存在時為 None）
    - login_status: success 或 failed
    - failure_reason: 失敗原因（成功時為 None）
    """
    user_agent = request.headers.get("user-agent", "")
    ip_address = request.client.host if request.client else None

    record = LoginHistory(
        user_id=user_id,
        attempted_email=email,
        ip_address=ip_address,
        user_agent=user_agent[:500] if user_agent else None,
        device_type=_detect_device_type(user_agent) if user_agent else None,
        login_status=login_status,
        failure_reason=failure_reason,
    )
    db.add(record)
    db.commit()


# ========== 登入 ==========

@router.post("/login", response_model=TokenResponse)
@limiter.limit("10/minute")
def login(
    login_data: LoginRequest,
    request: Request,
    response: Response,
    db: Session = Depends(get_db),
):
    """使用者登入"""
    # 1. 查使用者
    user = db.query(User).filter(User.email == login_data.email).first()

    if not user:
        _record_login(db, request, login_data.email, None, LoginStatus.FAILED, "帳號不存在")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="帳號或密碼錯誤"
        )

    # 2. 檢查帳號是否被鎖定
    if user.locked_until and user.locked_until > datetime.now():
        remaining = (user.locked_until - datetime.now()).seconds // 60 + 1
        _record_login(db, request, login_data.email, user.id, LoginStatus.FAILED, "帳號鎖定中")
        raise HTTPException(
            status_code=status.HTTP_423_LOCKED,
            detail=f"帳號已鎖定，請於 {remaining} 分鐘後再試",
        )

    # 3. 檢查帳號狀態
    if user.status != "active":
        status_messages = {
            "inactive": "帳號尚未啟用，請先完成啟用流程",
            "suspended": "帳號已被停權，請聯繫系統管理員",
        }
        _record_login(db, request, login_data.email, user.id, LoginStatus.FAILED, f"帳號狀態：{user.status}")
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=status_messages.get(user.status, "帳號狀態異常"),
        )

    # 4. 驗證密碼
    if not verify_password(login_data.password, user.password_hash):
        # 失敗次數 +1
        user.failed_login_count = (user.failed_login_count or 0) + 1

        # 達到上限 → 鎖定帳號
        if user.failed_login_count >= MAX_FAILED_ATTEMPTS:
            user.locked_until = datetime.now() + timedelta(minutes=LOCKOUT_MINUTES)
            db.commit()
            _record_login(db, request, login_data.email, user.id, LoginStatus.FAILED, "密碼錯誤（觸發鎖定）")
            raise HTTPException(
                status_code=status.HTTP_423_LOCKED,
                detail=f"登入失敗已達 {MAX_FAILED_ATTEMPTS} 次，帳號鎖定 {LOCKOUT_MINUTES} 分鐘",
            )

        db.commit()
        remaining_attempts = MAX_FAILED_ATTEMPTS - user.failed_login_count
        _record_login(db, request, login_data.email, user.id, LoginStatus.FAILED, "密碼錯誤")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"帳號或密碼錯誤（還剩 {remaining_attempts} 次嘗試機會）",
        )

    # 5. 登入成功 → 重置鎖定狀態 + 更新登入紀錄
    user.failed_login_count = 0
    user.locked_until = None
    user.last_login_at = datetime.now()
    user.last_login_ip = request.client.host if request.client else None
    db.commit()

    # 6. 記錄成功登入
    _record_login(db, request, login_data.email, user.id, LoginStatus.SUCCESS)

    # 7. 查權限
    permissions = get_user_permissions(db, user.id)

    # 8. 產生 token
    access_token = create_access_token(user.id)
    refresh_token = create_refresh_token(user.id)

    save_refresh_token(db, user.id, refresh_token)

    # 9. 組合使用者資訊 UserInfo
    user_info = UserInfo.model_validate(user)
    user_info.permissions = permissions

    return TokenResponse(
        access_token=access_token,
        refresh_token=refresh_token,
        user=user_info,
    )


@router.post("/refresh", response_model=TokenResponse)
def refresh(request: RefreshTokenRequest, db: Session = Depends(get_db)):
    """用 refresh token 換新的 access token"""
    user_id = verify_token(request.refresh_token)

    if not user_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="無效的 refresh token"
        )

    # 檢查 token 是否被撤銷
    if is_token_revoked(db, request.refresh_token):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="token已被撤銷"
        )

    user = db.query(User).filter(User.id == user_id).first()

    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="使用者不存在"
        )

    access_token = create_access_token(user.id)
    refresh_token = create_refresh_token(user.id)

    save_refresh_token(db, user.id, refresh_token)

    return TokenResponse(
        access_token=access_token,
        refresh_token=refresh_token,
        user=UserInfo.model_validate(user),
    )


@router.post("/logout")
def logout(request: LogoutRequest, db: Session = Depends(get_db)):
    """使用者登出，撤銷 refresh token"""
    success = revoke_token(db, request.refresh_token)

    if not success:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Token 不存在或已被撤銷"
        )
    return {"message": "登出成功"}


@router.post("/forgot-password")
def forgot_password(request: ForgotPasswordRequest, db: Session = Depends(get_db)):
    """忘記密碼 - 寄送重設連結"""
    # 1. 查詢用戶是否存在
    user = db.query(User).filter(User.email == request.email).first()

    # 2. 如果用戶存在，產生 token 並寄信
    if user:
        token = create_password_reset_token(db, user.id)
        send_password_reset_email(user.email, token)

    # 3. 不管 email 是否存在，都回傳相同訊息（安全考量）
    return {"message": "如果此信箱存在，已寄出重設密碼連結"}


@router.post("/reset-password")
def reset_password(request: ResetPasswordRequest, db: Session = Depends(get_db)):
    """重設密碼"""
    # 1. 驗證 token，取得 user_id
    user_id = verify_password_reset_token(db, request.token)

    if not user_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="無效或已過期的重設連結"
        )

    # 2. 查詢用戶
    user = db.query(User).filter(User.id == user_id).first()

    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="使用者不存在"
        )

    # 3. 更新密碼
    user.password_hash = hash_password(request.new_password)
    db.commit()

    return {"message": "密碼重設成功，請使用新密碼登入"}


@router.post("/activate-account")
def activate_account(request: ResetPasswordRequest, db: Session = Depends(get_db)):
    """啟用帳號，重設密碼"""
    # 1. 驗證 token，取得 user_id
    user_id = verify_password_reset_token(db, request.token, token_type=UserTokenType.activation)

    if not user_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="無效或已過期的重設連結"
        )

    # 2. 查詢用戶
    user = db.query(User).filter(User.id == user_id).first()

    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="使用者不存在"
        )

    # 3. 更新密碼 + 啟用帳號
    user.password_hash = hash_password(request.new_password)
    user.status = 'active' 
    db.commit()

    return {"message": "帳號啟用成功，請使用新密碼登入"}


# ========== Token 驗證（前端頁面載入時使用） ==========

@router.get("/verify-token")
def verify_page_token(
    token: str = Query(...),
    type: str = Query(...),
    db: Session = Depends(get_db),
):
    """
    驗證 token 是否有效，並回傳對應的使用者 email
    前端在重設密碼/啟用帳號頁面載入時呼叫
    """
    # 1. 根據 type 決定 token 類型
    if type == "activation":
        token_type = UserTokenType.activation
    else:
        token_type = UserTokenType.reset_password

    # 2. 驗證 token（唯讀，不消耗 token）
    #    不用 verify_password_reset_token()，因為那個函式會標記 is_revoked
    from app.services.auth import hash_token
    token_hash = hash_token(token)

    user_token = (
        db.query(UserToken)
        .filter(
            UserToken.token_hash == token_hash,
            UserToken.token_type == token_type,
            UserToken.is_revoked == False,
        )
        .first()
    )

    if not user_token or user_token.expires_at < datetime.utcnow():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="連結已失效或不存在"
        )

    # 3. 用 user_id 查使用者 email
    user = db.query(User).filter(User.id == user_token.user_id).first()

    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="使用者不存在"
        )

    return {"email": user.email}


# ========== 登入歷史查詢 ==========

@router.get("/login-history", response_model=LoginHistoryListResponse)
def get_login_history(
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
    _: User = Depends(require_permission("system:view")),
):
    """
    查詢登入歷史記錄（管理員功能）

    需要 system:view 權限
    支援分頁：page（頁碼）、limit（每頁筆數）
    按時間倒序排列（最新的在前面）
    """
    # 1. 計算總筆數
    total = db.query(LoginHistory).count()

    # 2. 分頁查詢
    offset = (page - 1) * limit
    records = (
        db.query(LoginHistory)
        .order_by(LoginHistory.created_at.desc())
        .offset(offset)
        .limit(limit)
        .all()
    )

    return {
        "records": records,
        "total": total,
        "page": page,
        "limit": limit,
    }

