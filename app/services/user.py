"""
User Service - 使用者相關的業務邏輯

職責：
- 查詢使用者（含 JOIN 部門名稱）
- 將 User 物件轉換為 dict 格式
"""

from sqlalchemy.orm import Session
from app.models import User, Department


def get_user_with_dept(db: Session, user_id: int):
    """
    用 ID 查詢單一使用者，並 LEFT JOIN 取得部門名稱

    Args:
        db: 資料庫 Session
        user_id: 使用者 ID

    Returns:
        tuple(User, str | None) - (User 物件, 部門名稱)
        如果使用者不存在，回傳 None
    """
    result = (
        db.query(User, Department.name.label("department_name"))
        .outerjoin(Department, User.department_id == Department.id)
        .filter(User.id == user_id)
        .first()
    )
    return result  # (User, dept_name) 或 None


def user_to_dict(user: User, dept_name: str | None) -> dict:
    """
    將 User 物件 + 部門名稱轉換為 dict

    Args:
        user: User 物件
        dept_name: 部門名稱（可能是 None）

    Returns:
        dict - 符合 UserResponse schema 的格式
    """
    return {
        "id": user.id,
        "name": user.name,
        "email": user.email,
        "employee_id": user.employee_id,
        "phone": user.phone,
        "department_id": user.department_id,
        "job_title": user.job_title,
        "created_at": user.created_at,
        "avatar_url": user.avatar_url,
        "status": user.status.value,  # Enum 轉字串
        "last_login_at": user.last_login_at,
        "last_login_ip": user.last_login_ip,
        "password_changed_at": user.password_changed_at,
        "department_name": dept_name
    }
