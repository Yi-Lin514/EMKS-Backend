from pydantic import BaseModel, ConfigDict

class RoleCreate(BaseModel):
    """新增角色時的Request"""
    name: str
    code: str
    description: str | None = None


class RoleUpdate(BaseModel):
    """更新角色資訊的Request"""
    name: str | None = None
    code: str | None = None
    description: str | None = None


class RoleResponse(BaseModel):
    """回應角色資訊的Response"""
    id: int
    name: str
    code: str
    description: str | None = None
    is_system: bool 
    
    model_config = ConfigDict(from_attributes=True)


class RoleListResponse(BaseModel):
    """回傳多個角色(列表)"""
    roles: list[RoleResponse]
    total: int