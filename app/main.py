# FastAPI 應用程式進入點

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.routers import (
    auth_router,
    user_router,
    department_router,
    role_router,
    permission_router,
    knowledge_folder_router,
    knowledge_document_router,
    knowledge_review_router,
    knowledge_favorite_router,
    ai_router,
)

# 強制載入所有 ORM 類別，確保關聯表正確建立
from app.models import User, KnowledgeDocument

# 建立 FastAPI 應用程式實例
app = FastAPI(
    title="企業內部知識管理系統 API",
    version="1.0.0"
)

# CORS 設定
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://localhost:5174"],
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
app.include_router(knowledge_folder_router)
app.include_router(knowledge_document_router)
app.include_router(knowledge_review_router)
app.include_router(knowledge_favorite_router)
app.include_router(ai_router)

@app.get("/")
def root():
    return {"message": "企業內部知識管理系統 API"}
