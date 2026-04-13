from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.database import get_db
from app.services.auth import get_current_user
from app.models import User
from app.services import knowledge_favorite as favorite_service
from app.services import knowledge_document as document_service

router = APIRouter(
    prefix="/knowledge",
    tags=["knowledge-favorite"],
    dependencies=[Depends(get_current_user)],
)


@router.post("/favorites/{document_id}")
def add_favorite(
    document_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """收藏文件，IntegrityError 攔截重複收藏"""

    document = document_service.get_document_by_id(db, document_id)
    if not document:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="文件不存在",
        )

    try:
        favorite = favorite_service.add_favorite(db, current_user.id, document_id)
    except IntegrityError:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="已收藏過此文件",
        )

    return {
        "success": True,
        "data": {
            "id": favorite.id,
            "document_id": favorite.document_id,
            "created_at": favorite.created_at,
        },
        "message": "收藏成功",
    }


@router.delete("/favorites/{document_id}")
def remove_favorite(
    document_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """取消收藏文件"""

    removed = favorite_service.remove_favorite(db, current_user.id, document_id)
    if not removed:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="未收藏此文件",
        )

    return {
        "success": True,
        "message": "已取消收藏",
    }


@router.get("/favorites")
def get_favorites(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """取得使用者的收藏列表，版本資訊從 current_version 取得，過濾已刪除文件"""

    favorites = favorite_service.get_favorites(db, current_user.id)

    return {
        "success": True,
        "data": [
            {
                "id": fav.id,
                "document_id": fav.document_id,
                "filename": fav.document.filename,
                "file_type": fav.document.file_type,
                "file_size": fav.document.current_version.file_size if fav.document.current_version else None,
                "folder_id": fav.document.folder_id,
                "permission_level": fav.document.permission_level,
                "vectorization_status": fav.document.current_version.vectorization_status if fav.document.current_version else "none",
                "chunk_count": fav.document.current_version.chunk_count if fav.document.current_version else 0,
                "uploaded_by_name": fav.document.uploader.name if fav.document.uploader else None,
                "created_at": fav.document.created_at,
                "favorited_at": fav.created_at,
            }
            for fav in favorites
            if not fav.document.is_deleted
        ],
    }
