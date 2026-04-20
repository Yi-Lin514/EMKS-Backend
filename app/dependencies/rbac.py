"""
RBAC (Role-Based Access Control) 依賴項
"""

from fastapi import Depends, HTTPException, status
from sqlalchemy import and_, or_
from sqlalchemy.orm import Session
from typing import List, Callable

from app.database import get_db
from app.models import User, UserRole, RolePermission, Permission
from app.models.knowledge import KnowledgeDocument
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


def can_access_document(db: Session, user: User, document: KnowledgeDocument) -> bool:
    """文件 resource-level 權限檢查，語意與 build_permission_filter (RAG) 一致。

    - 擁有 ai:admin_tools（admin 角色）→ 直接通過；跟 RAG 層同一個判斷點
    - permission_level='public' → 所有登入使用者可讀
    - permission_level='department' → 僅同部門可讀
    """
    if "ai:admin_tools" in get_user_permissions(db, user.id):
        return True
    if document.permission_level == "public":
        return True
    if (
        document.permission_level == "department"
        and user.department_id is not None
        and user.department_id == document.department_id
    ):
        return True
    return False


def build_document_access_filter(db: Session, user: User):
    """為 KnowledgeDocument 查詢建立權限 WHERE 子句；回傳 None 表示不需要過濾（admin）。"""
    if "ai:admin_tools" in get_user_permissions(db, user.id):
        return None
    if user.department_id is None:
        return KnowledgeDocument.permission_level == "public"
    return or_(
        KnowledgeDocument.permission_level == "public",
        and_(
            KnowledgeDocument.permission_level == "department",
            KnowledgeDocument.department_id == user.department_id,
        ),
    )
