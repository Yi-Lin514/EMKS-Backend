# 2026-04-15 env 驅動部署準備

> 類型：📦 建構型（寫完歸檔，不主動擴充）
> 上下文：雲端部署 B 階段（本地實作）完成
> 配套檔案：[../../CLAUDE-DEPLOYMENT-ADR.md](../../CLAUDE-DEPLOYMENT-ADR.md)

## 為什麼寫這份筆記

ADR 記「決策是什麼」，這份記「當初那樣選的推理過程」。半年後我忘了為什麼 CORS 要 fail-loud、為什麼 Dockerfile CMD 改 shell form 時，翻 git log 只會看到 diff 沒看到理由。

## 4 個關鍵 trade-off

### 1. `DATABASE_URL` 做普通欄位 + validator，不做 `_OVERRIDE` 命名

**選**：`DATABASE_URL: str = ""` + `@model_validator(mode="after")` 在空值時組 MySQL URL
**沒選**：`DATABASE_URL_OVERRIDE: str = ""` + 保留舊 `@property`

**為什麼**：讀 code 的人一看就懂「`DATABASE_URL` 就是最終連線字串」。替代方案多一個 `_OVERRIDE` 會讓未來自己疑惑「為什麼不直接叫 `DATABASE_URL`」。代價是 validator 多寫 5 行，可接受。

**心法**：**命名直觀性 > 程式碼行數**。

### 2. CORS 選 fail-loud，不補 safe default

**選**：`allow_origins=settings.CORS_ORIGINS.split(",")` — 空字串時 `[""]` 會讓所有 origin 失敗
**沒選**：`[o for o in settings.CORS_ORIGINS.split(",") if o]` — 空字串退化成空 list，CORS 全擋但靜默

**為什麼**：部署時漏設 `CORS_ORIGINS` 是常見錯，靜默全擋會 debug 半天才發現「原來是我忘了設 env」。fail loud 直接炸在眼前，早發現早修。

**心法**：**設定類 env 寧可炸給你看，不要靜默 fallback**。

### 3. Dockerfile 改 shell form CMD，放棄 exec form 的 SIGTERM 直達

**選**：`CMD uv run uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}`
**沒選**：寫 entrypoint script 用 `exec uv run ...` 讓 SIGTERM 繞過 sh 直達 uvicorn

**為什麼**：Render 注入動態 `$PORT`，exec form 的 JSON array 不展開 env var，所以一定要走 shell form。代價是 SIGTERM 經過 sh 不優雅傳給 uvicorn，進行中請求被強殺。但在 demo 場景：
- 觸發條件：Render 重新部署 × 剛好有人在打請求（機率極低）
- 觸發後損失：請求被截斷，使用者重試即可（損失極小）
- 兩者都趨近於零 → 不值得為它建 entrypoint script

**心法**：**技術債值不值得還 = 實際觸發機率 × 觸發後損失。兩者都趨近於零就不還**。

### 4. 跳過 SQLite 模式本地驗證，折進之後的 seed 步驟

**選**：現在只驗 MySQL 模式能起來（確認 config / database / main 改動沒改壞）
**沒選**：現在也驗 SQLite 模式

**為什麼**：現在跑 SQLite 會同時測到 schema 自動建、demo seed、chroma 路徑切換 — 失敗的話 blast radius 太大，錯在哪分不清。seed step 本來就要解決「從零建 DB」，SQLite 相容性順便在那裡一起驗。

**心法**：**一次驗一個變因。組合測試放到所有組件都 OK 後再做**。

## 兩個打臉的發現（ADR 假設 vs 實際 code）

1. **ChromaDB client 模式**：ADR 視為最大部署風險點，實際 [`vector_store.py`](../app/services/vector_store.py) 早就內建 `CHROMA_HOST` env 雙模式切換（有設 → `HttpClient`，沒設 → `PersistentClient`），**零改動**。
2. **Frontend axios baseURL**：ADR + 舊 CLAUDE.md 都說「寫死 `http://localhost:8000`」，實際早就是 `import.meta.env.VITE_API_URL || ...` env 驅動，只是變數名跟 ADR 寫的 `VITE_API_BASE_URL` 不同。

**教訓**：ADR 是規劃不是事實。寫 ADR 時假設「某處要改」之前，**先 Read 實際 code 驗證假設**，否則會為假問題設計解法、浪費一次 session 才發現問題自己解決了。

## env 驅動類改動的驗證盲點

log 看不出「env 真的有讀到」vs「code 裡的 `|| fallback` 起作用」— 行為完全相同。

**真驗證手法**：暫時把 env 值改成一定會錯的（如 port 改 9999），重啟、測請求，**請求打不通 = env 有讀到 = 驗證成功**。之後改回正確值。

今天跳過了這步，賭「雲端部署時不設 env 就炸，自然會發現」當兜底。**下次要判斷這個賭注合不合理**，看改動是否有部署這個最終關卡兜底；如果沒有（例如純本地功能），就一定要惡搞驗證。
