from datetime import datetime
from sqlalchemy.orm import Session, joinedload

from app.models.knowledge import KnowledgeDocument, KnowledgeDocVersion


def get_pending_versions(db: Session) -> list[KnowledgeDocVersion]:
    """獲取待審核的知識文件版本"""

    return (
        db.query(KnowledgeDocVersion)
        .join(KnowledgeDocument, KnowledgeDocVersion.document_id == KnowledgeDocument.id)
        .options(
            joinedload(KnowledgeDocVersion.document).joinedload(KnowledgeDocument.department),
            joinedload(KnowledgeDocVersion.uploader),
        )
        .filter(
            KnowledgeDocVersion.status == "pending",
            KnowledgeDocument.is_deleted == False,
        )
        .order_by(KnowledgeDocVersion.created_at.asc())
        .all()
    )


def approve_version(
    db: Session, version: KnowledgeDocVersion, reviewer_id: int
) -> None:
    """審核通過版本，更新狀態並將 document.current_version_id 指向此版本"""

    version.status = "approved"
    version.reviewed_by = reviewer_id
    version.reviewed_at = datetime.now()

    document = version.document
    document.current_version_id = version.id
    db.commit()


def reject_version(
    db: Session, version: KnowledgeDocVersion, reviewer_id: int, reason: str
) -> None:
    """拒絕知識文件版本"""

    version.status = "rejected"
    version.reviewed_by = reviewer_id
    version.reviewed_at = datetime.now()
    version.reject_reason = reason
    db.commit()
