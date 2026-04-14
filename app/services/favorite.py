from sqlalchemy.orm import Session

from app.models.knowledge import KnowledgeFavorite


def add_favorite(db: Session, user_id: int, document_id: int) -> KnowledgeFavorite:
    """添加知識文件到用戶收藏夾"""

    favorite = KnowledgeFavorite(
        user_id=user_id,
        document_id=document_id,
    )
    db.add(favorite)
    db.commit()
    db.refresh(favorite)
    return favorite


def remove_favorite(db: Session, user_id: int, document_id: int) -> bool:
    """從用戶收藏夾中移除知識文件"""

    favorite = (
        db.query(KnowledgeFavorite)
        .filter(
            KnowledgeFavorite.user_id == user_id,
            KnowledgeFavorite.document_id == document_id,
        )
        .first()
    )
    if not favorite:
        return False

    db.delete(favorite)
    db.commit()
    return True


def get_favorites(db: Session, user_id: int) -> list[KnowledgeFavorite]:
    """獲取用戶的收藏文件"""

    return (
        db.query(KnowledgeFavorite)
        .filter(KnowledgeFavorite.user_id == user_id)
        .order_by(KnowledgeFavorite.created_at.desc())
        .all()
    )
