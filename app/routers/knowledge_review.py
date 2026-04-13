from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.database import get_db
from app.services.auth import get_current_user
from app.models import User
from app.dependencies.rbac import require_admin
from app.services import knowledge_review as review_service
from app.services import knowledge_document as document_service
from app.schemas.knowledge_review import RejectRequest

router = APIRouter(
    prefix="/knowledge",
    tags=["knowledge-review"],
    dependencies=[Depends(get_current_user)],
)


@router.get("/review")
def get_pending_versions(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    """取得所有待審核的版本列表（管理員限定）"""

    versions = review_service.get_pending_versions(db)

    return {
        "success": True,
        "data": [
            {
                "id": v.id,
                "document_id": v.document.id,
                "filename": v.document.filename,
                "file_type": v.document.file_type,
                "file_size": v.file_size,
                "version": v.version,
                "permission_level": v.document.permission_level,
                "department_id": v.document.department_id,
                "department_name": v.document.department.name if v.document.department else None,
                "status": v.status,
                "uploaded_by": v.uploaded_by,
                "uploaded_by_name": v.uploader.name if v.uploader else None,
                "created_at": v.created_at,
            }
            for v in versions
        ],
    }


@router.post("/review/{version_id}/approve")
def approve_version(
    version_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    """審核通過版本（管理員限定），更新 current_version_id 並觸發向量化"""

    version = document_service.get_version_by_id(db, version_id)
    if not version:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="版本不存在",
        )

    if version.document.is_deleted:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="文件已被刪除",
        )

    if version.status != "pending":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"版本狀態為 {version.status}，無法審核",
        )

    review_service.approve_version(db, version, current_user.id)
    # TODO: 目前向量化是同步阻塞（大檔案會卡住 request），未來可改用 Celery/BackgroundTasks 非同步處理
    document_service.process_vectorization(db, version)

    return {
        "success": True,
        "data": {
            "id": version.id,
            "document_id": version.document_id,
            "version": version.version,
            "status": version.status,
            "vectorization_status": version.vectorization_status,
            "chunk_count": version.chunk_count,
            "reviewed_by": version.reviewed_by,
            "reviewed_at": version.reviewed_at,
        },
        "message": "版本已批准，向量化處理中",
    }


@router.post("/review/{version_id}/reject")
def reject_version(
    version_id: int,
    body: RejectRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    """駁回版本（管理員限定），記錄駁回原因，版本保留在歷史紀錄中"""

    version = document_service.get_version_by_id(db, version_id)
    if not version:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="版本不存在",
        )

    if version.document.is_deleted:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="文件已被刪除",
        )

    if version.status != "pending":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"版本狀態為 {version.status}，無法審核",
        )

    review_service.reject_version(db, version, current_user.id, body.reason)

    return {
        "success": True,
        "data": {
            "id": version.id,
            "document_id": version.document_id,
            "version": version.version,
            "status": version.status,
            "reject_reason": version.reject_reason,
            "reviewed_by": version.reviewed_by,
            "reviewed_at": version.reviewed_at,
        },
        "message": "版本已駁回",
    }
