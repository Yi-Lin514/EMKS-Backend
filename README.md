# EMKS Backend — 企業內部知識管理系統（後端）

基於 FastAPI 的企業知識管理系統後端，核心功能是**文件管理 + RAG 問答 + Agent 自動化**。整個專案從手寫 RAG 做起，逐步引入 LlamaIndex（多輪對話 + SSE）與 LangGraph（Agent），最後整合成單一入口 — 讓 LLM 自己決定該用知識庫檢索還是工具調用。

---

## 核心亮點

### 1. RAG → Agent 統一入口（非 Tab 切換）
前期用 Tab 分 RAG / Agent 模式做 debug 與對照，確定 Agent 能完整包住 RAG 後合併 — **LLM 自己判斷該檢索知識庫還是呼叫工具**，前端只有一個對話框。走完這一輪才理解「過渡設計」與「統一入口」的取捨。

### 2. 手寫先於框架
- 自己寫 RAG Pipeline（chunk → embed → store → retrieve → generate）後才引入 LlamaIndex
- 自己寫權限過濾、評估系統、Chunk 策略對比後才用 Agent
- 知道每個框架在替我做什麼，不是黑盒子

### 3. 權限過濾設計（pre-filter）
使用者問問題時，先根據部門/權限算出可見文件範圍，把 `where` 條件傳進 ChromaDB，HNSW 搜尋時就只看有權限的向量 — 不是搜完再砍。

### 4. SSE 串流的 Production 漏洞修復
連續三輪修復斷線處理：
- **第一輪**：加 `is_disconnected()` 檢查 + `try/finally` 關閉 LLM stream
- **第二輪**：發現 async router + sync generator 會讓 DB session 跨 thread → service 改自開 `SessionLocal()`
- **第三輪深度 review**：`iterate_in_threadpool` 底層不保證同一 worker thread — 剩餘技術債故意保留（成本 vs 風險評估）

### 5. RAG 評估系統
RAG 輸出非確定性、無法用單元測試。設計三層評估：Retrieval（找對文件）/ 權限過濾 / Generation（答案品質），搭配 15 組測試題定位問題。

---

## 技術棧

| 類別 | 技術 |
|------|------|
| 框架 | FastAPI 0.127 + SQLAlchemy 2.0 + Pydantic 2 |
| 資料庫 | MySQL 8.0 / ChromaDB（向量） |
| AI | OpenAI GPT-4o-mini + text-embedding-3-small |
| RAG / Agent | LlamaIndex（多輪對話）+ LangGraph（Agent 狀態機） |
| 認證 | JWT + RBAC（Role-Based Access Control） |
| 部署 | Docker + docker-compose（MySQL / ChromaDB / Backend / Frontend 一鍵啟動） |
| 套件管理 | uv |

---

## 架構

```
app/
├── main.py              FastAPI 進入點、router 註冊、CORS
├── config.py            Settings（pydantic_settings，讀 .env）
├── database.py          SQLAlchemy engine、SessionLocal、Base
├── models/              ORM models（user / department / role / permission / knowledge）
├── schemas/             Pydantic schemas（API 請求/回應）
├── routers/             API 路由（auth / user / ai / document / folder / review / favorite）
├── services/            業務邏輯（agent / rag / embedding / vector_store / ...）
└── dependencies/        FastAPI dependencies（rbac 權限檢查）
```

**資料流分層**：Router → Service → Model → Database

---

## 主要資料流

### 文件上傳 → 向量化
```
前端上傳 → Router 驗證 → Service 存檔 + 寫 MySQL metadata
        → Chunk 切塊（重疊 200 字元）→ OpenAI Embedding
        → ChromaDB 儲存向量 + metadata（含權限）
```

### AI 問答（統一入口）
```
使用者問題 → SSE 串流端點 → Condense Question（多輪對話改寫）
        → LangGraph Agent 決策
            ├─ 需要知識庫 → search_knowledge tool → ChromaDB（pre-filter 權限）
            └─ 特殊任務 → 其他 tool（條件性啟用，RBAC 控制）
        → LLM 生成 → 逐 token 推到前端
        → 儲存對話紀錄（含引用來源）
```

---

## 快速啟動

### 本機開發

```bash
# 1. 安裝依賴
uv sync

# 2. 設定 .env（複製 .env.example，填入你的 OPENAI_API_KEY 等）
cp .env.example .env

# 3. 建立資料庫
mysql -u root -p < database/EMKS_DB.sql

# 4. 建立管理員帳號（demo seed，可選）
mysql -u root -p EMKS_DB < seed.sql  # 參考 database/demo_seed.sql

# 5. 啟動
uv run uvicorn app.main:app --reload
```

### Docker（推薦）

```bash
docker-compose up -d
```

一鍵啟動 MySQL / ChromaDB / Backend / Frontend 四個容器。

---

## API 概覽

| Prefix | 功能 |
|--------|------|
| `/auth` | 登入 / 登出 / 忘記密碼 / Refresh Token |
| `/users` / `/departments` / `/roles` / `/permissions` | 會員權限管理 |
| `/knowledge/documents` | 文件 CRUD + 版本控制 + 下載 |
| `/knowledge/folders` | 資料夾樹狀結構 |
| `/knowledge/reviews` | 文件審核流程 |
| `/knowledge/favorites` | 我的收藏 |
| `/ai/agent` (SSE) | 統一入口 AI 對話 |
| `/ai/conversations` | 對話紀錄 CRUD |

啟動後開 `http://localhost:8000/docs` 看完整 Swagger。

---

## 開發歷程（簡版）

| 階段 | 內容 |
|:----:|------|
| Phase 1 | 需求規格 + 既有架構分析 |
| Phase 2 | 後端：文件管理 + RAG Pipeline + AI 問答 |
| Phase 3 | 前端：知識庫 UI + 對話介面 |
| Phase 4 | 業務邏輯重構（資料夾 + 審核 + 收藏 + 版本控制） |
| Phase 5 | 手寫強化：權限過濾 + RAG 評估 + Chunk 策略優化 |
| Phase 6 | Docker 容器化（全服務打包） |
| Phase 7 | LlamaIndex：多輪對話 + SSE 串流 |
| Phase 8 | LangGraph：Agent 自動化 |
| Phase 9 | 統一入口（RAG + Agent 合併） |

---

## License

個人作品集專案，未授權商業使用。
