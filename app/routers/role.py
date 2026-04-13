from fastapi import APIRouter, Depends, HTTPException, status
from app.schemas import (
    RoleCreate,
    RoleUpdate,
    RoleResponse,
    RoleListResponse
)
from app.schemas.permission import PermissionResponse, RolePermissionUpdate
from sqlalchemy.orm import Session
from app.database import get_db
from app.models import Role, User, Permission, RolePermission
from app.dependencies import require_permission

router = APIRouter(prefix="/roles", tags=["Roles"])

# 取得所有角色資訊
@router.get("", response_model=RoleListResponse)
def get_roles(
    db: Session = Depends(get_db),
    _: User = Depends(require_permission("role:view")),
):
    """查詢資料庫裡所有的角色"""
    roles = db.query(Role).all()
    
    return {"roles":roles, "total":len(roles)}


# 取得單一角色資訊
@router.get("/{id}", response_model=RoleResponse)
def get_role(
    id: int,
    db: Session = Depends(get_db),
    _: User = Depends(require_permission("role:view")),
):
    """查詢單一角色的資訊"""
    role = db.query(Role).filter(Role.id == id).first()
    
    if not role:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="角色不存在"
        )
        
    return role


# 新增角色
@router.post("", response_model=RoleResponse, status_code=status.HTTP_201_CREATED)
def create_role(
    data: RoleCreate,
    db: Session = Depends(get_db),
    _: User = Depends(require_permission("role:create")),
):
    """新增角色到資料庫"""
    # 1. 檢查 code 是否重複
    existing = db.query(Role).filter(Role.code == data.code).first()
    
    if existing:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="角色已存在"
        )
        
    # 2. 建立新的 Role 物件
    new_role = Role(
        name = data.name,
        code = data.code,
        description = data.description
    )
    
    # 3. 存到資料庫
    db.add(new_role)
    db.commit()
    db.refresh(new_role)
    
    # 4. 回傳
    return new_role


# 更新角色資訊
@router.put("/{id}",response_model=RoleResponse)
def update_role(
    id: int,
    data: RoleUpdate,
    db: Session = Depends(get_db),
    _: User = Depends(require_permission("role:edit")),
):
    """更新資料庫的角色資訊"""
    # 1. 確認該角色存在
    role = db.query(Role).filter(Role.id == id).first()
    
    if not role:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="角色不存在"
        )
        
    # 2. 如果要改code，檢查新code是否重複
    if data.code is not None:
        duplicate = db.query(Role).filter(Role.code == data.code, Role.id != id).first()
        
        if duplicate:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="該角色代碼已被使用"
            )
            
    # 3. 只更新有傳進來的欄位
    if data.name is not None:
        role.name = data.name
    if data.code is not None:
        role.code = data.code
    if data.description is not None:
        role.description = data.description
        
    # 4. 提交
    db.commit()
    db.refresh(role)
    
    # 5. 回傳
    return role

# 刪除角色
@router.delete("/{id}")
def delete_role(
    id: int,
    db: Session = Depends(get_db),
    _: User = Depends(require_permission("role:delete")),
):
    """刪除該角色在資料庫的資料"""
    # 1. 確認角色是否存在
    role = db.query(Role).filter(Role.id == id).first()
    
    if not role:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="角色不存在"
        )
    
    # 2. 刪除角色
    db.delete(role)
    db.commit()
    
    # 3. 回傳訊息
    return {"message": "刪除成功"}


# ========== 角色-權限管理 ==========

# 取得某角色擁有的所有權限
@router.get("/{id}/permissions", response_model=list[PermissionResponse])
def get_role_permissions(
    id: int,
    db: Session = Depends(get_db),
    _: User = Depends(require_permission("role:view")),
):
    """
    查詢某角色目前被指派的所有權限

    流程：role_permissions 橋接表 JOIN permissions 表
    回傳：該角色擁有的 Permission 物件列表
    """
    # 1. 確認角色存在
    role = db.query(Role).filter(Role.id == id).first()
    if not role:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="角色不存在"
        )

    # 2. 透過 role_permissions 橋接表查出所有關聯的 permission
    permissions = (
        db.query(Permission)
        .join(RolePermission, RolePermission.permission_id == Permission.id)
        .filter(RolePermission.role_id == id)
        .order_by(Permission.resource, Permission.action)
        .all()
    )

    return permissions


# 批次更新角色的權限（整批取代）
@router.put("/{id}/permissions", response_model=list[PermissionResponse])
def update_role_permissions(
    id: int,
    data: RolePermissionUpdate,
    db: Session = Depends(get_db),
    _: User = Depends(require_permission("role:edit")),
):
    """
    批次更新角色的權限

    策略：「先全刪再全建」（Replace All）
    - 前端勾完 checkbox → 送出所有被勾選的 permission_id
    - 後端刪掉舊的關聯 → 建立新的關聯
    - 好處：邏輯簡單，不用比對差異
    """
    # 1. 確認角色存在
    role = db.query(Role).filter(Role.id == id).first()
    if not role:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="角色不存在"
        )

    # 2. 驗證所有 permission_id 都存在
    if data.permission_ids:
        existing_count = (
            db.query(Permission)
            .filter(Permission.id.in_(data.permission_ids))
            .count()
        )
        if existing_count != len(data.permission_ids):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="部分權限 ID 不存在"
            )

    # 3. 刪除該角色的所有舊權限關聯
    db.query(RolePermission).filter(RolePermission.role_id == id).delete()

    # 4. 建立新的關聯
    for perm_id in data.permission_ids:
        db.add(RolePermission(role_id=id, permission_id=perm_id))

    # 5. 提交
    db.commit()

    # 6. 回傳更新後的權限列表
    permissions = (
        db.query(Permission)
        .join(RolePermission, RolePermission.permission_id == Permission.id)
        .filter(RolePermission.role_id == id)
        .order_by(Permission.resource, Permission.action)
        .all()
    )

    return permissions