import pytest
from fastapi import HTTPException

from app.dependencies.rbac import get_user_permissions, require_admin, require_permission


def test_get_user_permissions_returns_codes(db, make_user):
    user = make_user(email="u1@demo.com", permissions=["document:view", "document:create"])

    perms = get_user_permissions(db, user.id)

    assert set(perms) == {"document:view", "document:create"}


def test_get_user_permissions_dedupes_across_roles(db, make_user):
    """同一 user 透過多個 role 拿到同一 permission 時只回傳一次。"""
    from app.models import Role, Permission, RolePermission, UserRole, ScopeType

    user = make_user(email="u2@demo.com", permissions=["document:view"])

    # 再加一個 role 也給同一個 permission
    extra = Role(code="extra", name="extra")
    db.add(extra)
    db.flush()
    perm = db.query(Permission).filter(Permission.code == "document:view").first()
    db.add(RolePermission(role_id=extra.id, permission_id=perm.id))
    db.add(UserRole(user_id=user.id, role_id=extra.id, scope_type=ScopeType.GLOBAL))
    db.commit()

    perms = get_user_permissions(db, user.id)

    assert perms.count("document:view") == 1


def test_require_admin_passes_for_user_scope_permission(db, make_user):
    admin = make_user(email="admin@demo.com", permissions=["user:create"])

    result = require_admin(current_user=admin, db=db)

    assert result is admin


def test_require_admin_rejects_non_admin(db, make_user):
    viewer = make_user(email="viewer@demo.com", permissions=["document:view"])

    with pytest.raises(HTTPException) as exc:
        require_admin(current_user=viewer, db=db)

    assert exc.value.status_code == 403


def test_require_permission_enforces_specific_code(db, make_user):
    user = make_user(email="u3@demo.com", permissions=["document:view"])

    require_permission("document:view")(current_user=user, db=db)  # ok

    with pytest.raises(HTTPException) as exc:
        require_permission("document:delete")(current_user=user, db=db)
    assert exc.value.status_code == 403
