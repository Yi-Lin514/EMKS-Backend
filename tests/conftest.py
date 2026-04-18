import os

# Force sqlite before any app module imports
os.environ["DATABASE_URL"] = "sqlite:///:memory:"
os.environ.setdefault("JWT_SECRET_KEY", "test-secret-key")
os.environ.setdefault("CORS_ORIGINS", "http://localhost")

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from slowapi.errors import RateLimitExceeded
from fastapi.responses import JSONResponse

from app.database import Base, get_db
from app.models import (
    User, UserStatus, Role, Permission, UserRole, RolePermission, ScopeType,
)
from app.services.auth import hash_password
from app.rate_limit import limiter
from app.routers.auth import router as auth_router


@pytest.fixture(scope="session")
def engine():
    eng = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=eng)
    return eng


@pytest.fixture
def db(engine):
    """每個 test 自己一個 session；結束後清空所有 table 保證隔離。"""
    TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    session = TestingSessionLocal()
    try:
        yield session
    finally:
        session.close()
        # 反向刪除避免外鍵衝突
        with engine.begin() as conn:
            for table in reversed(Base.metadata.sorted_tables):
                conn.execute(table.delete())


@pytest.fixture
def app(db):
    """Minimal app with auth router + rate limit handler；rate limiter 預設關掉避免污染測試。"""
    limiter.enabled = False
    application = FastAPI()
    application.state.limiter = limiter

    @application.exception_handler(RateLimitExceeded)
    async def _rate_limit_handler(request, exc):
        return JSONResponse(status_code=429, content={"detail": str(exc.detail)})

    application.include_router(auth_router)

    def override_get_db():
        try:
            yield db
        finally:
            pass

    application.dependency_overrides[get_db] = override_get_db
    return application


@pytest.fixture
def client(app):
    return TestClient(app)


@pytest.fixture
def make_user(db):
    """建立 active user，可選擇給定 permission codes（自動建立 role 並掛上）。"""

    def _make(
        email: str = "test@demo.com",
        password: str = "password123",
        permissions: list[str] | None = None,
        status: UserStatus = UserStatus.active,
    ) -> User:
        user = User(
            email=email,
            password_hash=hash_password(password),
            name=email.split("@")[0],
            status=status,
        )
        db.add(user)
        db.flush()

        if permissions:
            role = Role(code=f"role_{user.id}", name=f"role for {email}")
            db.add(role)
            db.flush()

            for code in permissions:
                perm = db.query(Permission).filter(Permission.code == code).first()
                if not perm:
                    resource, action = code.split(":", 1)
                    perm = Permission(code=code, name=code, resource=resource, action=action)
                    db.add(perm)
                    db.flush()
                db.add(RolePermission(role_id=role.id, permission_id=perm.id))

            db.add(UserRole(user_id=user.id, role_id=role.id, scope_type=ScopeType.GLOBAL))

        db.commit()
        db.refresh(user)
        return user

    return _make
