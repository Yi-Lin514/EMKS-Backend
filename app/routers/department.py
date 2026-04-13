from fastapi import APIRouter, Depends, HTTPException, status
from app.schemas import (
    DepartmentCreate,
    DepartmentUpdate,
    DepartmentResponse,
    DepartmentListResponse,
)
from sqlalchemy.orm import Session, aliased
from app.database import get_db
from app.models import Department, User
from app.dependencies.rbac import require_permission

router = APIRouter(prefix="/departments", tags=["Departments"])


def _build_department_response(db: Session, dept_id: int) -> dict | None:
    """查詢單一部門的完整資料（含 parent_name, manager_name, members）"""
    ParentDept = aliased(Department)
    Manager = aliased(User)

    result = (
        db.query(
            Department.id,
            Department.name,
            Department.code,
            Department.parent_id,
            ParentDept.name.label("parent_name"),
            Department.manager_id,
            Manager.name.label("manager_name"),
            Department.description,
            Department.level,
        )
        .outerjoin(ParentDept, Department.parent_id == ParentDept.id)
        .outerjoin(Manager, Department.manager_id == Manager.id)
        .filter(Department.id == dept_id)
        .first()
    )

    if not result:
        return None

    # 查詢該部門的成員
    members = (
        db.query(User.id, User.name, User.job_title)
        .filter(User.department_id == dept_id)
        .all()
    )

    return {
        "id": result.id,
        "name": result.name,
        "code": result.code,
        "parent_id": result.parent_id,
        "parent_name": result.parent_name,
        "manager_id": result.manager_id,
        "manager_name": result.manager_name,
        "description": result.description,
        "level": result.level,
        "member_count": len(members),
        "members": [
            {"id": m.id, "name": m.name, "job_title": m.job_title} for m in members
        ],
    }


# 取得部門列表
@router.get("", response_model=DepartmentListResponse)
def get_departments(
    db: Session = Depends(get_db),
    _: User = Depends(require_permission("department:view")),
):
    """查詢所有部門（含上層部門名稱、主管名稱、成員）"""
    ParentDept = aliased(Department)
    Manager = aliased(User)

    # LEFT JOIN 查詢：Department ← Parent ← Manager
    results = (
        db.query(
            Department.id,
            Department.name,
            Department.code,
            Department.parent_id,
            ParentDept.name.label("parent_name"),
            Department.manager_id,
            Manager.name.label("manager_name"),
            Department.description,
            Department.level,
        )
        .outerjoin(ParentDept, Department.parent_id == ParentDept.id)
        .outerjoin(Manager, Department.manager_id == Manager.id)
        .all()
    )

    # 一次查出所有使用者的部門歸屬，避免 N+1 查詢
    all_users = db.query(User.id, User.name, User.job_title, User.department_id).all()
    dept_members: dict[int, list] = {}
    for u in all_users:
        if u.department_id is not None:
            dept_members.setdefault(u.department_id, []).append(
                {"id": u.id, "name": u.name, "job_title": u.job_title}
            )

    departments = []
    for r in results:
        members = dept_members.get(r.id, [])
        departments.append(
            {
                "id": r.id,
                "name": r.name,
                "code": r.code,
                "parent_id": r.parent_id,
                "parent_name": r.parent_name,
                "manager_id": r.manager_id,
                "manager_name": r.manager_name,
                "description": r.description,
                "level": r.level,
                "member_count": len(members),
                "members": members,
            }
        )

    return {"departments": departments, "total": len(departments)}


# 取得單一部門資料
@router.get("/{id}", response_model=DepartmentResponse)
def get_department(
    id: int,
    db: Session = Depends(get_db),
    _: User = Depends(require_permission("department:view")),
):
    """查詢單一部門（含主管名稱、成員列表）"""
    result = _build_department_response(db, id)

    if not result:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="找不到該部門"
        )

    return result


# 新增部門
@router.post("", response_model=DepartmentResponse, status_code=status.HTTP_201_CREATED)
def create_department(
    data: DepartmentCreate,
    db: Session = Depends(get_db),
    _: User = Depends(require_permission("department:create")),
):
    """新增部門到資料庫"""
    # 1. 檢查 code 是否重複 (code是唯一)
    existing = db.query(Department).filter(Department.code == data.code).first()

    if existing:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="部門已存在")

    # 2. 計算層級（有上層 → parent.level + 1，否則 1）
    level = 1
    if data.parent_id:
        parent = db.query(Department).filter(Department.id == data.parent_id).first()
        if parent:
            level = parent.level + 1

    # 3. 建立新的 Department 物件
    new_department = Department(
        name=data.name,
        code=data.code,
        parent_id=data.parent_id,
        manager_id=data.manager_id,
        description=data.description,
        level=level,
    )

    # 4. 存到資料庫
    db.add(new_department)
    db.commit()
    db.refresh(new_department)

    # 5. 回傳完整資料（含 parent_name, manager_name 等）
    return _build_department_response(db, new_department.id)


# 更新部門資訊
@router.put("/{id}", response_model=DepartmentResponse)
def update_department(
    id: int,
    data: DepartmentUpdate,
    db: Session = Depends(get_db),
    _: User = Depends(require_permission("department:edit")),
):
    """更新部門"""
    # 1. 用 id 查部門
    department = db.query(Department).filter(Department.id == id).first()

    if not department:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="找不到該部門"
        )

    # 2. 如果要改 code，檢查新 code 是否跟別人重複
    if data.code is not None:
        duplicate = (
            db.query(Department)
            .filter(Department.code == data.code, Department.id != id)
            .first()
        )
        if duplicate:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT, detail="該部門代碼已被使用"
            )

    # 3. 只更新有傳進來的欄位
    if data.name is not None:
        department.name = data.name
    if data.code is not None:
        department.code = data.code
    if data.parent_id is not None:
        department.parent_id = data.parent_id
        # 重新計算層級
        parent = db.query(Department).filter(Department.id == data.parent_id).first()
        department.level = (parent.level + 1) if parent else 1
    if data.manager_id is not None:
        department.manager_id = data.manager_id
    if data.description is not None:
        department.description = data.description

    # 4. 儲存
    db.commit()
    db.refresh(department)

    # 5. 回傳完整資料
    return _build_department_response(db, department.id)


# 刪除部門資訊
@router.delete("/{id}")
def delete_department(
    id: int,
    db: Session = Depends(get_db),
    _: User = Depends(require_permission("department:delete")),
):
    """刪除部門"""
    # 1. 先查找要刪除的部門
    department = db.query(Department).filter(Department.id == id).first()

    # 2. 找不到，給錯誤提示
    if not department:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="找不到該部門"
        )

    # 3. 刪除
    db.delete(department)
    db.commit()

    # 4. 回傳訊息
    return {"message": "刪除成功"}
