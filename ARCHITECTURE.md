# EMKS — Architecture & Technical Deep Dive

> 本文件是完整的技術細節參考，README 放重點摘要。

---

## System Overview

```
┌──────────────────────────────────────────────────────────────────────┐
│                          EMKS 系統架構                               │
│                                                                      │
│  ┌────────────────────┐           ┌─────────────────────────────┐   │
│  │  Vue 3 SPA         │   fetch   │  FastAPI Backend             │   │
│  │  (Vercel)          │ ───SSE──► │  (Render)                    │   │
│  │                    │           │                              │   │
│  │  Pinia Stores      │   axios   │  Router → Service → Model   │   │
│  │  ├ auth (JWT)      │ ───REST─► │  │                          │   │
│  │  ├ user/dept/role  │           │  ├ auth.py    (JWT+RBAC)    │   │
│  │  ├ toast/loading   │           │  ├ agent.py   (LangGraph)   │   │
│  │  └ hasPermission() │           │  ├ rag.py     (LlamaIndex)  │   │
│  │                    │           │  ├ embedding  (OpenAI)      │   │
│  │  Route Guards      │           │  └ vector_store (ChromaDB)  │   │
│  │  ├ 登入檢查        │           │                              │   │
│  │  ├ 權限檢查        │           │  Dependencies               │   │
│  │  └ 已登入導回      │           │  └ rbac.py (require_perm)   │   │
│  └────────────────────┘           └──────────┬──────────────────┘   │
│                                              │                       │
│                            ┌─────────────────┼─────────────────┐     │
│                            │                 │                 │     │
│                      ┌─────▼──────┐   ┌──────▼──────┐  ┌──────▼───┐ │
│                      │  MySQL 8   │   │  ChromaDB    │  │  OpenAI  │ │
│                      │  15 tables │   │  HNSW index  │  │  API     │ │
│                      │  users     │   │  cosine sim  │  │  GPT-4o  │ │
│                      │  documents │   │  pre-filter  │  │  -mini   │ │
│                      │  chat_msg  │   │  by RBAC     │  │  embed-  │ │
│                      │  roles     │   │              │  │  ding-3  │ │
│                      └────────────┘   └─────────────┘  └──────────┘ │
└──────────────────────────────────────────────────────────────────────┘
```

**部署拓撲**：Backend on Render (Singapore, Free tier, Docker) / Frontend on Vercel (Hobby, Vite) / MySQL + ChromaDB 跟 container 綁定（Free tier 限制）

---

## Backend 分層架構

```
Router（HTTP 層）→ Service（業務邏輯）→ Model（ORM）→ Database
         │
         └─ Dependencies（rbac.py：權限檢查注入）
```

### 目錄結構

```
app/
├── main.py                 FastAPI 進入點、router 註冊、CORS、lifespan（seed）
├── config.py               Settings（pydantic_settings，讀 .env）
├── database.py             SQLAlchemy engine + SessionLocal + Base
├── dependencies/
│   └── rbac.py             get_user_permissions / require_admin / require_permission
├── models/
│   ├── user.py             User（含 lockout 欄位）
│   ├── role.py             Role
│   ├── permission.py       Permission（code = "resource:action"）
│   ├── department.py       Department（self-ref parent）
│   ├── role_permission.py  Role ↔ Permission junction
│   ├── user_role.py        User ↔ Role junction（含 scope）
│   ├── user_token.py       JWT refresh / reset / activation tokens
│   ├── login_history.py    登入稽核
│   └── knowledge.py        Folder / Document / Version / Favorite / Conversation / Message
├── schemas/                Pydantic request/response DTOs
├── routers/
│   ├── auth.py             登入 / 登出 / refresh / 忘記密碼 / 啟用帳號
│   ├── user.py             CRUD + profile
│   ├── department.py       CRUD
│   ├── role.py             CRUD + 權限指派
│   ├── permission.py       列表
│   ├── folder.py           資料夾 CRUD
│   ├── document.py         文件上傳 / 列表 / 下載 / 版本
│   ├── review.py           文件審核流程
│   ├── favorite.py         收藏
│   └── ai.py               SSE 串流對話 + 對話紀錄 CRUD
├── services/
│   ├── auth.py             JWT 生成/驗證、bcrypt、token lifecycle
│   ├── agent.py            LangGraph Agent（4 tools + streaming）
│   ├── rag.py              RAG 工具函式（context builder / permission filter / condense）
│   ├── embedding.py        chunk_text + OpenAI embedding API + PDF 解析
│   ├── vector_store.py     ChromaDB CRUD
│   ├── document.py         文件上傳 + 向量化 pipeline
│   ├── conversation.py     對話 CRUD
│   ├── email.py            SMTP / console 雙模式寄信
│   ├── review.py           審核邏輯
│   ├── folder.py           資料夾邏輯
│   ├── favorite.py         收藏邏輯
│   ├── user.py             User helper
│   └── prompt.py           共用 prompt
└── seed/
    └── seed_demo.py        Demo 資料（4 帳號 + 8 文件 + 角色權限）
```

---

## API Endpoints（51 個）

### Auth（8）
| Method | Path | Auth | 說明 |
|--------|------|------|------|
| POST | `/auth/login` | - | 登入（lockout after 5 failed） |
| POST | `/auth/refresh` | - | 換發 access token |
| POST | `/auth/logout` | JWT | 登出（revoke refresh） |
| POST | `/auth/forgot-password` | - | 寄重設密碼信 |
| POST | `/auth/reset-password` | - | 重設密碼 |
| POST | `/auth/activate-account` | - | 啟用帳號 |
| GET | `/auth/verify-token` | - | 驗證 reset/activation token 是否有效（前端頁面載入用） |
| GET | `/auth/login-history` | system:view | 登入稽核紀錄（分頁） |

### User（8）
| Method | Path | Auth | 說明 |
|--------|------|------|------|
| GET | `/users/me` | JWT | 自己的 profile |
| PUT | `/users/me` | JWT | 改自己資料 |
| PUT | `/users/me/password` | JWT | 改自己密碼 |
| GET | `/users` | user:view | 列表（搜尋 / 篩選 / 分頁） |
| GET | `/users/{id}` | user:view | 單一使用者詳情 |
| POST | `/users` | user:create | 建帳號（寄啟用信） |
| PUT | `/users/{id}` | user:edit | 改帳號 |
| DELETE | `/users/{id}` | user:delete | 刪帳號 |

### Department（5）
| Method | Path | Auth | 說明 |
|--------|------|------|------|
| GET | `/departments` | department:view | 列表（樹狀 + 成員統計） |
| GET | `/departments/{id}` | department:view | 單一部門 |
| POST | `/departments` | department:create | 建部門（自動算 level） |
| PUT | `/departments/{id}` | department:edit | 改部門 |
| DELETE | `/departments/{id}` | department:delete | 刪部門（有子節點或文件時拒絕） |

### Role & Permission（8）
| Method | Path | Auth | 說明 |
|--------|------|------|------|
| GET | `/roles` | role:view | 角色列表 |
| GET | `/roles/{id}` | role:view | 單一角色 |
| POST | `/roles` | role:create | 建角色（code 唯一） |
| PUT | `/roles/{id}` | role:edit | 改角色 |
| DELETE | `/roles/{id}` | role:delete | 刪角色 |
| GET | `/roles/{id}/permissions` | role:view | 該角色擁有的權限 |
| PUT | `/roles/{id}/permissions` | role:edit | 批次取代角色權限（先刪全建） |
| GET | `/permissions` | role:view | 全部權限碼列表 |

### Knowledge — Folder（4）
| Method | Path | Auth | 說明 |
|--------|------|------|------|
| POST | `/knowledge/folders` | admin | 建資料夾 |
| GET | `/knowledge/folders/tree` | JWT | 資料夾樹 |
| PUT | `/knowledge/folders/{id}` | admin | 改資料夾 |
| DELETE | `/knowledge/folders/{id}` | admin | 刪資料夾（有子節點或文件時拒絕） |

### Knowledge — Document（8）
| Method | Path | Auth | 說明 |
|--------|------|------|------|
| POST | `/knowledge/documents` | JWT | 上傳文件（支援多檔，.txt / .pdf） |
| GET | `/knowledge/documents` | JWT | 文件列表 |
| GET | `/knowledge/documents/{id}` | JWT | 單一文件詳情 |
| DELETE | `/knowledge/documents/{id}` | JWT | 軟刪文件 + 清 ChromaDB chunks |
| POST | `/knowledge/documents/{id}/versions` | JWT | 上傳新版本（checksum 防重複） |
| GET | `/knowledge/documents/{id}/versions` | JWT | 版本列表 |
| GET | `/knowledge/documents/{id}/versions/{vid}/download` | JWT | 下載指定版本 |
| POST | `/knowledge/documents/{id}/versions/{vid}/restore` | JWT | 還原到舊版本（建新版，需重審） |

### Knowledge — Review（3）
| Method | Path | Auth | 說明 |
|--------|------|------|------|
| GET | `/knowledge/review` | admin | 待審清單 |
| POST | `/knowledge/review/{id}/approve` | admin | 審核通過（觸發同步向量化） |
| POST | `/knowledge/review/{id}/reject` | admin | 駁回（記錄原因） |

### Knowledge — Favorite（3）
| Method | Path | Auth | 說明 |
|--------|------|------|------|
| POST | `/knowledge/favorites/{id}` | JWT | 收藏文件 |
| DELETE | `/knowledge/favorites/{id}` | JWT | 取消收藏 |
| GET | `/knowledge/favorites` | JWT | 我的收藏列表 |

### AI（4）
| Method | Path | Auth | 說明 |
|--------|------|------|------|
| POST | `/ai/agent` | JWT | SSE 串流 AI 對話 |
| GET | `/ai/conversations` | JWT | 對話列表 |
| GET | `/ai/conversations/{id}/messages` | JWT | 對話歷史 |
| DELETE | `/ai/conversations/{id}` | JWT | 刪對話 |

---

## DB Schema

### ER Diagram

```
departments ◄──────────── users ─────────────► login_history
    │  (department_id)      │
    │                       ├──► user_roles ──► roles ──► role_permissions ──► permissions
    │                       ├──► user_tokens
    │                       ├──► chat_conversations ──► chat_messages (sources JSON)
    │                       └──► knowledge_favorites
    │
    └──► knowledge_folders ──► knowledge_documents ──► knowledge_doc_versions
                                      │                        │
                                      └── current_version_id ──┘
```

### 資料表概覽（15 tables）

| Table | 用途 | 重要欄位 |
|-------|------|---------|
| **users** | 使用者 | email(unique), password_hash, department_id, status(active/inactive/suspended), failed_login_count, locked_until |
| **departments** | 部門 | parent_id(self-ref), manager_id, level |
| **roles** | 角色 | code(unique), is_system |
| **permissions** | 權限 | code("resource:action"), resource, action |
| **role_permissions** | 角色↔權限 | composite PK (role_id, permission_id) |
| **user_roles** | 使用者↔角色 | scope_type(global/department), scope_department_id |
| **user_tokens** | Token 管理 | token_type(refresh/reset_password/email_verify/activation), token_hash(SHA-256), is_revoked, expires_at |
| **login_history** | 登入稽核 | attempted_email, ip, user_agent, device_type, login_status, failure_reason |
| **password_history** | 密碼歷史 | user_id, password_hash（SQL 有建表，app 層未使用，預留防重複密碼） |
| **knowledge_folders** | 資料夾 | parent_id(self-ref), department_id |
| **knowledge_documents** | 文件 | permission_level(public/department), current_version_id, is_deleted(soft) |
| **knowledge_doc_versions** | 文件版本 | version(int), status(pending/approved/rejected), vectorization_status(none/processing/completed/failed), checksum(SHA-256) |
| **knowledge_favorites** | 收藏 | unique(user_id, document_id) |
| **chat_conversations** | 對話 | user_id, title |
| **chat_messages** | 訊息 | role(user/assistant), content(Text), sources(JSON) |

### 預設角色權限矩陣

SQL 定義 23 個權限碼（含 manage 類），下表簡化為主要操作：

| 角色 | 文件 | 使用者 | 部門 | 角色 | 系統 | AI |
|------|------|--------|------|------|------|-----|
| super_admin | 全部 | 全部 | 全部 | 全部 | 全部 | chat + admin_tools + manage |
| dept_admin | CRUD | view/create/edit | view/edit | - | - | chat |
| editor | view/create/edit | - | - | - | - | chat |
| viewer | view | - | - | - | - | chat |
| guest | view | - | - | - | - | - |

---

## AI 問答 — 完整資料流

### Entry Point

`POST /ai/agent` → SSE streaming generator

### 流程圖

```
使用者輸入 question
    │
    ▼
Router (ai.py)
    ├─ JWT 驗證 → get_current_user
    ├─ ContextVar 設定 user context（thread-safe，跨 thread 傳遞）
    └─ 回傳 StreamingResponse(media_type="text/event-stream")
           │
           ▼
    run_agent_stream() generator
        │
        ├─ 1. get_or_create_conversation → yield { type: conversation_id }
        ├─ 2. save user message to MySQL
        ├─ 3. 載入 chat history
        ├─ 4. _build_agent_app(is_admin)
        │       │
        │       └─ LangGraph StateGraph
        │            START → agent_node → should_continue?
        │                                  ├─ has tool_calls → ToolNode → agent_node (loop)
        │                                  └─ no tool_calls  → END
        │
        ├─ 5. agent_app.stream(mode="messages")
        │       └─ 每個 AIMessageChunk → yield { type: token, content: "..." }
        │
        ├─ 6. 收集 ContextVar sources
        │       └─ 偵測拒答關鍵詞 → 有拒答就不送 sources
        │
        ├─ 7. yield { type: sources, sources: [...] }
        ├─ 8. yield { type: done }
        └─ 9. save assistant message + sources to MySQL
```

### LangGraph Agent 架構

```
Agent Tools（動態組裝）
    │
    ├─ 全員可用（EMPLOYEE_TOOLS）
    │   ├─ search_knowledge_base(query)   ← RAG 核心
    │   ├─ get_recent_documents(days=7)   ← 最近文件異動
    │   └─ get_pending_reviews()          ← 待審文件
    │
    └─ Admin 限定（ADMIN_ONLY_TOOLS）
        └─ get_popular_questions(days=7, limit=5)  ← 熱門問題統計

Graph 編譯：
    is_admin=True  → bind_tools(EMPLOYEE + ADMIN_ONLY)
    is_admin=False → bind_tools(EMPLOYEE only)
```

### RAG Search Pipeline（search_knowledge_base 內部）

```
1. 多輪改寫
   chat_history + question → condense_question()（LlamaIndex OpenAI LLM）
   └─ 將追問改寫為獨立問句

2. 向量搜尋
   search_query → get_embedding()（OpenAI text-embedding-3-small）
              → search_chunks(embedding, n=5, where=permission_filter)
                  │
                  └─ ChromaDB cosine similarity + RBAC pre-filter
                       ├─ admin     → 無 filter
                       ├─ 部門員工  → { $or: [public, department_id] }
                       └─ 其他     → { permission_level: public }

3. 後處理
   results → filter(relevance >= 0.35)
           → dedup by document_id（保留最高分 chunk）
           → top 5 排序
           → 存入 ContextVar sources
           → 回傳格式化文字給 LLM
```

---

## 文件上傳 → 向量化 Pipeline

```
前端上傳 .txt/.pdf
    │
    ▼
save_uploaded_file()
    └─ uploads/knowledge/{YYYY/MM}/{uuid}.{ext}
    └─ 回傳 (file_path, size, type, SHA-256 checksum)
    │
    ▼
create_document()
    └─ MySQL: KnowledgeDocument + Version v1 (status=pending)
    │
    ▼
Admin 審核通過 → process_vectorization()
    │
    ├─ extract_text_from_file()
    │   ├─ .txt → 直接讀取
    │   └─ .pdf → pymupdf (fitz) 逐頁擷取
    │
    ├─ chunk_text(text, chunk_size=500, overlap=50)
    │   └─ 滑動窗口切塊
    │
    ├─ get_embeddings_batch(chunks)
    │   └─ OpenAI text-embedding-3-small API
    │
    ├─ delete_document_chunks(document_id)  ← 清舊向量
    │
    ├─ add_chunks(document_id, chunks, embeddings, metadata)
    │   └─ ChromaDB: ID = doc{id}_chunk{i}
    │   └─ metadata: { document_id, title, permission_level, department_id }
    │
    └─ version.vectorization_status = "completed"
       version.chunk_count = N
```

---

## RBAC 權限系統

### 資料模型

```
User ──M:N──► UserRole ──► Role ──M:N──► RolePermission ──► Permission
                │                                              │
                ├─ scope_type: global / department              ├─ code: "resource:action"
                └─ scope_department_id                         └─ ex: user:create, ai:chat
```

### 檢查流程

```
HTTP Request
    │
    ├─ get_current_user()        ← JWT decode → User model
    │
    ├─ require_permission(code)  ← Factory dependency
    │   └─ get_user_permissions(db, user_id)
    │       └─ UserRole → RolePermission → Permission
    │       └─ 回傳 List[str] of permission codes
    │       └─ 403 if code not in list
    │
    └─ require_admin             ← Shortcut：有任何 "user:" 開頭權限就算 admin
```

### 雙層權限過濾（AI 問答特有）

注意：AI 的 admin 判定跟後台管理不同。後台管理用 `require_admin`（有任何 `user:` 開頭權限），AI agent 用 `ai:admin_tools` 權限碼（`routers/ai.py:28`）。這是刻意分開的 — 可以讓某人管後台但不開放 admin 專屬 AI 工具，反之亦然。

```
第一層：Graph 層面（功能級）
    _check_admin() → "ai:admin_tools" in permissions
    _build_agent_app(is_admin)
    └─ admin 才掛 ADMIN_ONLY_TOOLS → non-admin 的 LLM 根本看不到 get_popular_questions

第二層：Tool 內部（資料級）
    search_knowledge_base → build_permission_filter(is_admin, dept_id)
    └─ ChromaDB where clause 過濾可見文件
    get_popular_questions → 內部再驗一次 is_admin（防 bind tools 層 bug / cache 污染）
```

---

## 認證流程

### JWT Token Lifecycle

```
登入成功
    ├─ create_access_token(user_id)   → 30 min expiry
    ├─ create_refresh_token(user_id)  → 7 days expiry
    └─ save_refresh_token(db, hash)   → user_tokens 表

API 請求
    └─ Authorization: Bearer {access_token}
       └─ verify_token → user_id → get User from DB

Token 過期
    └─ 前端 axios interceptor 攔 401
       └─ POST /auth/refresh + refresh_token
          └─ 驗證 token 未 revoked → 發新 access_token
          └─ 重送原 request（subscriber queue 防 thundering herd）

登出
    └─ revoke_token → user_tokens.is_revoked = True
```

### 帳號安全機制

- **登入鎖定**：連續 5 次失敗 → 鎖 15 分鐘
- **密碼雜湊**：bcrypt（passlib）
- **Token 儲存**：DB 只存 SHA-256 hash，不存明文
- **密碼重設**：一次性 token，1 小時過期，用過即 revoke
- **登入稽核**：login_history 記錄 IP / user-agent / device type / 成功失敗

---

## Frontend 架構

### 技術棧

| 類別 | 技術 | 版本 |
|------|------|------|
| 框架 | Vue 3 (Composition API + `<script setup>`) | 3.5.25 |
| 建置 | Vite | 7.2.4 |
| 路由 | Vue Router | 4.6.3 |
| 狀態管理 | Pinia | 3.0.4 |
| HTTP | Axios | 1.13.2 |
| UI 元件 | Element Plus | 2.13.2 |
| 樣式 | Tailwind CSS + CSS Variables | 3.4.19 |
| 字型 | Plus Jakarta Sans (heading) + Noto Sans TC (body) | - |

### 目錄結構

```
src/
├── main.js               Vue app 進入點
├── App.vue               Root（RouterView + AppLayout）
├── router/index.js        10 routes + beforeEach 三層守衛
├── stores/
│   ├── auth.js            JWT tokens + user + hasPermission()
│   ├── user.js            使用者 CRUD（搜尋 / 篩選 / 分頁）
│   ├── department.js      部門 CRUD
│   ├── role.js            角色 + 權限指派
│   ├── loading.js         全域 loading（counter pattern）
│   └── toast.js           全域通知（auto-dismiss 2s）
├── utils/
│   └── axios.js           interceptors + auto refresh token（subscriber queue）
├── components/
│   ├── AppLayout.vue      側邊欄（手風琴）+ 頂部列 + content slot
│   ├── AppToast.vue       Toast 通知
│   ├── AppLoading.vue     全域 loading overlay
│   └── knowledge/
│       ├── FolderSidebar.vue       資料夾樹（新增 / 改名 / 刪除）
│       └── VersionHistoryModal.vue  版本歷史 modal
├── views/
│   ├── LoginView.vue              登入（含冷啟動偵測）
│   ├── ForgotPasswordView.vue     忘記密碼
│   ├── ResetPasswordView.vue      重設密碼
│   ├── ProfileView.vue            個人資料（3 tabs）
│   ├── AiChatView.vue             AI 問答（SSE streaming）
│   ├── KnowledgeBaseView.vue      知識庫（4 tabs）
│   ├── UsersView.vue              使用者管理
│   ├── DepartmentsView.vue        部門管理
│   ├── RolesView.vue              角色管理
│   └── LoginHistoryView.vue       登入稽核
└── assets/
    ├── variables.css       CSS 變數（色彩 / 字型 / layout）
    └── main.css            Tailwind imports + global styles
```

### SSE Streaming 實作

```
AiChatView.vue
    │
    ├─ fetch(POST /ai/agent, { headers: Bearer JWT })
    │   └─ 不用 EventSource — 要帶 JWT header
    │
    ├─ response.body.getReader()
    │   └─ ReadableStream + TextDecoder
    │
    └─ while loop 讀 chunk
        ├─ buffer 累積 → split("\n\n") 切 SSE events
        ├─ "data: {...}" → JSON.parse
        │   ├─ type: "conversation_id" → 設定 conversationId
        │   ├─ type: "token"           → aiMessage.content += data.content（逐字渲染）
        │   ├─ type: "sources"         → aiMessage.sources = data.sources
        │   └─ type: "done"            → 結束
        └─ error → fallback 錯誤訊息
```

### 路由守衛

```
beforeEach(to, from, next)
    │
    ├─ to.meta.requiresAuth && !authenticated → redirect /
    ├─ authenticated && to.path === "/" → redirect /ai-chat
    └─ to.meta.requiredPermission && !hasPermission → redirect /ai-chat
```

---

## Docker 配置

### docker-compose.yml（4 containers）

```
┌─────────────┐  ┌─────────────┐  ┌──────────────┐  ┌─────────────┐
│   mysql      │  │  chromadb    │  │   backend    │  │  frontend   │
│   :3307→3306 │  │  :8100→8000 │  │   :8000      │  │   :80       │
│              │  │              │  │              │  │  nginx      │
│  init: SQL   │  │  persistent  │  │  depends:    │  │  /api/ →    │
│  vol: data   │  │  vol: data   │  │  mysql+chroma│  │  backend    │
└─────────────┘  └─────────────┘  └──────────────┘  └─────────────┘
```

### Backend Dockerfile

```dockerfile
FROM python:3.12-slim
ENV PYTHONUNBUFFERED=1
RUN pip install uv
WORKDIR /app
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev
COPY app/ ./app/
COPY seed_docs/ ./seed_docs/
EXPOSE 8000
CMD uv run uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}
```

### Frontend Dockerfile（multi-stage）

```dockerfile
# Stage 1: Build
FROM node:22-alpine AS build
COPY package*.json ./
RUN npm ci
COPY . .
RUN VITE_API_URL=/api npm run build

# Stage 2: Serve
FROM nginx:alpine
COPY --from=build /app/dist /usr/share/nginx/html
COPY nginx.conf /etc/nginx/conf.d/default.conf
```

---

## 設定參數一覽（config.py）

| 類別 | 參數 | 預設值 | 說明 |
|------|------|--------|------|
| **JWT** | JWT_ALGORITHM | HS256 | |
| | ACCESS_TOKEN_EXPIRE_MINUTES | 30 | |
| | REFRESH_TOKEN_EXPIRE_DAYS | 7 | |
| **OpenAI** | LLM_MODEL | gpt-4o-mini | |
| | LLM_TEMPERATURE | 0.0 | 降低隨機性 |
| | LLM_MAX_TOKENS | 1024 | |
| | EMBEDDING_MODEL | text-embedding-3-small | |
| **RAG** | CHUNK_SIZE | 500 | chars per chunk |
| | CHUNK_OVERLAP | 50 | sliding window overlap |
| | RAG_SEARCH_RESULTS | 5 | top-k |
| | RAG_RELEVANCE_THRESHOLD | 0.35 | 低於此分數過濾掉 |
| **Upload** | ALLOWED_EXTENSIONS | txt, pdf | |
| **Email** | EMAIL_MODE | console | console(dev) / smtp(prod) |
| | PASSWORD_RESET_EXPIRE_HOURS | 1 | |

---

## 已知技術債 & 優化空間

### 值得做（面試加分）

| # | 問題 | 位置 | 建議 |
|---|------|------|------|
| 1 | 向量化同步阻塞 | `services/document.py:224` | Production 用 Celery + 回 202 Accepted |
| 2 | 缺 DB index | `chat_messages.created_at`, `knowledge_doc_versions.created_at` | 加 index 改善查詢效能 |
| 3 | SSE 無 AbortController | `AiChatView.vue` | 離開頁面時主動取消 stream |
| 4 | Auth 無 rate limit | `POST /auth/login` | Redis-backed throttle |

### 知道就好（面試能講）

| # | 問題 | 說明 |
|---|------|------|
| 5 | user_tokens 無清理 | 過期 token 不刪，表無限長。Production 加 cron |
| 6 | 上傳只驗副檔名 | 不驗 MIME type，惡意 PDF 可能 crash pymupdf |
| 7 | Permission 每次 JOIN 3 表 | 量大加 Redis TTL cache |
| 8 | Structured logging 尚未覆蓋全層 | 基礎已建（loguru + request_id / user_id ContextVar + middleware，見 [STRUCTURED-LOGGING-NOTES.md](../STRUCTURED-LOGGING-NOTES.md)）；SSE agent 每輪 tool call 的 structured log 尚未補 |
| 9 | iterate_in_threadpool 不保證同 thread | 技術債故意保留（成本 vs 風險評估過） |

---

## 外部依賴版本

### Backend（Python ≥ 3.12）

| Library | Version | 用途 |
|---------|---------|------|
| fastapi | 0.127+ | Web framework |
| sqlalchemy | 2.0+ | ORM |
| pydantic-settings | - | Config from .env |
| openai | ≥ 2.26 | GPT-4o-mini + embedding |
| langgraph | ≥ 1.1.3 | Agent state machine |
| langchain-openai | ≥ 1.1.12 | ChatOpenAI wrapper |
| langchain-core | ≥ 1.2.22 | Messages / Tools |
| llama-index | ≥ 0.14.18 | Condense question |
| chromadb | ≥ 1.5.5 | Vector store |
| pymupdf | ≥ 1.27.2 | PDF text extraction |
| passlib[bcrypt] | - | Password hashing |
| python-jose[cryptography] | - | JWT |
| pymysql | - | MySQL driver |
| python-multipart | - | File upload (Form/File) |

### Frontend（Node ≥ 20.19）

| Library | Version | 用途 |
|---------|---------|------|
| vue | 3.5.25 | UI framework |
| vue-router | 4.6.3 | Routing |
| pinia | 3.0.4 | State management |
| axios | 1.13.2 | HTTP client |
| element-plus | 2.13.2 | UI components |
| tailwindcss | 3.4.19 | Utility CSS |
| vite | 7.2.4 | Build tool |
| vitest | 4.0.18 | Testing |
