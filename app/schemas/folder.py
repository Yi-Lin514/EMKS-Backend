from pydantic import BaseModel, Field
from typing import Optional, List
from datetime import datetime


class FolderCreate(BaseModel):
    """知識庫資料夾創建請求模型"""

    name: str = Field(min_length=1, max_length=100)
    parent_id: Optional[int] = None
    department_id: Optional[int] = None


class FolderUpdate(BaseModel):
    """知識庫資料夾更新請求模型"""

    name: Optional[str] = Field(default=None, min_length=1, max_length=100)
    parent_id: Optional[int] = None
    department_id: Optional[int] = None


class FolderResponse(BaseModel):
    """知識庫資料夾響應模型"""

    id: int
    name: str
    parent_id: Optional[int] = None
    department_id: Optional[int] = None
    department_name: Optional[str] = None
    created_by: int
    created_at: datetime

    class Config:
        from_attributes = True


class FolderTreeNode(BaseModel):
    """知識庫資料夾樹節點模型"""

    id: int
    name: str
    parent_id: Optional[int] = None
    department_id: Optional[int] = None
    department_name: Optional[str] = None
    children: List["FolderTreeNode"] = []

    class Config:
        from_attributes = True
