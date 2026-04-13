"""
RBAC (Role-Based Access Control) 依賴項
"""

from fastapi import Depends, HTTPException, status
from sqlalchemy.orm import Session
from typing import List, Callable

from app.database import get_db
from app.models import User, UserRole, RolePermission, Permission
from app.services.auth import get_current_user


def get_user_permissions(db: Session, user_id: int) -> List[str]:
    """查詢使用者擁有的所有權限代碼"""
    results = db.query(Permission.code).join(
        RolePermission, Permission.id == RolePermission.permission_id
    ).join(
        UserRole, RolePermission.role_id == UserRole.role_id
    ).filter(
        UserRole.user_id == user_id
    ).distinct().all()

    return [r[0] for r in results]


def require_admin(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> User:
    """檢查使用者是否具有管理員權限（擁有 user: 開頭的權限），若無則拋出 403"""
    permissions = get_user_permissions(db, current_user.id)
    is_admin = any(p.startswith("user:") for p in permissions)
    if not is_admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="需要管理員權限",
        )
    return current_user


def require_permission(permission_code: str) -> Callable:
    """
    權限檢查依賴項工廠
    
    使用方式：Depends(require_permission("user:create"))
    """

    def permission_checker(
        current_user: User = Depends(get_current_user),
        db: Session = Depends(get_db)
    ) -> User:
        user_permissions = get_user_permissions(db, current_user.id)

        if permission_code not in user_permissions:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"權限不足：需要 {permission_code} 權限"
            )

        return current_user

    return permission_checker
