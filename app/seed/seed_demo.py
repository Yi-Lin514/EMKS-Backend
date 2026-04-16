"""Demo seed — 路線 A（全 stateless demo）的核心。

雲端冷啟動時由 lifespan 背景呼叫 `run_seed_sync()`，會：
  1. 建 4 部門 / 14 權限 / 4 角色 / 4 demo 帳號
  2. 把 seed_docs/ 的檔案複製到 uploads/knowledge/seed/
  3. 直接建 approved + completed 的 KnowledgeDocVersion（跳過審核流程）
  4. 跑 embedding + 存進 ChromaDB

冪等：檢查 admin@demo.com 是否存在，有就整段 skip。
設計細節見 docs/SEED.md。
"""

from __future__ import annotations

import hashlib
import shutil
from datetime import datetime
from pathlib import Path

from sqlalchemy.orm import Session

from app.database import Base, SessionLocal, engine
from app.models import (
    Department,
    Permission,
    Role,
    RolePermission,
    ScopeType,
    User,
    UserRole,
    UserStatus,
)
from app.models.knowledge import KnowledgeDocument, KnowledgeDocVersion
from app.services.auth import hash_password
from app.services.embedding import (
    chunk_text,
    extract_text_from_file,
    get_embeddings_batch,
)
from app.services.vector_store import add_chunks, delete_document_chunks

SEED_DOCS_DIR = Path("seed_docs")
SEED_UPLOAD_DIR = Path("uploads/knowledge/seed")

# ---------- 資料定義 ----------

DEPARTMENTS = [
    {"code": "mgmt", "name": "管理部", "description": "管理階層", "sort_order": 1},
    {"code": "it", "name": "資訊部", "description": "IT 與系統維運", "sort_order": 2},
    {"code": "mfg", "name": "製造部", "description": "生產製造", "sort_order": 3},
    {"code": "qc", "name": "品管部", "description": "品質管制", "sort_order": 4},
]

PERMISSIONS = [
    # User
    {"code": "user:view", "name": "查看使用者", "resource": "user", "action": "view"},
    {"code": "user:create", "name": "建立使用者", "resource": "user", "action": "create"},
    {"code": "user:edit", "name": "編輯使用者", "resource": "user", "action": "edit"},
    {"code": "user:delete", "name": "刪除使用者", "resource": "user", "action": "delete"},
    # Department
    {"code": "department:view", "name": "查看部門", "resource": "department", "action": "view"},
    {"code": "department:create", "name": "建立部門", "resource": "department", "action": "create"},
    {"code": "department:edit", "name": "編輯部門", "resource": "department", "action": "edit"},
    {"code": "department:delete", "name": "刪除部門", "resource": "department", "action": "delete"},
    # Role
    {"code": "role:view", "name": "查看角色", "resource": "role", "action": "view"},
    {"code": "role:create", "name": "建立角色", "resource": "role", "action": "create"},
    {"code": "role:edit", "name": "編輯角色", "resource": "role", "action": "edit"},
    {"code": "role:delete", "name": "刪除角色", "resource": "role", "action": "delete"},
    # System
    {"code": "system:view", "name": "查看系統資訊", "resource": "system", "action": "view"},
    # AI — agent 用 ai:admin_tools 判斷是否為 admin（見 routers/ai.py::_check_admin）
    {"code": "ai:admin_tools", "name": "AI 管理員工具", "resource": "ai", "action": "admin_tools"},
]

ROLES = [
    {"code": "admin", "name": "系統管理員", "description": "全系統管理權限", "is_system": True},
    {"code": "manager", "name": "部門主管", "description": "查看使用者/部門/角色", "is_system": True},
    {"code": "employee", "name": "一般員工", "description": "僅能查看部門列表", "is_system": True},
    {"code": "viewer", "name": "唯讀觀察者", "description": "登入後僅能使用 AI 和查看有權限的文件", "is_system": True},
]

ROLE_PERMISSIONS: dict[str, list[str]] = {
    "admin": [p["code"] for p in PERMISSIONS],
    "manager": ["user:view", "department:view", "role:view", "system:view"],
    "employee": ["department:view"],
    "viewer": [],
}

USERS = [
    {
        "email": "admin@demo.com",
        "name": "系統管理員",
        "password": "demo123",
        "employee_id": "DEMO001",
        "department_code": "mgmt",
        "role_code": "admin",
        "job_title": "系統管理員",
    },
    {
        "email": "manager@demo.com",
        "name": "部門主管",
        "password": "demo123",
        "employee_id": "DEMO002",
        "department_code": "it",
        "role_code": "manager",
        "job_title": "資訊部主管",
    },
    {
        "email": "employee@demo.com",
        "name": "一般員工",
        "password": "demo123",
        "employee_id": "DEMO003",
        "department_code": "mfg",
        "role_code": "employee",
        "job_title": "產線工程師",
    },
    {
        "email": "viewer@demo.com",
        "name": "唯讀觀察者",
        "password": "demo123",
        "employee_id": "DEMO004",
        "department_code": "qc",
        "role_code": "viewer",
        "job_title": "品管員",
    },
]

# (檔名, permission_level, 所屬部門 code or None)
DOCUMENTS: list[tuple[str, str, str | None]] = [
    ("01_員工手冊.txt", "public", None),
    ("02_資安規範.txt", "public", None),
    ("03_報銷流程.txt", "public", None),
    ("04_出差規範.txt", "public", None),
    ("05_新人Onboarding.txt", "public", None),
    ("06_客訴處理流程.txt", "public", None),
    ("07_ISO品管手冊.txt", "department", "qc"),
    ("08_生產SOP.txt", "department", "mfg"),
]


# ---------- 主流程 ----------

def _already_seeded(db: Session) -> bool:
    return db.query(User).filter(User.email == "admin@demo.com").first() is not None


def _seed_rbac(db: Session) -> dict:
    """Seed departments / permissions / roles / role_permissions / users / user_roles。
    回傳 {'dept': {code: id}, 'role': {code: id}, 'admin_user': User}。
    """
    # Departments
    dept_map: dict[str, int] = {}
    for d in DEPARTMENTS:
        dept = Department(**d)
        db.add(dept)
        db.flush()
        dept_map[d["code"]] = dept.id

    # Permissions
    perm_map: dict[str, int] = {}
    for p in PERMISSIONS:
        perm = Permission(**p)
        db.add(perm)
        db.flush()
        perm_map[p["code"]] = perm.id

    # Roles
    role_map: dict[str, int] = {}
    for r in ROLES:
        role = Role(**r)
        db.add(role)
        db.flush()
        role_map[r["code"]] = role.id

    # Role-Permission
    for role_code, perm_codes in ROLE_PERMISSIONS.items():
        for perm_code in perm_codes:
            db.add(RolePermission(
                role_id=role_map[role_code],
                permission_id=perm_map[perm_code],
            ))

    # Users + UserRoles
    admin_user: User | None = None
    for u in USERS:
        user = User(
            email=u["email"],
            name=u["name"],
            password_hash=hash_password(u["password"]),
            employee_id=u["employee_id"],
            department_id=dept_map[u["department_code"]],
            job_title=u["job_title"],
            status=UserStatus.active,
        )
        db.add(user)
        db.flush()

        db.add(UserRole(
            user_id=user.id,
            role_id=role_map[u["role_code"]],
            scope_type=ScopeType.GLOBAL,
            scope_department_id=0,
        ))

        if u["role_code"] == "admin":
            admin_user = user

    db.commit()
    assert admin_user is not None, "admin user must be created"
    return {"dept": dept_map, "role": role_map, "admin_user": admin_user}


def _seed_one_document(
    db: Session,
    src: Path,
    filename: str,
    perm_level: str,
    department_id: int | None,
    admin_user: User,
) -> None:
    """單份文件：複製檔案 → 建 ORM 紀錄 → embedding → ChromaDB。失敗在這層 catch，不影響其他文件。"""
    dst = SEED_UPLOAD_DIR / filename
    shutil.copyfile(src, dst)

    content = src.read_bytes()
    checksum = hashlib.sha256(content).hexdigest()
    file_size = len(content)
    file_type = filename.rsplit(".", 1)[-1].lower()

    # 建 document + version（直接設 approved + processing）
    doc = KnowledgeDocument(
        filename=filename,
        file_type=file_type,
        permission_level=perm_level,
        department_id=department_id,
        uploaded_by=admin_user.id,
    )
    db.add(doc)
    db.flush()

    version = KnowledgeDocVersion(
        document_id=doc.id,
        version=1,
        file_path=str(dst).replace("\\", "/"),
        file_size=file_size,
        checksum=checksum,
        status="approved",
        vectorization_status="processing",
        uploaded_by=admin_user.id,
        reviewed_by=admin_user.id,
        reviewed_at=datetime.utcnow(),
    )
    db.add(version)
    db.flush()

    doc.current_version_id = version.id
    db.commit()

    # 向量化
    try:
        text = extract_text_from_file(str(dst), file_type)
        chunks = chunk_text(text)
        if not chunks:
            raise ValueError("no chunks produced (empty file?)")

        embeddings = get_embeddings_batch(chunks)
        metadata = {
            "document_title": filename,
            "permission_level": perm_level,
            "department_id": department_id or 0,
        }
        # 防禦性清理：切換 DB 後可能有同 ID 的殘留 chunk（Render 環境下 no-op）
        delete_document_chunks(doc.id)
        chunk_count = add_chunks(doc.id, chunks, embeddings, metadata)

        version.vectorization_status = "completed"
        version.chunk_count = chunk_count
        db.commit()
        print(f"[seed] vectorized: {filename} ({chunk_count} chunks)")
    except Exception as exc:
        version.vectorization_status = "failed"
        version.error_message = str(exc)[:500]
        db.commit()
        print(f"[seed] vectorization FAILED for {filename}: {exc}")


def _seed_documents(db: Session, ctx: dict) -> None:
    if not SEED_DOCS_DIR.exists():
        print(f"[seed] {SEED_DOCS_DIR} not found, skip documents")
        return

    SEED_UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

    for filename, perm_level, dept_code in DOCUMENTS:
        src = SEED_DOCS_DIR / filename
        if not src.exists():
            print(f"[seed] skip missing file: {filename}")
            continue

        department_id = ctx["dept"][dept_code] if dept_code else None
        _seed_one_document(
            db=db,
            src=src,
            filename=filename,
            perm_level=perm_level,
            department_id=department_id,
            admin_user=ctx["admin_user"],
        )


def run_seed_sync() -> None:
    """同步版 seed 入口（lifespan 用 asyncio.to_thread 包起來跑）。"""
    # SQLite 第一次啟動需要建表；MySQL 已有 schema 則 create_all 是 no-op
    Base.metadata.create_all(bind=engine)

    db = SessionLocal()
    try:
        if _already_seeded(db):
            print("[seed] already seeded, skip")
            return

        print("[seed] start...")
        ctx = _seed_rbac(db)
        _seed_documents(db, ctx)
        print("[seed] done")
    except Exception as exc:
        db.rollback()
        print(f"[seed] FATAL: {exc}")
        raise
    finally:
        db.close()
