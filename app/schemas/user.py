from pydantic import BaseModel, ConfigDict, EmailStr
from datetime import datetime 
from typing import Literal


class UserResponse(BaseModel):
    """丟給前端使用者個人資訊的回應"""
    id: int
    name: str
    email: str 
    employee_id: str | None = None
    phone: str | None = None
    department_id: int | None = None
    job_title: str | None = None
    created_at: datetime
    avatar_url: str | None = None
    status: Literal["active", "inactive", "suspended"] = "active"
    last_login_at: datetime | None = None
    last_login_ip: str | None = None
    password_changed_at: datetime | None = None
    department_name: str | None = None
    
    model_config = ConfigDict(from_attributes=True)


class UserUpdate(BaseModel):
    """更新個人資料的請求格式"""
    name: str | None = None
    phone: str | None = None
    avatar_url: str | None = None


class PasswordChange(BaseModel):
    """接收更改密碼的請求格式"""
    current_password: str
    new_password: str


class UserCreate(BaseModel):
    """管理員新增使用者時的請求格式"""
    name: str
    employee_id: str | None = None
    email: EmailStr
    phone: str | None = None
    job_title: str | None = None
    department_id: int
    role_id: int | None = None
    status: Literal["active","inactive","suspended"] = "active"


class UserAdminUpdate(BaseModel):
    """管理員更新使用者時的請求格式"""
    name: str | None = None
    employee_id: str | None = None
    phone: str | None = None
    job_title: str | None = None
    department_id: int | None = None
    role_id: int | None = None
    status: Literal["active","inactive","suspended"] | None = None


class UserStatsResponse(BaseModel):
    total: int
    active: int
    inactive: int
    suspended: int


class UserListResponse(BaseModel):
    """回傳使用者列表（含分頁資訊）"""
    users: list[UserResponse]
    total: int
    page: int
    page_size: int
    stats: UserStatsResponse | None = None