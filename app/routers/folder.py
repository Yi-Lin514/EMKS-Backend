from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.database import get_db
from app.services.auth import get_current_user
from app.models import User
from app.dependencies.rbac import require_admin
from app.services import folder as folder_service
from app.models.knowledge import KnowledgeFolder, KnowledgeDocument
from app.schemas.folder import FolderCreate, FolderUpdate

router = APIRouter(
    prefix="/knowledge",
    tags=["knowledge-folder"],
    dependencies=[Depends(get_current_user)],
)


@router.post("/folders")
def create_folder(
    body: FolderCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    """新增資料夾（管理員限定），驗證父資料夾存在性"""

    if body.parent_id:
        parent = folder_service.get_folder_by_id(db, body.parent_id)
        if not parent:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="父資料夾不存在",
            )

    folder = folder_service.create_folder(
        db=db,
        name=body.name,
        parent_id=body.parent_id,
        department_id=body.department_id,
        created_by=current_user.id,
    )

    return {
        "success": True,
        "data": {
            "id": folder.id,
            "name": folder.name,
            "parent_id": folder.parent_id,
            "department_id": folder.department_id,
            "created_by": folder.created_by,
            "created_at": folder.created_at,
        },
        "message": "資料夾建立成功",
    }


@router.get("/folders/tree")
def get_folder_tree(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """取得資料夾樹狀結構"""

    folders = folder_service.get_folder_tree(db)
    tree = folder_service.build_tree(folders)

    return {
        "success": True,
        "data": tree,
    }


@router.put("/folders/{folder_id}")
def update_folder(
    folder_id: int,
    body: FolderUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    """更新資料夾（管理員限定），防止自我參照"""

    folder = folder_service.get_folder_by_id(db, folder_id)
    if not folder:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="資料夾不存在",
        )

    if body.parent_id is not None:
        if body.parent_id == folder_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="資料夾不能設為自己的子資料夾",
            )
        parent = folder_service.get_folder_by_id(db, body.parent_id)
        if not parent:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="父資料夾不存在",
            )

    update_data = body.model_dump(exclude_unset=True)
    folder = folder_service.update_folder(
        db=db,
        folder=folder,
        **update_data,
    )

    return {
        "success": True,
        "data": {
            "id": folder.id,
            "name": folder.name,
            "parent_id": folder.parent_id,
            "department_id": folder.department_id,
        },
        "message": "資料夾更新成功",
    }


@router.delete("/folders/{folder_id}")
def delete_folder(
    folder_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    """刪除資料夾（管理員限定），有子資料夾或文件時不可刪"""

    folder = folder_service.get_folder_by_id(db, folder_id)
    if not folder:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="資料夾不存在",
        )

    has_children = (
        db.query(KnowledgeFolder)
        .filter(KnowledgeFolder.parent_id == folder_id)
        .first()
    )
    if has_children:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="資料夾下有子資料夾，無法刪除",
        )

    has_documents = (
        db.query(KnowledgeDocument)
        .filter(
            KnowledgeDocument.folder_id == folder_id,
            KnowledgeDocument.is_deleted == False,
        )
        .first()
    )
    if has_documents:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="資料夾下有文件，無法刪除",
        )

    folder_service.delete_folder(db, folder)

    return {
        "success": True,
        "message": "資料夾已刪除",
    }
