from sqlalchemy import (
    Column,
    Integer,
    String,
    DateTime,
    Boolean,
    Enum,
    ForeignKey,
    Text,
    UniqueConstraint,
    JSON,
)
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship
from app.database import Base


class KnowledgeFolder(Base):
    """知識庫資料夾模型"""

    __tablename__ = "knowledge_folders"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(100), nullable=False)
    parent_id = Column(
        Integer,
        ForeignKey("knowledge_folders.id", ondelete="RESTRICT"),
        nullable=True,
    )
    department_id = Column(
        Integer,
        ForeignKey("departments.id", ondelete="SET NULL"),
        nullable=True,
    )
    created_by = Column(
        Integer,
        ForeignKey("users.id"),
        nullable=False,
    )

    created_at = Column(DateTime, server_default=func.now(), nullable=False)
    updated_at = Column(
        DateTime, server_default=func.now(), onupdate=func.now(), nullable=False
    )

    parent = relationship("KnowledgeFolder", remote_side=[id], backref="children")
    department = relationship("Department")
    creator = relationship("User")
    documents = relationship("KnowledgeDocument", back_populates="folder")


class KnowledgeDocument(Base):
    """知識庫文件模型"""

    __tablename__ = "knowledge_documents"

    id = Column(Integer, primary_key=True, autoincrement=True)
    filename = Column(String(255), nullable=False)
    file_type = Column(String(20), nullable=False)

    folder_id = Column(
        Integer,
        ForeignKey("knowledge_folders.id", ondelete="SET NULL"),
        nullable=True,
    )

    permission_level = Column(
        Enum("public", "department", name="kb_permission_level_enum"),
        nullable=False,
        default="public",
    )
    department_id = Column(
        Integer,
        ForeignKey("departments.id", ondelete="SET NULL"),
        nullable=True,
    )

    current_version_id = Column(
        Integer,
        ForeignKey("knowledge_doc_versions.id", ondelete="SET NULL"),
        nullable=True,
    )

    uploaded_by = Column(
        Integer,
        ForeignKey("users.id"),
        nullable=False,
        index=True,
    )
    is_deleted = Column(Boolean, nullable=False, default=False)

    created_at = Column(DateTime, server_default=func.now(), nullable=False)
    updated_at = Column(
        DateTime, server_default=func.now(), onupdate=func.now(), nullable=False
    )

    folder = relationship("KnowledgeFolder", back_populates="documents")
    uploader = relationship("User", foreign_keys=[uploaded_by])
    department = relationship("Department")
    current_version = relationship("KnowledgeDocVersion", foreign_keys=[current_version_id])
    versions = relationship("KnowledgeDocVersion", foreign_keys="KnowledgeDocVersion.document_id", back_populates="document")


class KnowledgeDocVersion(Base):
    """知識庫文件版本模型"""

    __tablename__ = "knowledge_doc_versions"

    id = Column(Integer, primary_key=True, autoincrement=True)
    document_id = Column(
        Integer,
        ForeignKey("knowledge_documents.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    version = Column(Integer, nullable=False)
    file_path = Column(String(500), nullable=False)
    file_size = Column(Integer, nullable=False)
    checksum = Column(String(64), nullable=True)
    restored_from = Column(Integer, nullable=True)

    status = Column(
        Enum("pending", "approved", "rejected", name="kb_version_status_enum"),
        nullable=False,
        default="pending",
    )
    vectorization_status = Column(
        Enum("none", "processing", "completed", "failed", name="kb_version_vec_status_enum"),
        nullable=False,
        default="none",
    )
    chunk_count = Column(Integer, nullable=False, default=0)
    error_message = Column(Text, nullable=True)

    reviewed_by = Column(
        Integer,
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    reviewed_at = Column(DateTime, nullable=True)
    reject_reason = Column(String(500), nullable=True)

    uploaded_by = Column(
        Integer,
        ForeignKey("users.id"),
        nullable=False,
        index=True,
    )

    created_at = Column(DateTime, server_default=func.now(), nullable=False)
    updated_at = Column(
        DateTime, server_default=func.now(), onupdate=func.now(), nullable=False
    )

    document = relationship("KnowledgeDocument", foreign_keys=[document_id], back_populates="versions")
    uploader = relationship("User", foreign_keys=[uploaded_by])
    reviewer = relationship("User", foreign_keys=[reviewed_by])


class KnowledgeFavorite(Base):
    """知識庫收藏模型"""

    __tablename__ = "knowledge_favorites"
    __table_args__ = (
        UniqueConstraint("user_id", "document_id", name="uk_user_document"),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(
        Integer,
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    document_id = Column(
        Integer,
        ForeignKey("knowledge_documents.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    created_at = Column(DateTime, server_default=func.now(), nullable=False)

    user = relationship("User")
    document = relationship("KnowledgeDocument")


class ChatConversation(Base):
    """聊天會話模型"""

    __tablename__ = "chat_conversations"

    id = Column(Integer, primary_key=True, autoincrement=True)
    title = Column(String(255), nullable=False)
    user_id = Column(
        Integer,
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    created_at = Column(DateTime, server_default=func.now(), nullable=False)
    updated_at = Column(
        DateTime, server_default=func.now(), onupdate=func.now(), nullable=False
    )

    user = relationship("User")
    messages = relationship("ChatMessage", back_populates="conversation", cascade="all, delete-orphan")


class ChatMessage(Base):
    """聊天訊息模型"""

    __tablename__ = "chat_messages"

    id = Column(Integer, primary_key=True, autoincrement=True)
    conversation_id = Column(
        Integer,
        ForeignKey("chat_conversations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    role = Column(
        Enum("user", "assistant", name="chat_role_enum"),
        nullable=False,
    )
    content = Column(Text, nullable=False)
    sources = Column(JSON, nullable=True)

    created_at = Column(DateTime, server_default=func.now(), nullable=False)

    conversation = relationship("ChatConversation", back_populates="messages")
