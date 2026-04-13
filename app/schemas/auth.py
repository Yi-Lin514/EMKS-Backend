from pydantic import BaseModel, EmailStr, ConfigDict


class UserInfo(BaseModel):
    """使用者基本資訊（回傳給前端）"""
    id: int
    name: str
    email: EmailStr
    status: str
    department_id: int | None = None
    employee_id: str | None = None
    job_title: str | None = None
    permissions: list[str] = []

    model_config = ConfigDict(from_attributes=True)


class LoginRequest(BaseModel):
    """登入請求"""
    email: EmailStr
    password: str


class TokenResponse(BaseModel):
    """登入成功回應"""
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    user: UserInfo


class TokenPayload(BaseModel):
    """JWT Payload"""
    sub: int
    exp: int


class RefreshTokenRequest(BaseModel):
    """刷新 Token 請求"""
    refresh_token: str


class LogoutRequest(BaseModel):
    """登出請求"""
    refresh_token: str


class ForgotPasswordRequest(BaseModel):
    """忘記密碼請求"""
    email: EmailStr


class ResetPasswordRequest(BaseModel):
    """重設密碼請求"""
    token: str
    new_password: str
