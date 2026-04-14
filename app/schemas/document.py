from pydantic import BaseModel
from typing import Optional
from datetime import datetime


class KnowledgeDocumentUploadResponse(BaseModel):
    """知識庫文件上傳響應模型"""

    id: int
    filename: str
    file_type: str
    permission_level: str
    vectorization_status: str
    uploaded_by: int
    created_at: datetime

    class Config:
        from_attributes = True


class KnowledgeDocumentListItem(BaseModel):
    """知識庫文件列表項目模型"""

    id: int
    filename: str
    file_type: str
    file_size: int
    permission_level: str
    department_id: Optional[int] = None
    department_name: Optional[str] = None
    vectorization_status: str
    chunk_count: int
    uploaded_by: int
    uploaded_by_name: Optional[str] = None
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class KnowledgeDocumentDetail(BaseModel):
    """知識庫文件詳情模型"""

    id: int
    filename: str
    file_path: str
    file_type: str
    file_size: int
    permission_level: str
    department_id: Optional[int] = None
    department_name: Optional[str] = None
    vectorization_status: str
    chunk_count: int
    error_message: Optional[str] = None
    uploaded_by: int
    uploaded_by_name: Optional[str] = None
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True
