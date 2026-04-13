from pydantic import BaseModel, Field
from typing import Optional
from datetime import datetime


class RejectRequest(BaseModel):
    """知識庫文件審核拒絕請求模型"""

    reason: str = Field(min_length=1, max_length=500)


class ReviewDocumentItem(BaseModel):
    """知識庫文件審核項目模型"""

    id: int
    filename: str
    file_type: str
    file_size: int
    permission_level: str
    department_id: Optional[int] = None
    department_name: Optional[str] = None
    status: str
    uploaded_by: int
    uploaded_by_name: Optional[str] = None
    created_at: datetime

    class Config:
        from_attributes = True
