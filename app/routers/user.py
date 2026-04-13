from fastapi import APIRouter, Depends, HTTPException, status
from app.models import User, Department, UserStatus, UserTokenType, UserRole, ScopeType
from app.schemas import (
    UserResponse,
    UserUpdate,
    PasswordChange,
    UserCreate,
    UserAdminUpdate,
    UserListResponse,
)
from app.services import (
    get_current_user,
    verify_password,
    hash_password,
    get_user_with_dept,
    user_to_dict,
    create_password_reset_token,
    send_activation_email,
)
from app.dependencies import require_permission
from app.database import get_db
from sqlalchemy.orm import Session
import secrets


router = APIRouter(prefix="/users", tags=["Users"])


# ===== profile =====
@router.get("/me", response_model=UserResponse)
def get_my_profile(
    current_user: User = Depends(get_current_user), db: Session = Depends(get_db)
):
    """取得目前登入者的個人資料"""
    result = get_user_with_dept(db, current_user.id)
    user, dept_name = result
    return user_to_dict(user, dept_name)


@router.put("/me", response_model=UserResponse)
def update_my_profile(
    user_data: UserUpdate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """更新目前登入者的個人資訊"""
    # 1. 取出有傳值的欄位並更新
    update_data = user_data.model_dump(exclude_unset=True)
    for key, value in update_data.items():
        setattr(current_user, key, value)

    # 2. 存到資料庫
    db.commit()
    db.refresh(current_user)

    # 3. 查詢並回傳（含 department_name）
    result = get_user_with_dept(db, current_user.id)
    user, dept_name = result
    return user_to_dict(user, dept_name)


@router.put("/me/password")
def change_password(
    password_data: PasswordChange,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """更新目前登入者的密碼"""
    # 1. 驗證目前密碼是否正確
    if not verify_password(password_data.current_password, current_user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="目前密碼不正確"
        )

    # 2. 新密碼加密並更新
    current_user.password_hash = hash_password(password_data.new_password)
    db.commit()

    return {"message": "密碼修改成功"}


# ===== /users =====


# 管理員取得使用者列表
@router.get("", response_model=UserListResponse)
def get_users(
    page: int = 1,
    page_size: int = 10,
    search: str = None,
    status: str = None,
    department_id: int = None,
    role_id: int = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("user:view")),
):
    """取得使用者列表(分頁+搜尋)"""
    # 1. 建立基礎查詢
    query = db.query(User, Department.name.label("department_name")).outerjoin(
        Department, User.department_id == Department.id
    )

    # 2. 如果有搜尋條件，加上過濾
    # 搜尋欄
    if search:
        search_pattern = f"%{search}%"
        query = query.filter(
            (User.name.ilike(search_pattern))
            | (User.email.ilike(search_pattern))
            | (User.employee_id.ilike(search_pattern))
        )
    # 部門下拉選單
    if department_id:
        query = query.filter(User.department_id == department_id)

    # 狀態下拉選單
    if status in ["active", "inactive", "suspended"]:
        query = query.filter(User.status == status)

    # 角色下拉選單
    if role_id:
        query = query.join(UserRole, User.id == UserRole.user_id).filter(
            UserRole.role_id == role_id
        )

    # 3. 計算總筆數（過濾後）
    total = query.count()

    # 3.5 統計各狀態人數（不受篩選影響）
    stats = {
        "total": db.query(User).count(),
        "active": db.query(User).filter(User.status == "active").count(),
        "inactive": db.query(User).filter(User.status == "inactive").count(),
        "suspended": db.query(User).filter(User.status == "suspended").count(),
    }

    # 4. 分頁
    offset = (page - 1) * page_size
    results = query.offset(offset).limit(page_size).all()

    # 5. 轉換格式
    users = [user_to_dict(user, dept_name) for user, dept_name in results]

    return {"total": total, "page": page, "page_size": page_size, "users": users, "stats": stats}


# 管理員取得目標使用者
@router.get("/{id}", response_model=UserResponse)
def get_user(
    id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("user:view")),
):
    """取得使用者個人資料"""
    result = get_user_with_dept(db, id)

    if not result:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="使用者不存在"
        )

    user, dept_name = result
    return user_to_dict(user, dept_name)


# 管理員新增使用者
@router.post("", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
def create_user(
    user_data: UserCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("user:create")),
):
    """新增使用者"""
    # 1. 檢查 email 是否已存在
    existing_user = db.query(User).filter(User.email == user_data.email).first()
    if existing_user:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="帳號已被註冊"
        )
    # 檢查員工編號是否重複
    if user_data.employee_id:
        existing_emp = (
            db.query(User).filter(User.employee_id == user_data.employee_id).first()
        )
        if existing_emp:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST, detail="員工編號已存在"
            )

    # 2. 建立新使用者（預設密碼）
    new_user = User(
        name=user_data.name,
        email=user_data.email,
        employee_id=user_data.employee_id,
        phone=user_data.phone,
        job_title=user_data.job_title,
        department_id=user_data.department_id,
        status="inactive",
        password_hash=hash_password(secrets.token_urlsafe(16)),
    )

    # 3. 存到資料庫
    db.add(new_user)
    db.commit()

    # 4. 如果有指定角色，建立角色關聯
    if user_data.role_id is not None:
        new_user_role = UserRole(
            user_id=new_user.id,
            role_id=user_data.role_id,
            scope_type=ScopeType.GLOBAL,
            scope_department_id=0,
            assigned_by=current_user.id,
        )
        db.add(new_user_role)
        db.commit()

    token = create_password_reset_token(db, new_user.id, UserTokenType.activation)
    send_activation_email(new_user.email, token)
    db.refresh(new_user)

    # 4. 查詢並回傳（含 department_name）
    result = get_user_with_dept(db, new_user.id)
    user, dept_name = result
    return user_to_dict(user, dept_name)


# 管理員更新使用者
@router.put("/{id}", response_model=UserResponse)
def update_user(
    id: int,
    user_data: UserAdminUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("user:edit")),
):
    """更新使用者"""
    # 1. 確認使用者存在
    user = db.query(User).filter(User.id == id).first()
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="使用者不存在"
        )

    # 2. 更新欄位
    user_update = user_data.model_dump(exclude_unset=True)
    role_id = user_update.pop("role_id", None)
    for key, value in user_update.items():
        setattr(user, key, value)
    # 如果有傳 role_id，更新使用者角色
    if role_id is not None:
        # 刪除原本的角色關聯
        db.query(UserRole).filter(UserRole.user_id == user.id).delete()
        # 新增新的角色關聯
        new_user_role = UserRole(
            user_id=user.id,
            role_id=role_id,
            scope_type=ScopeType.GLOBAL,
            scope_department_id=0,
            assigned_by=current_user.id,
        )
        db.add(new_user_role)

    # 3. 存到資料庫
    db.commit()
    db.refresh(user)

    # 4. 查詢並回傳（含 department_name）
    result = get_user_with_dept(db, id)
    user, dept_name = result
    return user_to_dict(user, dept_name)


# 管理員刪除使用者
@router.delete("/{id}")
def delete_user(
    id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("user:delete")),
):
    """刪除使用者"""
    # 1. 確認使用者存在
    user = db.query(User).filter(User.id == id).first()
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="使用者不存在"
        )

    # 2. 刪除
    db.delete(user)
    db.commit()

    return {"message": "使用者已刪除"}
