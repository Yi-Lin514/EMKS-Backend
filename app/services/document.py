import os
import uuid
import hashlib
import shutil
from datetime import datetime
from sqlalchemy.orm import Session, joinedload
from sqlalchemy import func as sql_func
from fastapi import UploadFile

from app.config import settings
from app.models.knowledge import KnowledgeDocument, KnowledgeDocVersion
from app.services import embedding as embedding_service
from app.services import vector_store as vector_store_service


async def save_uploaded_file(file: UploadFile) -> tuple[str, int, str, str]:
    """保存上傳的文件到磁盤，並返回文件路徑、大小、類型和校驗碼"""

    original_filename = file.filename
    extension = original_filename.rsplit(".", 1)[-1].lower()

    date_dir = datetime.now().strftime("%Y/%m")
    upload_path = f"{settings.UPLOAD_DIR}/{date_dir}"
    os.makedirs(upload_path, exist_ok=True)

    unique_filename = f"{uuid.uuid4().hex}.{extension}"
    file_path = f"{upload_path}/{unique_filename}"

    content = await file.read()
    with open(file_path, "wb") as f:
        f.write(content)

    file_size = os.path.getsize(file_path)
    checksum = hashlib.sha256(content).hexdigest()

    return file_path, file_size, extension, checksum


def create_document(
    db: Session,
    filename: str,
    file_path: str,
    file_type: str,
    file_size: int,
    checksum: str,
    permission_level: str,
    department_id: int | None,
    uploaded_by: int,
    folder_id: int | None = None,
) -> tuple[KnowledgeDocument, KnowledgeDocVersion]:
    """建立知識文件並同時建立 v1 版本紀錄，使用 flush 確保兩筆資料在同一筆交易"""

    document = KnowledgeDocument(
        filename=filename,
        file_type=file_type,
        folder_id=folder_id,
        permission_level=permission_level,
        department_id=department_id,
        uploaded_by=uploaded_by,
    )
    db.add(document)
    db.flush()

    version = KnowledgeDocVersion(
        document_id=document.id,
        version=1,
        file_path=file_path,
        file_size=file_size,
        checksum=checksum,
        uploaded_by=uploaded_by,
    )
    db.add(version)
    db.commit()
    db.refresh(document)
    db.refresh(version)
    return document, version


def get_next_version_number(db: Session, document_id: int) -> int:
    """獲取知識文件的下一個版本號"""

    max_version = (
        db.query(sql_func.max(KnowledgeDocVersion.version))
        .filter(KnowledgeDocVersion.document_id == document_id)
        .scalar()
    )
    return (max_version or 0) + 1


def get_latest_version(db: Session, document_id: int) -> KnowledgeDocVersion | None:
    """獲取知識文件的最新版本"""

    return (
        db.query(KnowledgeDocVersion)
        .filter(KnowledgeDocVersion.document_id == document_id)
        .order_by(KnowledgeDocVersion.version.desc())
        .first()
    )


def upload_new_version(
    db: Session,
    document: KnowledgeDocument,
    file_path: str,
    file_size: int,
    checksum: str,
    uploaded_by: int,
) -> KnowledgeDocVersion:
    """上傳新的文件版本"""

    next_version = get_next_version_number(db, document.id)

    version = KnowledgeDocVersion(
        document_id=document.id,
        version=next_version,
        file_path=file_path,
        file_size=file_size,
        checksum=checksum,
        uploaded_by=uploaded_by,
    )
    db.add(version)
    db.commit()
    db.refresh(version)
    return version


def get_versions(db: Session, document_id: int) -> list[KnowledgeDocVersion]:
    """獲取知識文件的所有版本"""

    return (
        db.query(KnowledgeDocVersion)
        .filter(KnowledgeDocVersion.document_id == document_id)
        .order_by(KnowledgeDocVersion.version.desc())
        .all()
    )


def get_version_by_id(db: Session, version_id: int) -> KnowledgeDocVersion | None:
    """獲取指定ID的知識文件版本"""

    return db.query(KnowledgeDocVersion).filter(KnowledgeDocVersion.id == version_id).first()


def restore_version(
    db: Session,
    document: KnowledgeDocument,
    source_version: KnowledgeDocVersion,
    uploaded_by: int,
) -> KnowledgeDocVersion:
    """複製指定版本的檔案並建立新版本紀錄（status=pending，需重新審核）"""

    original_path = source_version.file_path
    extension = original_path.rsplit(".", 1)[-1].lower()

    date_dir = datetime.now().strftime("%Y/%m")
    upload_path = f"{settings.UPLOAD_DIR}/{date_dir}"
    os.makedirs(upload_path, exist_ok=True)

    new_filename = f"{uuid.uuid4().hex}.{extension}"
    new_path = f"{upload_path}/{new_filename}"
    shutil.copy2(original_path, new_path)

    next_version = get_next_version_number(db, document.id)

    version = KnowledgeDocVersion(
        document_id=document.id,
        version=next_version,
        file_path=new_path,
        file_size=source_version.file_size,
        checksum=source_version.checksum,
        restored_from=source_version.version,
        uploaded_by=uploaded_by,
    )
    db.add(version)
    db.commit()
    db.refresh(version)
    return version


def get_documents(db: Session, extra_filter=None) -> list[KnowledgeDocument]:
    """獲取所有知識文件；extra_filter 用於套入 RBAC 的 permission_level/department_id 過濾。"""

    query = (
        db.query(KnowledgeDocument)
        .options(
            joinedload(KnowledgeDocument.current_version),
            joinedload(KnowledgeDocument.uploader),
            joinedload(KnowledgeDocument.department),
            joinedload(KnowledgeDocument.versions),
        )
        .filter(KnowledgeDocument.is_deleted == False)
    )
    if extra_filter is not None:
        query = query.filter(extra_filter)
    return query.order_by(KnowledgeDocument.created_at.desc()).all()


def get_document_by_id(db: Session, document_id: int) -> KnowledgeDocument | None:
    """獲取指定ID的知識文件"""

    return (
        db.query(KnowledgeDocument)
        .options(
            joinedload(KnowledgeDocument.current_version),
            joinedload(KnowledgeDocument.uploader),
            joinedload(KnowledgeDocument.department),
        )
        .filter(
            KnowledgeDocument.id == document_id,
            KnowledgeDocument.is_deleted == False,
        )
        .first()
    )


def soft_delete_document(db: Session, document: KnowledgeDocument) -> None:
    """軟刪除知識文件"""

    document.is_deleted = True
    db.commit()

    vector_store_service.delete_document_chunks(document.id)


def process_vectorization(db: Session, version: KnowledgeDocVersion) -> None:
    """處理知識文件版本的向量化"""

    version.vectorization_status = "processing"
    db.commit()

    try:
        document = version.document

        text = embedding_service.extract_text_from_file(
            version.file_path, document.file_type
        )

        chunks = embedding_service.chunk_text(text)

        if not chunks:
            version.vectorization_status = "failed"
            version.error_message = "No text content extracted"
            db.commit()
            return

        embeddings = embedding_service.get_embeddings_batch(chunks)

        metadata = {
            "document_title": document.filename,
            "permission_level": document.permission_level,
            "department_id": document.department_id,
        }

        vector_store_service.delete_document_chunks(document.id)

        chunk_count = vector_store_service.add_chunks(
            document_id=document.id,
            chunks=chunks,
            embeddings=embeddings,
            metadata=metadata,
        )

        version.vectorization_status = "completed"
        version.chunk_count = chunk_count
        version.error_message = None
        db.commit()

    except Exception as e:
        version.vectorization_status = "failed"
        version.error_message = str(e)
        db.commit()
