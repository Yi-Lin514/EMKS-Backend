import json
from collections.abc import Generator
from contextvars import ContextVar
from datetime import datetime, timedelta
from typing import Annotated, TypedDict

from langchain_core.messages import AIMessage, AIMessageChunk, HumanMessage, SystemMessage
from langchain_core.tools import tool
from langchain_openai import ChatOpenAI
from langgraph.graph import END, START, StateGraph
from langgraph.graph.message import add_messages
from langgraph.prebuilt import ToolNode
from sqlalchemy import func as sql_func
from sqlalchemy.orm import joinedload

from app.config import settings
from app.database import SessionLocal
from app.models.knowledge import (
    ChatConversation,
    ChatMessage,
    KnowledgeDocument,
    KnowledgeDocVersion,
)
from app.services.conversation import (
    get_or_create_conversation,
    save_message,
)
from app.services.embedding import get_embedding
from app.services.rag import build_permission_filter, condense_question
from app.services.vector_store import search_chunks


class AgentState(TypedDict):
    messages: Annotated[list, add_messages]


AGENT_SYSTEM_PROMPT = (
    "你是企業知識庫智慧助理。你可以呼叫工具來取得所需資訊，取得足夠資訊後再彙整回答。\n"
    "規則：\n"
    "1. 根據工具回傳的真實資料回答，**絕對不要根據訓練語料或猜測編造任何統計、列表、數據**\n"
    "2. 如果使用者的請求需要某項資訊，但你目前沒有對應的工具可以取得（工具列表中沒有），\n"
    "   必須直接回答「抱歉，我目前沒有權限或工具可以查詢這項資訊」，不要硬掰、不要列舉示例、不要用其他工具勉強湊答案\n"
    "3. **統計性、排名、熱門度、頻率、趨勢類問題的處理**（例如「大家最常問什麼」、「最熱門的文件」、「最近趨勢」等需要彙總分析的問題）：\n"
    "   - **第一步**：先檢查工具列表中是否有對應的統計工具（如 `get_popular_questions` 等），有就直接呼叫，**不要因為規則嚴格就跳過**\n"
    "   - **只有當工具列表中沒有任何統計工具時**，才回答「抱歉，沒有權限查詢這類統計」\n"
    "   - 絕對不可以用 `search_knowledge_base` 或 `get_recent_documents` 的結果整理成「常見主題」「常見問題」來假裝是統計 — 屬於資訊誤導\n"
    "4. 如果使用者的請求需要多個工具的資訊，全部取得後再統一回答\n"
    "5. 使用繁體中文回答\n"
    "6. 回答格式清晰，善用標題、列表、粗體"
)


# 用 ContextVar 而非 threading.local：LangGraph ToolNode 用 ThreadPoolExecutor 跑工具，
# langchain 會把 main thread 的 contextvars copy 給 worker thread；threading.local 做不到。
_user_context_var: ContextVar[dict] = ContextVar("agent_user_context", default={})


def _get_db():
    return SessionLocal()


@tool
def get_recent_documents(days: int = 7) -> str:
    """查詢最近 N 天內新增或更新的知識庫文件。用於瞭解近期文件活動。"""
    cutoff = datetime.now() - timedelta(days=days)
    db = _get_db()
    try:
        docs = (
            db.query(KnowledgeDocument)
            .options(
                joinedload(KnowledgeDocument.current_version),
                joinedload(KnowledgeDocument.uploader),
            )
            .filter(
                KnowledgeDocument.is_deleted == False,
                KnowledgeDocument.updated_at >= cutoff,
            )
            .order_by(KnowledgeDocument.updated_at.desc())
            .all()
        )

        if not docs:
            return f"最近 {days} 天沒有新增或更新的文件。"

        lines = []
        for doc in docs:
            version_info = f"v{doc.current_version.version}" if doc.current_version else "無版本"
            uploader_name = doc.uploader.name if doc.uploader else "未知"
            lines.append(
                f"- {doc.filename}（{version_info}，上傳者：{uploader_name}，"
                f"更新時間：{doc.updated_at.strftime('%Y-%m-%d')}）"
            )

        return f"最近 {days} 天的文件異動共 {len(docs)} 筆：\n" + "\n".join(lines)
    finally:
        db.close()


@tool
def get_pending_reviews() -> str:
    """查詢待審核的文件版本列表（一般員工只能看到自己上傳的；管理員看到全部）。
    用於瞭解審核狀況。請根據實際回傳內容用對應的口吻回答 — 如果只看到自己上傳的，
    不要聲稱是「全公司」或「所有」待審文件。"""
    ctx = _user_context_var.get()
    is_admin = ctx.get("is_admin", False)
    current_user_id = ctx.get("user_id")

    db = _get_db()
    try:
        query = (
            db.query(KnowledgeDocVersion)
            .join(KnowledgeDocument, KnowledgeDocVersion.document_id == KnowledgeDocument.id)
            .options(
                joinedload(KnowledgeDocVersion.document),
                joinedload(KnowledgeDocVersion.uploader),
            )
            .filter(
                KnowledgeDocVersion.status == "pending",
                KnowledgeDocument.is_deleted == False,
            )
        )

        # 資料級權限：非 admin 只看自己上傳的待審版本
        if not is_admin:
            query = query.filter(KnowledgeDocVersion.uploaded_by == current_user_id)

        versions = query.order_by(KnowledgeDocVersion.created_at.asc()).all()

        if not versions:
            return "目前沒有待審核的文件。"

        lines = []
        for v in versions:
            uploader_name = v.uploader.name if v.uploader else "未知"
            waiting_days = (datetime.now() - v.created_at).days
            lines.append(
                f"- {v.document.filename} v{v.version}（上傳者：{uploader_name}，"
                f"等待 {waiting_days} 天，上傳日期：{v.created_at.strftime('%Y-%m-%d')}）"
            )

        return f"待審核文件共 {len(versions)} 份：\n" + "\n".join(lines)
    finally:
        db.close()


@tool
def search_knowledge_base(query: str) -> str:
    """搜尋知識庫內容。根據語意搜尋相關文件片段，用於回答知識性問題。"""
    ctx = _user_context_var.get()

    # 多輪對話時，用 condense_question 將追問改寫為獨立問題，提高搜尋精準度
    chat_history = ctx.get("chat_history", [])
    search_query = query
    if chat_history:
        search_query = condense_question(chat_history, query)

    query_embedding = get_embedding(search_query)

    # 使用共用的權限過濾函數，避免重複邏輯
    where = build_permission_filter(
        is_admin=ctx.get("is_admin", False),
        department_id=ctx.get("department_id"),
    )

    results = search_chunks(
        query_embedding=query_embedding,
        n_results=settings.RAG_SEARCH_RESULTS,
        where=where,
    )

    documents = results.get("documents", [[]])[0]
    metadatas = results.get("metadatas", [[]])[0]
    distances = results.get("distances", [[]])[0]

    if not documents:
        return "知識庫中找不到相關資料。"

    lines = []
    sources = []
    for doc, meta, distance in zip(documents, metadatas, distances):
        relevance = round(1 - distance, 4)
        if relevance < settings.RAG_RELEVANCE_THRESHOLD:
            continue
        lines.append(
            f"[來源：{meta['document_title']}，相關度：{relevance:.0%}]\n{doc[:300]}"
        )
        sources.append({
            "document_id": meta["document_id"],
            "document_title": meta["document_title"],
            "chunk_content": doc,
            "relevance_score": relevance,
        })

    if not lines:
        return "知識庫中找不到足夠相關的資料。"

    # enrich sources with current_version_id so frontend can build download URL
    # (Chroma metadata 刻意不存 version_id — 新版核准時會 re-index，
    # 只有 current version 的 chunks 會留下；真要下載仍以 DB 當下狀態為準)
    doc_ids = [s["document_id"] for s in sources]
    db = _get_db()
    try:
        version_map = dict(
            db.query(KnowledgeDocument.id, KnowledgeDocument.current_version_id)
            .filter(KnowledgeDocument.id.in_(doc_ids))
            .all()
        )
        for s in sources:
            s["current_version_id"] = version_map.get(s["document_id"])
    finally:
        db.close()

    # 把結構化 sources 寫進 context dict，供 run_agent_stream 讀出送前端
    # dedup by document_id：多輪工具呼叫會重複搜到同份文件，只保留最高相關度的 chunk
    existing = ctx.get("sources", [])
    seen: dict[int, int] = {}  # document_id → index in existing
    for i, s in enumerate(existing):
        seen[s["document_id"]] = i
    for s in sources:
        did = s["document_id"]
        if did in seen:
            if s["relevance_score"] > existing[seen[did]]["relevance_score"]:
                existing[seen[did]] = s
        else:
            seen[did] = len(existing)
            existing.append(s)

    return f"搜尋到 {len(lines)} 筆相關內容：\n\n" + "\n\n---\n\n".join(lines)


@tool
def get_popular_questions(days: int = 7, limit: int = 5) -> str:
    """統計最近 N 天內使用者最常問的問題。用於瞭解知識需求趨勢。"""
    # 第二道牆（A）：function 內部再驗一次 is_admin，
    # 防止 bind tools 那層因 bug / cache 污染漏放
    ctx = _user_context_var.get()
    if not ctx.get("is_admin", False):
        return "權限不足：此功能僅限管理員使用。"

    cutoff = datetime.now() - timedelta(days=days)
    db = _get_db()
    try:
        questions = (
            db.query(
                ChatMessage.content,
                sql_func.count(ChatMessage.id).label("count"),
            )
            .join(ChatConversation, ChatMessage.conversation_id == ChatConversation.id)
            .filter(
                ChatMessage.role == "user",
                ChatMessage.created_at >= cutoff,
            )
            .group_by(ChatMessage.content)
            .order_by(sql_func.count(ChatMessage.id).desc())
            .limit(limit)
            .all()
        )

        if not questions:
            return f"最近 {days} 天沒有使用者提問紀錄。"

        lines = [f"- {q.content}（{q.count} 次）" for q in questions]
        return f"近 {days} 天熱門問題 Top {limit}：\n" + "\n".join(lines)
    finally:
        db.close()


# 員工版工具：所有人都能用（資料級權限在 function 內部過濾）
EMPLOYEE_TOOLS = [get_recent_documents, get_pending_reviews, search_knowledge_base]
# 管理員專屬工具：員工的 LLM 根本看不到（功能級權限）
ADMIN_ONLY_TOOLS = [get_popular_questions]

llm = ChatOpenAI(
    model=settings.LLM_MODEL,
    api_key=settings.OPENAI_API_KEY,
    temperature=settings.LLM_TEMPERATURE,
)


def should_continue(state: AgentState):
    last_message = state["messages"][-1]
    if last_message.tool_calls:
        return "tools"
    return END


def _build_agent_app(is_admin: bool):
    """依權限動態組工具列表 + bind + 編 graph（第一道牆，B）。"""
    tools = list(EMPLOYEE_TOOLS)
    if is_admin:
        tools = tools + ADMIN_ONLY_TOOLS

    llm_with_tools = llm.bind_tools(tools)

    def agent_node(state: AgentState):
        system = SystemMessage(content=AGENT_SYSTEM_PROMPT)
        response = llm_with_tools.invoke([system] + state["messages"])
        return {"messages": [response]}

    tool_node = ToolNode(tools)

    graph = StateGraph(AgentState)
    graph.add_node("agent", agent_node)
    graph.add_node("tools", tool_node)
    graph.add_edge(START, "agent")
    graph.add_conditional_edges("agent", should_continue, {"tools": "tools", END: END})
    graph.add_edge("tools", "agent")
    return graph.compile()


def run_agent(
    question: str,
    is_admin: bool = False,
    department_id: int | None = None,
    user_id: int | None = None,
) -> str:
    """非串流版 Agent（保留供測試或內部呼叫使用）。"""
    token = _user_context_var.set({
        "is_admin": is_admin,
        "department_id": department_id,
        "user_id": user_id,
    })
    try:
        agent_app = _build_agent_app(is_admin=is_admin)
        result = agent_app.invoke({
            "messages": [HumanMessage(content=question)],
        })
        return result["messages"][-1].content
    finally:
        _user_context_var.reset(token)


def set_user_context(
    is_admin: bool,
    department_id: int | None,
    user_id: int | None,
    chat_history: list[dict] | None = None,
) -> None:
    """在 router async handler 裡呼叫，讓 iterate_in_threadpool 的每次 context copy 都帶上值。

    為什麼不能在 generator 裡 set？因為 iterate_in_threadpool 每次 next() 都複製一份新 context，
    generator 裡 set() 的值不會帶到下一次 next()，工具呼叫可能在不同的 next() 裡讀不到。
    在 router async handler 裡 set → iterate_in_threadpool 複製的是已經 set 好的 context → 每次都有值。
    """
    _user_context_var.set({
        "is_admin": is_admin,
        "department_id": department_id,
        "user_id": user_id,
        "chat_history": chat_history or [],
        "sources": [],  # mutable list — 工具 append 後所有 context 副本都看得到
    })


def run_agent_stream(
    question: str,
    user_id: int,
    conversation_id: int | None = None,
    is_admin: bool = False,
    chat_history: list[dict] | None = None,
) -> Generator[str, None, None]:
    """串流版 Agent — 統一入口，支援 SSE 串流 + 對話紀錄 + condense。

    ContextVar 由 router 在 async handler 裡 set（見 set_user_context），
    本函式不管 ContextVar 的生命週期。

    與 RAG chat_stream 相同原因，本函式自己開 DB session：
    SSE generator 在 threadpool worker thread 跑，SQLAlchemy session 不是 thread-safe。
    """
    db = SessionLocal()
    conv_id = None
    full_answer = ""
    assistant_saved = False
    history = chat_history or []

    try:
        # 1. 建立或取得對話
        conversation = get_or_create_conversation(
            db, conversation_id, user_id, title=question
        )

        save_message(db, conversation.id, "user", question)
        db.commit()

        conv_id = conversation.id

        # 回傳 conversation_id 讓前端追蹤
        yield f"data: {json.dumps({'type': 'conversation_id', 'conversation_id': conv_id})}\n\n"

        # 2. 組裝歷史訊息 + 當前問題
        agent_messages = []
        for msg in history:
            if msg["role"] == "user":
                agent_messages.append(HumanMessage(content=msg["content"]))
            else:
                agent_messages.append(AIMessage(content=msg["content"]))
        agent_messages.append(HumanMessage(content=question))

        # 3. 串流執行 Agent
        agent_app = _build_agent_app(is_admin=is_admin)

        # stream_mode="messages" 讓 LangGraph 逐 token yield AIMessageChunk
        for msg_chunk, _metadata in agent_app.stream(
            {"messages": agent_messages},
            stream_mode="messages",
        ):
            # 只串流 AI 的文字回答（跳過工具呼叫 chunk）
            if isinstance(msg_chunk, AIMessageChunk) and msg_chunk.content:
                if not msg_chunk.tool_call_chunks:
                    full_answer += msg_chunk.content
                    yield f"data: {json.dumps({'type': 'token', 'content': msg_chunk.content}, ensure_ascii=False)}\n\n"

        # 4. 送參考來源（如果 search_knowledge_base 有收集到）
        # Agent 拒答時不送 sources — 搜到的 chunk 跟問題無關，顯示只會誤導
        _REFUSAL_MARKERS = ("沒有權限", "沒有工具", "無法查詢", "找不到相關")
        agent_refused = any(m in full_answer for m in _REFUSAL_MARKERS)
        sources = _user_context_var.get().get("sources", []) if not agent_refused else []
        # 按相關度排序，最多送 5 筆給前端
        sources.sort(key=lambda s: s["relevance_score"], reverse=True)
        sources = sources[:5]
        if sources:
            yield f"data: {json.dumps({'type': 'sources', 'sources': sources}, ensure_ascii=False)}\n\n"

        yield f"data: {json.dumps({'type': 'done'})}\n\n"

        # 5. 存 assistant 回答
        save_message(db, conv_id, "assistant", full_answer, sources if sources else None)
        db.commit()
        assistant_saved = True

    finally:
        # 斷線時保存 partial answer
        if not assistant_saved and full_answer and conv_id is not None:
            try:
                save_message(
                    db,
                    conv_id,
                    "assistant",
                    full_answer + "\n\n[使用者中斷]",
                )
                db.commit()
            except Exception:
                db.rollback()

        db.close()
