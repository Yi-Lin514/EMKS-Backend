from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from app.database import get_db
from app.models import Permission, User
from app.schemas.permission import PermissionListResponse
from app.dependencies import require_permission

router = APIRouter(prefix="/permissions", tags=["Permissions"])


# 取得所有權限列表
@router.get("", response_model=PermissionListResponse)
def get_permissions(
    db: Session = Depends(get_db),
    _: User = Depends(require_permission("role:view")),
):
    """
    查詢資料庫裡所有的權限

    用途：前端權限矩陣需要知道「有哪些權限可以勾選」
    權限需求：role:view（能看角色的人就能看權限清單）
    """
    permissions = db.query(Permission).order_by(Permission.resource, Permission.action).all()

    return {"permissions": permissions, "total": len(permissions)}
