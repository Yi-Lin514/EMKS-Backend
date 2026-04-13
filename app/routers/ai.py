from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session
from starlette.concurrency import iterate_in_threadpool

from app.database import get_db
from app.services.auth import get_current_user
from app.models import User
from app.dependencies.rbac import get_user_permissions
from app.schemas.ai import (
    AgentRequest,
    ConversationResponse,
    ConversationDetailResponse,
    MessageResponse,
)
from app.services import agent as agent_service
from app.services import conversation as conv_service

router = APIRouter(
    prefix="/ai",
    tags=["ai"],
    dependencies=[Depends(get_current_user)],
)


def _check_admin(db: Session, user_id: int) -> bool:
    permissions = get_user_permissions(db, user_id)
    return "ai:admin_tools" in permissions


@router.post("/agent")
async def agent_chat(
    payload: AgentRequest,
    request: Request,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """統一入口 — Agent 串流回答（SSE）。

    ContextVar 必須在這裡 set（async handler），不能在 generator 裡 set。
    原因：iterate_in_threadpool 每次 next() 都複製一份 context，
    只有在複製之前就 set 好的值才會帶進每個 worker thread。
    """
    is_admin = _check_admin(db, current_user.id)

    # 讀 chat_history（router db 只做讀取，不跨 thread）
    chat_history = []
    if payload.conversation_id:
        chat_history = conv_service.get_chat_history(db, payload.conversation_id)

    # 在 async context 設定 ContextVar — iterate_in_threadpool 複製時會帶上
    agent_service.set_user_context(
        is_admin=is_admin,
        department_id=current_user.department_id,
        user_id=current_user.id,
        chat_history=chat_history,
    )

    sync_generator = agent_service.run_agent_stream(
        question=payload.question,
        user_id=current_user.id,
        conversation_id=payload.conversation_id,
        is_admin=is_admin,
        chat_history=chat_history,
    )

    async def event_generator():
        try:
            async for chunk in iterate_in_threadpool(sync_generator):
                if await request.is_disconnected():
                    break
                yield chunk
        finally:
            sync_generator.close()

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )


@router.get("/conversations")
def get_conversations(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    conversations = conv_service.get_conversations(db, current_user.id)

    return {
        "success": True,
        "data": [
            ConversationResponse(
                id=conv.id,
                title=conv.title,
                created_at=conv.created_at,
                updated_at=conv.updated_at,
            )
            for conv in conversations
        ],
    }


@router.get("/conversations/{conversation_id}/messages")
def get_conversation_messages(
    conversation_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    conversation = conv_service.get_conversation_messages(
        db, conversation_id, current_user.id
    )

    if not conversation:
        raise HTTPException(status_code=404, detail="對話不存在")

    return {
        "success": True,
        "data": ConversationDetailResponse(
            id=conversation.id,
            title=conversation.title,
            messages=[
                MessageResponse(
                    id=msg.id,
                    role=msg.role,
                    content=msg.content,
                    sources=msg.sources,
                    created_at=msg.created_at,
                )
                for msg in conversation.messages
            ],
            created_at=conversation.created_at,
        ),
    }


@router.delete("/conversations/{conversation_id}")
def delete_conversation(
    conversation_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    deleted = conv_service.delete_conversation(
        db, conversation_id, current_user.id
    )

    if not deleted:
        raise HTTPException(status_code=404, detail="對話不存在")

    return {
        "success": True,
        "message": "對話已刪除",
    }
