from pydantic import BaseModel
from typing import Optional
from datetime import datetime


class ChatRequest(BaseModel):
    question: str
    conversation_id: Optional[int] = None


class AgentRequest(BaseModel):
    question: str
    conversation_id: Optional[int] = None


class SourceDocument(BaseModel):
    document_id: int
    document_title: str
    chunk_content: str
    relevance_score: float
    current_version_id: Optional[int] = None


class ChatResponse(BaseModel):
    answer: str
    sources: list[SourceDocument]
    conversation_id: int


class MessageResponse(BaseModel):
    id: int
    role: str
    content: str
    sources: Optional[list[SourceDocument]] = None
    created_at: datetime


class ConversationResponse(BaseModel):
    id: int
    title: str
    created_at: datetime
    updated_at: datetime


class ConversationDetailResponse(BaseModel):
    id: int
    title: str
    messages: list[MessageResponse]
    created_at: datetime
