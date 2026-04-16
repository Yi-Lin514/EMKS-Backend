# FastAPI 應用程式進入點

import asyncio
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.config import settings
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


async def _run_seed_background() -> None:
    """背景跑 seed。失敗不 propagate（不讓 seed 失敗導致 server 掛掉），但會印出 traceback。"""
    try:
        await asyncio.to_thread(run_seed_sync)
    except Exception:
        import traceback
        traceback.print_exc()


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

# CORS 設定
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS.split(","),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

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
