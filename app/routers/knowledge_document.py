import os
from fastapi import APIRouter, Depends, UploadFile, File, Form, HTTPException, status
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session
from typing import Optional

from app.database import get_db
from app.services.auth import get_current_user
from app.models import User
from app.config import settings
from app.services import knowledge_document as document_service

router = APIRouter(
    prefix="/knowledge",
    tags=["knowledge-document"],
    dependencies=[Depends(get_current_user)],
)


@router.post("/documents")
async def upload_document(
    files: list[UploadFile] = File(...),
    permission_level: str = Form(default="public"),
    department_id: Optional[int] = Form(default=None),
    folder_id: Optional[int] = Form(default=None),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """上傳一或多個新文件，同時建立 document + v1 版本（status=pending）"""

    if permission_level not in ("public", "department"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="permission_level 必須是 'public' 或 'department'",
        )

    if permission_level == "department" and department_id is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="permission_level 為 'department' 時必須提供 department_id",
        )

    results = []
    errors = []

    for file in files:
        extension = file.filename.rsplit(".", 1)[-1].lower() if "." in file.filename else ""
        if extension not in settings.ALLOWED_EXTENSIONS.split(","):
            errors.append(f"{file.filename}：不支援的格式 .{extension}")
            continue

        file_path, file_size, file_type, checksum = await document_service.save_uploaded_file(file)

        try:
            document, version = document_service.create_document(
                db=db,
                filename=file.filename,
                file_path=file_path,
                file_type=file_type,
                file_size=file_size,
                checksum=checksum,
                permission_level=permission_level,
                department_id=department_id,
                uploaded_by=current_user.id,
                folder_id=folder_id,
            )
        except Exception:
            if os.path.exists(file_path):
                os.remove(file_path)
            raise

        results.append({
            "id": document.id,
            "filename": document.filename,
            "file_type": document.file_type,
            "permission_level": document.permission_level,
            "version": version.version,
            "status": version.status,
            "vectorization_status": version.vectorization_status,
        })

    return {
        "success": True,
        "data": results,
        "errors": errors,
        "message": f"成功上傳 {len(results)} 個文件" + (f"，{len(errors)} 個失敗" if errors else ""),
    }


@router.get("/documents")
def list_documents(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """取得文件列表，版本相關資訊從 current_version 取得"""

    documents = document_service.get_documents(db)

    data = []
    for doc in documents:
        cv = doc.current_version
        # current_version 只在審核通過時設定；未通過時取最新版本顯示狀態
        if not cv and doc.versions:
            cv = max(doc.versions, key=lambda v: v.version)

        data.append({
            "id": doc.id,
            "filename": doc.filename,
            "file_type": doc.file_type,
            "file_size": cv.file_size if cv else None,
            "folder_id": doc.folder_id,
            "permission_level": doc.permission_level,
            "department_id": doc.department_id,
            "department_name": doc.department.name if doc.department else None,
            "status": cv.status if cv else "pending",
            "vectorization_status": cv.vectorization_status if cv else "none",
            "chunk_count": cv.chunk_count if cv else 0,
            "current_version": cv.version if cv else None,
            "uploaded_by": doc.uploaded_by,
            "uploaded_by_name": doc.uploader.name if doc.uploader else None,
            "created_at": doc.created_at,
        })

    return {
        "success": True,
        "data": data,
    }


@router.get("/documents/{document_id}")
def get_document(
    document_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """取得單一文件詳情，含目前版本資訊"""

    document = document_service.get_document_by_id(db, document_id)
    if not document:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="文件不存在",
        )

    cv = document.current_version

    return {
        "success": True,
        "data": {
            "id": document.id,
            "filename": document.filename,
            "file_type": document.file_type,
            "file_size": cv.file_size if cv else None,
            "folder_id": document.folder_id,
            "permission_level": document.permission_level,
            "department_id": document.department_id,
            "department_name": document.department.name if document.department else None,
            "status": cv.status if cv else "pending",
            "vectorization_status": cv.vectorization_status if cv else "none",
            "chunk_count": cv.chunk_count if cv else 0,
            "current_version": cv.version if cv else None,
            "uploaded_by": document.uploaded_by,
            "uploaded_by_name": document.uploader.name if document.uploader else None,
            "created_at": document.created_at,
            "updated_at": document.updated_at,
        },
    }


@router.delete("/documents/{document_id}")
def delete_document(
    document_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """軟刪除文件並清除 ChromaDB 中的 chunks"""

    document = document_service.get_document_by_id(db, document_id)
    if not document:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="文件不存在",
        )

    document_service.soft_delete_document(db, document)

    return {
        "success": True,
        "message": "文件已刪除",
    }


@router.post("/documents/{document_id}/versions")
async def upload_new_version(
    document_id: int,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """上傳新版本，檢查檔案類型一致 + checksum 防重複，status=pending 待審核"""

    document = document_service.get_document_by_id(db, document_id)
    if not document:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="文件不存在",
        )

    extension = file.filename.rsplit(".", 1)[-1].lower() if "." in file.filename else ""
    if extension != document.file_type:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"檔案類型必須是 .{document.file_type}，不接受 .{extension}",
        )

    file_path, file_size, file_type, checksum = await document_service.save_uploaded_file(file)

    latest = document_service.get_latest_version(db, document.id)
    if latest and latest.checksum == checksum:
        os.remove(file_path)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="檔案內容與最新版本相同，無需更新",
        )

    try:
        version = document_service.upload_new_version(
            db=db,
            document=document,
            file_path=file_path,
            file_size=file_size,
            checksum=checksum,
            uploaded_by=current_user.id,
        )
    except Exception:
        if os.path.exists(file_path):
            os.remove(file_path)
        raise

    return {
        "success": True,
        "data": {
            "id": version.id,
            "document_id": document.id,
            "version": version.version,
            "file_size": version.file_size,
            "status": version.status,
        },
        "message": f"已上傳第 {version.version} 版",
    }


@router.get("/documents/{document_id}/versions")
def get_versions(
    document_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """取得文件的所有版本列表，含 is_current 標記"""

    document = document_service.get_document_by_id(db, document_id)
    if not document:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="文件不存在",
        )

    versions = document_service.get_versions(db, document.id)

    return {
        "success": True,
        "data": [
            {
                "id": v.id,
                "version": v.version,
                "file_size": v.file_size,
                "status": v.status,
                "vectorization_status": v.vectorization_status,
                "chunk_count": v.chunk_count,
                "reject_reason": v.reject_reason,
                "restored_from": v.restored_from,
                "uploaded_by": v.uploaded_by,
                "uploaded_by_name": v.uploader.name if v.uploader else None,
                "reviewed_by": v.reviewed_by,
                "reviewed_at": v.reviewed_at,
                "is_current": v.id == document.current_version_id,
                "created_at": v.created_at,
            }
            for v in versions
        ],
    }


@router.get("/documents/{document_id}/versions/{version_id}/download")
def download_version(
    document_id: int,
    version_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """下載指定版本的檔案，檔名加上版本號"""

    document = document_service.get_document_by_id(db, document_id)
    if not document:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="文件不存在",
        )

    version = document_service.get_version_by_id(db, version_id)
    if not version or version.document_id != document.id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="版本不存在",
        )

    if not os.path.exists(version.file_path):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="檔案不存在",
        )

    download_filename = f"{document.filename.rsplit('.', 1)[0]}_v{version.version}.{document.file_type}"

    return FileResponse(
        path=version.file_path,
        filename=download_filename,
        media_type="application/octet-stream",
    )


@router.post("/documents/{document_id}/versions/{version_id}/restore")
def restore_version(
    document_id: int,
    version_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """還原指定版本（複製檔案建立新版本，需重新審核），只能還原 approved 的版本"""

    document = document_service.get_document_by_id(db, document_id)
    if not document:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="文件不存在",
        )

    source_version = document_service.get_version_by_id(db, version_id)
    if not source_version or source_version.document_id != document.id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="版本不存在",
        )

    if source_version.status != "approved":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="只能還原已通過審核的版本",
        )

    new_version = document_service.restore_version(
        db=db,
        document=document,
        source_version=source_version,
        uploaded_by=current_user.id,
    )

    return {
        "success": True,
        "data": {
            "id": new_version.id,
            "document_id": document.id,
            "version": new_version.version,
            "status": new_version.status,
            "restored_from": source_version.version,
        },
        "message": f"已從第 {source_version.version} 版還原，建立第 {new_version.version} 版（待審核）",
    }
