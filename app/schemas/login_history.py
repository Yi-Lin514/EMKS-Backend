from pydantic import BaseModel, ConfigDict
from datetime import datetime


class LoginHistoryResponse(BaseModel):
    """單一登入歷史記錄的回應格式"""
    id: int
    user_id: int | None = None
    attempted_email: str
    ip_address: str | None = None
    user_agent: str | None = None
    device_type: str | None = None
    login_status: str          # "success" 或 "failed"
    failure_reason: str | None = None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class LoginHistoryListResponse(BaseModel):
    """登入歷史列表的回應格式（含分頁）"""
    records: list[LoginHistoryResponse]
    total: int
    page: int
    limit: int
