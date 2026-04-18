# FastAPI 應用程式進入點

import asyncio
from contextlib import asynccontextmanager
from time import perf_counter
from uuid import uuid4

from fastapi import FastAPI, Depends, Request
from fastapi.middleware.cors import CORSMiddleware
from loguru import logger
from slowapi.errors import RateLimitExceeded
from sqlalchemy.orm import Session
from app.config import settings
from app.database import get_db
from app.logging_config import configure_logging, request_id_var
from app.rate_limit import limiter
from app.routers import (
    auth_router,
    user_router,
    department_router,
    role_router,
    permission_router,
    folder_router,
    document_router,
    review_router,
    favorite_router,
    ai_router,
)

# 強制載入所有 ORM 類別，確保關聯表正確建立
from app.models import User, KnowledgeDocument
from app.seed import run_seed_sync

# 啟動時設定 logging（module import 就執行一次）
configure_logging()


async def _run_seed_background() -> None:
    """背景跑 seed。失敗不 propagate（不讓 seed 失敗導致 server 掛掉），log 會附 traceback。"""
    try:
        await asyncio.to_thread(run_seed_sync)
    except Exception:
        logger.exception("seed background task crashed")


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup：非同步背景跑 seed，不 block health check
    # 存 task reference 在 app.state，否則 asyncio 會把沒人引用的 task GC 掉（官方文件有警告）
    app.state.seed_task = asyncio.create_task(_run_seed_background())
    yield
    # Shutdown：目前無需清理


# 建立 FastAPI 應用程式實例
app = FastAPI(
    title="企業內部知識管理系統 API",
    version="1.0.0",
    lifespan=lifespan,
)

# Rate limiting — key = user_id (from JWT) 或 IP fallback；見 app/rate_limit.py
app.state.limiter = limiter


@app.exception_handler(RateLimitExceeded)
async def rate_limit_handler(request: Request, exc: RateLimitExceeded):
    from fastapi.responses import JSONResponse

    logger.bind(
        path=request.url.path,
        limit=str(exc.detail),
    ).warning(f"rate limit hit: {request.url.path} ({exc.detail})")
    response = JSONResponse(
        status_code=429,
        content={"detail": f"請求過於頻繁，請稍後再試（{exc.detail}）"},
    )
    response.headers["Retry-After"] = "60"
    return response


# CORS 設定
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS.split(","),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def request_id_middleware(request: Request, call_next):
    """每個 request 產生 / 讀取 request_id，塞進 ContextVar 讓整條鏈路 log 都能帶上。"""
    rid = request.headers.get("x-request-id") or uuid4().hex[:12]
    token = request_id_var.set(rid)
    start = perf_counter()
    try:
        response = await call_next(request)
        duration_ms = round((perf_counter() - start) * 1000)
        logger.bind(
            method=request.method,
            path=request.url.path,
            status=response.status_code,
            duration_ms=duration_ms,
        ).info(f"{request.method} {request.url.path} -> {response.status_code} ({duration_ms}ms)")
        response.headers["X-Request-ID"] = rid
        return response
    except Exception:
        duration_ms = round((perf_counter() - start) * 1000)
        logger.bind(
            method=request.method,
            path=request.url.path,
            duration_ms=duration_ms,
        ).exception(f"{request.method} {request.url.path} crashed ({duration_ms}ms)")
        raise
    finally:
        request_id_var.reset(token)


# 路由註冊
app.include_router(auth_router)
app.include_router(user_router)
app.include_router(department_router)
app.include_router(role_router)
app.include_router(permission_router)
app.include_router(folder_router)
app.include_router(document_router)
app.include_router(review_router)
app.include_router(favorite_router)
app.include_router(ai_router)

@app.get("/")
def root():
    return {"message": "企業內部知識管理系統 API"}


@app.get("/health/ready")
def health_ready(db: Session = Depends(get_db)):
    """Seed 是否完成 — 冷啟動期間前端 LoginView 用來決定要不要顯示 loading overlay。"""
    try:
        admin = db.query(User).filter(User.email == "admin@demo.com").first()
        return {"ready": admin is not None}
    except Exception:
        return {"ready": False}
