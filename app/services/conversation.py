# 對話紀錄 CRUD — RAG 和 Agent 共用的對話管理邏輯

from sqlalchemy.orm import Session

from app.models.knowledge import ChatConversation, ChatMessage


def get_or_create_conversation(
    db: Session,
    conversation_id: int | None,
    user_id: int,
    title: str,
) -> ChatConversation:
    '''根據 conversation_id 獲取對話紀錄，如果不存在則創建一個新的對話紀錄'''
    if conversation_id:
        conversation = db.query(ChatConversation).filter(
            ChatConversation.id == conversation_id,
            ChatConversation.user_id == user_id,
        ).first()
        if conversation:
            return conversation

    conversation = ChatConversation(
        title=title[:100],
        user_id=user_id,
    )
    db.add(conversation)
    db.flush()
    return conversation


def get_chat_history(db: Session, conversation_id: int) -> list[dict]:
    '''根據 conversation_id 獲取對話歷史紀錄，按照時間順序返回'''
    messages = db.query(ChatMessage).filter(
        ChatMessage.conversation_id == conversation_id,
    ).order_by(ChatMessage.created_at).all()

    return [
        {"role": msg.role, "content": msg.content}
        for msg in messages
    ]


def save_message(
    db: Session,
    conversation_id: int,
    role: str,
    content: str,
    sources: list[dict] | None = None,
):
    '''將對話訊息保存到資料庫中，包含使用者的問題和助理的回答，以及相關的來源資訊'''
    message = ChatMessage(
        conversation_id=conversation_id,
        role=role,
        content=content,
        sources=sources,
    )
    db.add(message)


def get_conversations(db: Session, user_id: int) -> list[ChatConversation]:
    '''根據 user_id 獲取該使用者的所有對話紀錄，按照更新時間排序返回'''
    return db.query(ChatConversation).filter(
        ChatConversation.user_id == user_id,
    ).order_by(ChatConversation.updated_at.desc()).all()


def get_conversation_messages(
    db: Session, conversation_id: int, user_id: int
) -> ChatConversation | None:
    '''根據 conversation_id 和 user_id 獲取對話紀錄，確保該對話紀錄屬於該使用者'''
    return db.query(ChatConversation).filter(
        ChatConversation.id == conversation_id,
        ChatConversation.user_id == user_id,
    ).first()


def delete_conversation(
    db: Session, conversation_id: int, user_id: int
) -> bool:
    '''根據 conversation_id 和 user_id 刪除對話紀錄，確保該對話紀錄屬於該使用者'''
    conversation = db.query(ChatConversation).filter(
        ChatConversation.id == conversation_id,
        ChatConversation.user_id == user_id,
    ).first()

    if not conversation:
        return False

    db.delete(conversation)
    db.commit()
    return True
