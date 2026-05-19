# EMKS — 企業內部知識管理系統

AI 驅動的企業知識管理平台：文件管理 + RAG 問答 + Agent 自動化，依 RBAC 權限過濾每個人能看到的知識。

**Live Demo**: https://emks-frontend.vercel.app（首次載入需等 30-120 秒冷啟動）

**Demo 影片**: 🎥 [完整功能展示播放清單](https://www.youtube.com/watch?v=XIMqSGli-tI&list=PLE0JJfyjW48fgTjk15cM5wljBlXIY8-ys)

**技術白皮書**: 📄 [EMKS 技術白皮書 PDF](WHITEPAPER.pdf)（完整架構決策、反方案分析、踩坑記錄）

---

## 解決什麼問題

企業知識散落在各處，找資料靠人問人。現有工具（SharePoint / Confluence）能存文件但不能問答；通用 AI（ChatGPT）能問答但沒有企業內部知識、也沒有權限控管。

EMKS 把兩件事合在一起：**用自然語言問公司內部知識，答案只包含你有權限看的文件**。

---

## 核心設計決策

### 統一入口 — 不讓使用者選 RAG 還是 Agent

原本用 Tab 分 RAG（語意搜尋）和 Agent（工具呼叫）。做完發現兩個問題：

1. 使用者不知道問題該歸哪一類，選錯要退回重問
2. Agent 不強制走知識庫時會幻覺 — 編出看似合理但錯誤的公司規定

改成單一入口：LangGraph Agent 自己決定要不要呼叫 RAG tool。使用者只管問，Agent 在背後做路由。

### 權限是 pre-filter 不是 post-filter

ChromaDB 查詢時直接把 RBAC 條件傳進 `where` clause，HNSW 搜尋只掃有權限的向量。不是搜完全部再砍結果 — 效能更好、也不會在 response 裡洩漏無權限文件的存在。

### SSE 串流：跨 async/sync 邊界的三層防線

LLM 答案 20 秒不能等，前端逐字顯示是 UX 強需求。但 SSE 串流橫跨 async router 跟 sync agent generator 兩個世界 — 連續踩三輪坑才形成完整的防線敘事：

1. **斷線偵測**：`is_disconnected()` polling + `try/finally` 關 OpenAI stream — 不偵測會花 token 沒人看
2. **Service 層自開 SessionLocal**：sync generator 在 worker thread / async router 在 event loop，SQLAlchemy session 跨 thread 不安全 — 借 router 注入的 session 會 race condition + connection 爆
3. **ContextVar 在 async handler 一開始 set**：FastAPI `iterate_in_threadpool` 進 thread 那刻才複製 context — set 必須在進 thread 之前，否則 tool 內讀不到 user 資訊

換 `astream()` 路徑就少兩層（async-native 沒跨 thread）— 但連續三輪修完 sync 路徑已穩定，列為已知 tech debt（見 [ARCHITECTURE.md](ARCHITECTURE.md)）。

> 三層防線不是預先設計，是踩過三輪坑才看到的 narrative — async/sync 邊界三類問題。

### 手寫先於框架

先自己寫完 RAG pipeline（chunk → embed → store → retrieve → generate），再引入 LlamaIndex 和 LangGraph。知道每個框架在替我做什麼。

---

## 技術棧

| 層 | 技術 |
|---|---|
| Backend | FastAPI + SQLAlchemy 2 + Pydantic 2 |
| Database | MySQL 8（業務資料）+ ChromaDB（向量） |
| AI | OpenAI GPT-4o-mini + text-embedding-3-small |
| Agent | LangGraph（狀態機 + tool calling） |
| RAG | LlamaIndex（多輪對話改寫）+ ChromaDB（cosine similarity） |
| Frontend | Vue 3 + Vite 7 + Pinia + Tailwind CSS + Element Plus |
| Auth | JWT（access + refresh）+ bcrypt + RBAC |
| Deploy | Render (Backend, Docker) + Vercel (Frontend) |
| Dev | Docker Compose（MySQL + ChromaDB + Backend + Frontend 一鍵起） |

---

## 功能一覽

### AI 問答（SSE 串流）
- 單一對話框，Agent 自動路由 4 個 tools：知識庫搜尋 / 最近文件 / 待審文件 / 熱門問題
- 多輪對話（LlamaIndex condense question）
- 逐 token 串流（SSE）+ 引用來源顯示（可點擊下載原檔，複用既有 RBAC 守門的 download endpoint）
- 拒答時不顯示無關來源（Sources UX 優化）

### 文件管理 + 向量化
- 資料夾樹狀結構 + 文件上傳（.txt / .pdf）
- 審核流程（pending → approved / rejected）
- 版本控制（上傳新版 / 回滾舊版）
- 審核通過自動觸發向量化（chunk → embed → ChromaDB）

### RBAC 權限
- 5 個預設角色（super_admin → guest），可自訂
- 細粒度權限碼（`resource:action`，如 `user:create`、`ai:chat`）
- 前端路由守衛 + 後端 dependency injection 雙層檢查
- AI 問答依角色動態載入可用 tools + 搜尋結果 pre-filter

### 帳號系統
- 登入 / 登出 / token auto-refresh
- 忘記密碼（SMTP 寄信 → 一次性 token → 重設）
- 帳號啟用（admin 建帳號 → 寄啟用信 → 設密碼）
- 登入失敗鎖定（5 次 → 15 分鐘）+ 稽核紀錄

### 工程品質
- **pytest 覆蓋**：auth + RBAC + agent eval（10+ tests，sqlite in-memory；agent eval 用 parametrize + spy 抓到並修了 system prompt 規則 #3）
- **限流**：`/ai/agent` 5/min + 30/day per user · `/auth/login` 10/min per IP（slowapi，對標 Glean 額度設計）
- **可觀測性**：loguru structured logging + ContextVar 注入 request_id（每筆 log 帶 trace ID 跨多服務追蹤）
- **冷啟動 UX**：`/health/ready` + 前端輪詢 overlay（防 Render free tier 30-120 秒冷啟動的黑屏）

---

## 架構概覽

```
Vue 3 SPA ──fetch/SSE──► FastAPI ──► LangGraph Agent
(Vercel)     axios/REST    (Render)       │
                              │           ├─ search_knowledge_base → ChromaDB (pre-filter)
                              │           ├─ get_recent_documents   → MySQL
                              │           ├─ get_pending_reviews    → MySQL
                              │           └─ get_popular_questions  → MySQL (admin only)
                              │
                              ├──► MySQL 8 (users, documents, chat, RBAC)
                              ├──► ChromaDB (vectors + RBAC metadata)
                              └──► OpenAI API (GPT-4o-mini + embedding)
```

**分層**：Router（HTTP + auth）→ Service（業務邏輯）→ Model（ORM）→ Database

完整架構圖、API 列表、DB schema、資料流細節見 [ARCHITECTURE.md](ARCHITECTURE.md)。

---

## 快速啟動

### Docker（推薦）

```bash
cd EMKS-Backend
docker-compose up -d
```

一鍵起 MySQL / ChromaDB / Backend / Frontend 四個容器。開 http://localhost 即用。

### 本機開發

```bash
# Backend (cwd = EMKS-Backend/)
uv sync
cp .env.example .env          # 填 OPENAI_API_KEY 等
# 需本機 MySQL 先跑著並建好 EMKS_DB database；schema 與 seed 皆由 FastAPI 啟動時 Python seed 自動處理
uv run uvicorn app.main:app --reload

# Frontend (cwd = EMKS-Frontend/)
npm install
npm run dev
```

Swagger：http://localhost:8000/docs

---

## 踩過的坑（精選）

| 問題 | 根因 | 解法 |
|------|------|------|
| SSE 跨 thread DB session 爆炸 | async router + sync generator，FastAPI `iterate_in_threadpool` 不保證同 thread | Service 層自開 SessionLocal，不依賴 router 注入的 session |
| RAG relevance threshold 0.5 太高 | `text-embedding-3-small` + 中文內容的 cosine 分數偏低 | 退到 0.35，用實測結果校正 |
| Agent 拒答但來源面板 dump 無關文件 | 多輪 tool call 累積 sources 無 dedup + threshold 太低 | dedup by document_id + 拒答偵測不送 sources |
| Render 冷啟動 container 重啟後空白 | seed 模組沒 commit + seed_docs 沒 COPY 進 image | 補 commit + Dockerfile 加 COPY |
| Vercel SPA deep link 404 | Vue Router history mode 需 server fallback | vercel.json rewrite all → index.html |

---

## 開發歷程

| 階段 | 內容 |
|:----:|------|
| 1 | 需求規格 + 架構設計 |
| 2 | 後端：文件管理 + 手寫 RAG Pipeline |
| 3 | 前端：知識庫 UI + 對話介面 |
| 4 | 業務邏輯重構（資料夾 / 審核 / 收藏 / 版本控制） |
| 5 | 手寫強化：權限 pre-filter + RAG 評估 + Chunk 策略優化 |
| 6 | Docker 容器化（全服務一鍵啟動） |
| 7 | LlamaIndex 引入：多輪對話 + SSE 串流 |
| 8 | LangGraph 引入：Agent 狀態機 + tool calling |
| 9 | 統一入口（RAG + Agent 合併）+ 雲端部署（Render + Vercel） |

---

## Repo 結構

```
EMKS/
├── EMKS-Backend/        ← 你在這裡
│   ├── app/             FastAPI application（含 seed_demo.py — schema + data 單一來源）
│   ├── seed_docs/       Demo 文件（8 份）
│   ├── ARCHITECTURE.md  完整技術細節
│   └── docker-compose.yml
└── EMKS-Frontend/       Vue 3 SPA（獨立 repo）
```

Backend / Frontend 是兩個獨立 git repo，不是 monorepo。

---

## License

個人作品集專案，未授權商業使用。
