from pydantic import BaseModel, ConfigDict


class PermissionResponse(BaseModel):
    """單一權限的回應格式"""
    id: int
    code: str        # 例如 "user:create"
    name: str        # 例如 "新增使用者"
    resource: str    # 例如 "user"
    action: str      # 例如 "create"
    description: str | None = None

    model_config = ConfigDict(from_attributes=True)


class PermissionListResponse(BaseModel):
    """權限列表的回應格式"""
    permissions: list[PermissionResponse]
    total: int


class RolePermissionUpdate(BaseModel):
    """批次更新角色權限的 Request（傳入 permission_id 清單）"""
    permission_ids: list[int]
