from pydantic import BaseModel, ConfigDict


class DepartmentCreate(BaseModel):
    """新增部門時的Request"""
    name: str
    code: str
    parent_id: int | None = None
    manager_id: int | None = None
    description: str | None = None


class DepartmentUpdate(BaseModel):
    """更新部門時的Request"""
    name: str | None = None
    code: str | None = None
    parent_id: int | None = None
    manager_id: int | None = None
    description: str | None = None


class DepartmentMember(BaseModel):
    """部門成員（嵌套在部門回應中）"""
    id: int
    name: str
    job_title: str | None = None

    model_config = ConfigDict(from_attributes=True)


class DepartmentResponse(BaseModel):
    """回傳部門資料的Response"""
    id: int
    name: str
    code: str
    parent_id: int | None = None
    parent_name: str | None = None
    manager_id: int | None = None
    manager_name: str | None = None
    description: str | None = None
    level: int = 1
    member_count: int = 0
    members: list[DepartmentMember] = []

    model_config = ConfigDict(from_attributes=True)


class DepartmentListResponse(BaseModel):
    """回傳多個部門(列表)"""
    departments: list[DepartmentResponse]
    total: int
