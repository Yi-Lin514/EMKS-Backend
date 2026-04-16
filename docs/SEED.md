# Demo Seed 設計紀錄

> 文件用途：記錄 EMKS demo seed 的設計決策、權衡、與本地驗證做法。
> 寫給：未來接手的 Claude session、寫 README Architecture 章節時的參考素材。
> 上層脈絡：見 [CLAUDE-DEPLOYMENT-ADR.md](../../CLAUDE-DEPLOYMENT-ADR.md)（部署整體規劃）。

---

## 1. 為什麼需要 seed

EMKS 部署採「路線 A — 全 stateless demo」：Render 免費方案的容器每次重啟（通常因為 15 分鐘無流量被休眠喚醒）會清空 ephemeral disk。沒有 persistent 儲存就沒有累積資料的能力，所以需要 seed 在每次冷啟動時**自動把 demo 環境重建出來**。

這個取捨的好處與代價見 [CLAUDE-DEPLOYMENT-ADR.md 「核心策略」](../../CLAUDE-DEPLOYMENT-ADR.md)。本文聚焦在 seed 本身怎麼實作。

---

## 2. Seed 內容總覽

執行 [app/seed/seed_demo.py](../app/seed/seed_demo.py) 的 `run_seed_sync()` 後，DB 會有：

| 類型 | 數量 | 說明 |
|---|---|---|
| 部門 (Department) | 4 | 管理部 / 資訊部 / 製造部 / 品管部 |
| 權限 (Permission) | 14 | user / department / role / system / ai 五個 resource，13 個 CRUD + `ai:admin_tools` |
| 角色 (Role) | 4 | admin / manager / employee / viewer |
| 帳號 (User) | 4 | 各對應一個角色，密碼統一 `demo123` |
| 文件 (KnowledgeDocument) | 8 | 6 public + 2 department，全部 status=approved、vectorization_status=completed |
| ChromaDB chunks | ~33 | 8 份文件 × 平均 4 chunks（500 字／chunk） |

### 2.1 Demo 帳號 × 部門 × 角色

| Email | 部門 | 角色 | 權限數 |
|---|---|---|---|
| `admin@demo.com` | 管理部 (id=1) | admin | 14（含 `ai:admin_tools`） |
| `manager@demo.com` | 資訊部 (id=2) | manager | 4（user/department/role/system 的 view） |
| `employee@demo.com` | 製造部 (id=3) | employee | 1（department:view） |
| `viewer@demo.com` | 品管部 (id=4) | viewer | 0 |

### 2.2 文件權限分配（demo RBAC pre-filter 的關鍵設計）

| 文件 | permission_level | department_id | 誰查得到（RAG） |
|---|---|---|---|
| 01_員工手冊 | public | — | 全部 |
| 02_資安規範 | public | — | 全部 |
| 03_報銷流程 | public | — | 全部 |
| 04_出差規範 | public | — | 全部 |
| 05_新人Onboarding | public | — | 全部 |
| 06_客訴處理流程 | public | — | 全部 |
| 07_ISO品管手冊 | department | 4 (品管部) | admin + viewer |
| 08_生產SOP | department | 3 (製造部) | admin + employee |

**Demo 效果**：manager（資訊部）跟 employee（製造部）問 ChatGPT「ISO 品管手冊重點是什麼？」會拿到不同答案 — manager 查不到（資訊部沒此文件），employee 也查不到（製造部沒此文件），只有 viewer（品管部）跟 admin 拿得到。同樣地問「生產 SOP 第幾步是錫膏印刷」只有 admin 跟 employee 拿得到。這是面試現場最直觀的 RBAC 展示。

---

## 3. 設計決策

### 3.1 Lifespan 背景跑（async task）

**做法**：[app/main.py](../app/main.py) 用 `asynccontextmanager` 註冊 lifespan，startup 階段用 `asyncio.create_task(asyncio.to_thread(run_seed_sync))` fire-and-forget。

**Why**：seed 包含 8 次 OpenAI embedding API call，網路順的話 5-10 秒，慢的話 20+ 秒。如果同步擋在 startup，Render 會等不到 server 開始監聽 PORT，判定啟動失敗持續重啟。背景跑讓 server 立刻可接受請求，seed 在後面悄悄完成。

**取捨**：
- 前幾秒 RAG 還沒準備好 → 接受。前端可加「系統初始化中」提示。
- Seed 失敗不會 block server 啟動 → 接受。失敗的 traceback 會印在 log，部署後看 Render log 就知道。

**為什麼不用 sync startup event**（FastAPI 舊 API）：FastAPI 0.93+ 推薦用 lifespan context manager，舊 `@app.on_event("startup")` 已 deprecated。

**為什麼不放 Dockerfile RUN**：seed 需要呼叫 OpenAI API，build 時就得有 `OPENAI_API_KEY` → image 變敏感、變重。runtime 跑才合理。

### 3.2 跳過審核流程，直接建 approved + completed

**做法**：[app/seed/seed_demo.py](../app/seed/seed_demo.py) 的 `_seed_one_document()` 直接 `INSERT KnowledgeDocVersion` 設 `status="approved"`、`reviewed_by=admin.id`、`reviewed_at=now()`、`vectorization_status="processing"`，再手動跑 embedding + `add_chunks`，最後改 `vectorization_status="completed"`。

**Why**：正常流程是 upload → pending → admin approve → vectorize。Seed 是程式控制的可信來源，沒有「污染知識庫」風險，跑審核儀式是純儀式。

**取捨**：
- Seed 不經過 [services/document.py::create_document](../app/services/document.py)，等於繞開了該函式的 transaction logic → 接受。Seed 自己管 commit，邏輯獨立。
- 如果未來 `KnowledgeDocVersion` 加新欄位，seed 可能漏設 → 用「`status="approved"` 是 enum value 不是 enum member」這種風格保持寬鬆，欄位多了預設值會接管。

### 3.3 冪等：靠 `admin@demo.com` 是否存在

**做法**：`_already_seeded(db)` 查 `User.email == "admin@demo.com"`，找到就整個 `run_seed_sync()` 直接 return。

**Why**：Render container 重啟後 ephemeral disk 雖然會清空（含 SQLite 檔），但本地測試環境可能保留 — 一個簡單的 guard 讓本地 dev 不會每次啟動都重 seed。

**取捨**：
- 不檢查「seed 是否完整」（例如 8 份文件是否都 vectorized 完）→ 接受。失敗的部分會在 log 看到，要重 seed 就刪 SQLite 檔。
- 改 seed 內容後，本地要刪 SQLite 才生效 → 接受。Seed 不該頻繁變動，每次冷啟動都重做的是 Render 環境，那邊本來就 fresh。

### 3.4 防禦性 `delete_document_chunks` 在 add_chunks 前

**做法**：每份文件 embedding 前先 `delete_document_chunks(doc.id)` 清掉同 ID 的舊 chunks。

**Why**：[services/vector_store.py::add_chunks](../app/services/vector_store.py) 用 `f"doc{document_id}_chunk{i}"` 當 chunk ID。如果 ChromaDB 已有 `doc1_chunk0`（例如本地切過 MySQL/SQLite 後 doc id 從 1 重來），`add_chunks` 會炸 `IDAlreadyExists`。先刪後加是廉價保險。

**取捨**：
- Render 環境 ChromaDB 永遠是空的，這行是 no-op → 接受。本地 dev 才有意義，但成本是一次 collection.get + 可能的 collection.delete，可忽略。
- 不用更激進的「整個 collection drop 重建」→ 接受。那會破壞本地手動上傳的測試文件。

### 3.5 admin 角色必須有 `ai:admin_tools`

**做法**：`PERMISSIONS` 清單加上 `ai:admin_tools`，`ROLE_PERMISSIONS["admin"]` 自動繼承（用 list comprehension 拿全部）。

**Why（這 session 才發現的）**：權限系統有兩套 admin 判斷邏輯：

1. [dependencies/rbac.py::require_admin](../app/dependencies/rbac.py) — 看是否有任一 `user:` 開頭權限
2. [routers/ai.py::_check_admin](../app/routers/ai.py) — 看是否有 `ai:admin_tools` 權限

`require_admin` 用在文件審核、folder 管理；`_check_admin` 用在 agent 的 RAG 過濾（`is_admin=True` → `build_permission_filter` 回傳 `None` → 不過濾）。

只給 admin 角色 `user:*` 權限，會被 `require_admin` 認可，但 `_check_admin` 回傳 False → admin 在 RAG 階段被當一般使用者，只能看 public + 自己部門（管理部=1）的文件，**永遠拿不到 ISO品管手冊（dept=4）跟生產SOP（dept=3）**，違反「admin 看得到全部」的 demo 設計。

**取捨**：
- 沒去重構 `_check_admin` 統一兩套 admin 判斷 → 接受。這是 EMKS 既有設計，重構超出 seed 範圍。Seed 配合既有規則就好。
- Seed 寫 `ai:admin_tools` 時加註解指向 `_check_admin` → 維護性。

### 3.6 SSE 路徑跟 seed 無關，但要記得

Seed 跟 SSE 沒直接耦合，但部署後第一個請求很可能是 `/ai/agent`（demo 場景）。Render 冷啟動 + seed 還沒跑完，第一個 RAG 查詢可能拿到空結果或部分結果。前端 UX（系統初始化中）的優先度因此很高，不是「nice-to-have」。

---

## 4. 檔案佈局

```
EMKS-Backend/
├── app/
│   ├── main.py                  ← lifespan 註冊在這（_run_seed_background）
│   └── seed/
│       ├── __init__.py          ← export run_seed_sync
│       └── seed_demo.py         ← 主邏輯（DEPARTMENTS / PERMISSIONS / ROLES / USERS / DOCUMENTS）
├── seed_docs/
│   ├── PROMPTS.md               ← ChatGPT 用的提示詞（備案，目前由 Claude Code 直接生）
│   ├── 01_員工手冊.txt
│   ├── 02_資安規範.txt
│   ├── ...
│   └── 08_生產SOP.txt
└── uploads/
    └── knowledge/
        └── seed/                ← seed 啟動時把 seed_docs/ 複製到這（runtime 產生）
```

`uploads/` 在 `.gitignore` 內，不會 commit；`seed_docs/` 會 commit（Render 部署時 Docker image 要包含這些檔案）。

---

## 5. 本地驗證 recipe

### 5.1 完整重 seed（驗證 SQLite 模式從零跑）

```bash
cd EMKS-Backend
rm -f demo.db
rm -rf uploads/knowledge/seed
DATABASE_URL=sqlite:///./demo.db uv run uvicorn app.main:app --port 8000
# 等 5-15 秒給 lifespan 背景 seed 跑完
```

### 5.2 確認 seed 結果

```bash
uv run python -c "
import sqlite3
conn = sqlite3.connect('demo.db')
c = conn.cursor()
print('users:', [r[0] for r in c.execute('SELECT email FROM users')])
print('docs:', c.execute('SELECT COUNT(*) FROM knowledge_documents').fetchone()[0])
print('versions completed:', c.execute(\"SELECT COUNT(*) FROM knowledge_doc_versions WHERE vectorization_status='completed'\").fetchone()[0])
"
# 預期：4 users / 8 docs / 8 versions completed
```

### 5.3 驗證 RBAC pre-filter（最關鍵）

```bash
uv run python -c "
import sys; sys.stdout.reconfigure(encoding='utf-8')
from app.services.embedding import get_embedding
from app.services.vector_store import search_chunks
from app.services.rag import build_permission_filter

emb = get_embedding('生產SOP 的錫膏印刷步驟在做什麼？')
for name, is_admin, dept in [('admin', True, 1), ('manager', False, 2), ('employee', False, 3), ('viewer', False, 4)]:
    where = build_permission_filter(is_admin=is_admin, department_id=dept)
    hits = [m['document_title'] for m in search_chunks(emb, n_results=3, where=where)['metadatas'][0]]
    print(f'{name}: {hits}')
"
# 預期：admin 跟 employee 命中 08_生產SOP，manager 跟 viewer 命中 fallback public
```

### 5.4 登入測試（API 層）

```bash
# Server 還在跑時
curl -s -X POST http://127.0.0.1:8000/auth/login \
  -H "Content-Type: application/json" \
  -d '{"email":"admin@demo.com","password":"demo123"}' \
  | python -c "import sys,json; r=json.loads(sys.stdin.read()); print('perms count:', len(r['user']['permissions']))"
# 預期：14
```

---

## 6. 冷啟動成本估算

8 份文件 × 平均 4 chunks × ~500 字／chunk ≈ 16,000 字 ≈ ~24,000 tokens（中文 1.5 token／字粗估）。

`text-embedding-3-small` 定價 $0.02 / 1M tokens → 一次冷啟動 embedding cost ≈ **$0.0005**。

每天即使被喚醒 50 次（不可能但極限值），每月也才 $0.75。對 demo 場景完全可忽略。

---

## 7. 踩過的坑（這 session 真實學習）

### 7.1 uvicorn 把 print 吃掉

Seed 在 `asyncio.to_thread(run_seed_sync)` 跑，stdout 經過 worker thread + uvicorn 的 buffering，`print("[seed] start...")` 不會即時出現。本地驗證時看不到 seed log 不代表 seed 沒跑，要直接查 DB 才確定。

**生產解法**：要不要改用 `logging` 模組（uvicorn 有專門的 log handler）？目前還沒做 — 先觀察 Render 環境的行為再決定。Render 的 log streaming 可能跟本地 buffering 行為不同。

### 7.2 ChromaDB chunk ID 衝突

本地測試從 MySQL 切到 SQLite 時，doc.id 從 1 重來，但 ChromaDB 的 `doc1_chunk0` 還在 → `add_chunks` 炸 `IDAlreadyExists`。已加防禦性 `delete_document_chunks` 處理（見 3.4）。

**踩坑信號**：seed 看似 OK 但 RAG 查不到新內容 → 可能是 chunks 沒寫進去（雖然 DB 顯示 vectorization_status=failed，但容易被忽略）。

### 7.3 兩套 admin 判斷邏輯不一致

`require_admin`（看 user:* 權限）跟 `_check_admin`（看 ai:admin_tools）不對齊。Seed 一開始只給 `user:` 系列，admin 在 RAG 層被當一般使用者，看不到 dept 文件。詳見 3.5。

**踩坑信號**：admin 登入 OK、`/users` 等 admin 路由能用，但問 AI 拿不到該拿到的文件。要對 [routers/ai.py](../app/routers/ai.py) 第 28 行特別敏感。

### 7.4 seed_docs 是 PDF 還是 TXT？

評估過要不要加幾份 PDF 增加擬真性。決定**全 TXT**：

- PyMuPDF 抽 PDF 文字常引入頁眉頁尾碎片、奇怪換行 → chunking 後 embedding 品質差
- Demo 重點是「問題 → 對的答案」，不是「展示能處理 PDF」
- TXT 容易在 git 看 diff、容易手動修

如果未來想展示 PDF 處理能力，挑 1-2 份 TXT 另存 PDF 即可（seed 會自動讀 `.pdf`）。

---

## 8. 跟其他文件的關係

- 部署整體規劃 → [CLAUDE-DEPLOYMENT-ADR.md](../../CLAUDE-DEPLOYMENT-ADR.md)（meta-repo 根）
- 專案開發指引 → [CLAUDE.md](../../CLAUDE.md)（meta-repo 根）
- 後端 API 跟架構 → [README.md](../README.md)（待補 Architecture 章節時可從本文件擷取）
- 文件生成提示詞（備案） → [seed_docs/PROMPTS.md](../seed_docs/PROMPTS.md)
