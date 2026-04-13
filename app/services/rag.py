# RAG 工具函數 — 提供 build_context / build_permission_filter / condense_question
# 對話 CRUD 已搬到 conversation.py，Prompt 已搬到 prompt.py

from llama_index.llms.openai import OpenAI

from app.config import settings
from app.services.prompt import CONDENSE_PROMPT

llm = OpenAI(
    model=settings.LLM_MODEL,
    api_key=settings.OPENAI_API_KEY,
    temperature=settings.LLM_TEMPERATURE,
    max_tokens=settings.LLM_MAX_TOKENS,
)

# RAG 專用 system prompt — 保留供未來獨立 RAG 使用
SYSTEM_PROMPT = (
    "你是企業內部知識助手。請根據以下提供的文件內容回答使用者的問題。\n"
    "規則：\n"
    "1. 根據提供的文件內容回答，不要編造資訊\n"
    "2. 即使文件內容是表格、程式碼或清單格式，也要從中整理出回答\n"
    "3. 回答時引用來源文件名稱\n"
    "4. 使用繁體中文回答"
)


def build_context(search_results: dict) -> tuple[str, list[dict]]:
    '''從向量資料庫的搜尋結果中構建回答上下文和來源資訊'''
    documents = search_results.get("documents", [[]])[0]
    metadatas = search_results.get("metadatas", [[]])[0]
    distances = search_results.get("distances", [[]])[0]

    context_parts = []
    sources = []

    for i, (doc, meta, distance) in enumerate(zip(documents, metadatas, distances)):
        relevance_score = round(1 - distance, 4)

        if relevance_score < settings.RAG_RELEVANCE_THRESHOLD:
            continue

        context_parts.append(
            f"[文件 {i+1}] 來源：{meta['document_title']}\n{doc}"
        )
        sources.append({
            "document_id": meta["document_id"],
            "document_title": meta["document_title"],
            "chunk_content": doc,
            "relevance_score": relevance_score,
        })

    context = "\n\n---\n\n".join(context_parts)
    return context, sources


def build_permission_filter(
    is_admin: bool,
    department_id: int | None,
) -> dict | None:
    '''根據使用者的權限構建向量資料庫的搜尋過濾條件'''
    if is_admin:
        return None

    if department_id:
        return {
            "$or": [
                {"permission_level": "public"},
                {"department_id": department_id},
            ]
        }

    return {"permission_level": "public"}


def condense_question(chat_history: list[dict], question: str) -> str:
    '''將使用者的追問改寫成一個獨立的問題，讓向量資料庫搜尋能更準確'''
    history_text = "\n".join(
        f"{msg['role']}: {msg['content']}" for msg in chat_history
    )

    prompt = CONDENSE_PROMPT.format(
        chat_history=history_text,
        question=question,
    )

    response = llm.complete(prompt)
    return response.text.strip()
