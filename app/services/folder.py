from sqlalchemy.orm import Session, joinedload

from app.models.knowledge import KnowledgeFolder


def create_folder(
    db: Session,
    name: str,
    created_by: int,
    parent_id: int | None = None,
    department_id: int | None = None,
) -> KnowledgeFolder:
    """創建知識文件夾"""

    folder = KnowledgeFolder(
        name=name,
        parent_id=parent_id,
        department_id=department_id,
        created_by=created_by,
    )
    db.add(folder)
    db.commit()
    db.refresh(folder)
    return folder


def get_folder_tree(db: Session) -> list[KnowledgeFolder]:
    """獲取知識文件夾樹"""

    return (
        db.query(KnowledgeFolder)
        .options(joinedload(KnowledgeFolder.department))
        .order_by(KnowledgeFolder.name)
        .all()
    )


def build_tree(folders: list[KnowledgeFolder]) -> list[dict]:
    """構建知識文件夾樹"""

    folder_map = {}
    for f in folders:
        folder_map[f.id] = {
            "id": f.id,
            "name": f.name,
            "parent_id": f.parent_id,
            "department_id": f.department_id,
            "department_name": f.department.name if f.department else None,
            "children": [],
        }

    roots = []
    for f in folders:
        node = folder_map[f.id]
        if f.parent_id and f.parent_id in folder_map:
            folder_map[f.parent_id]["children"].append(node)
        else:
            roots.append(node)

    return roots


def get_folder_by_id(db: Session, folder_id: int) -> KnowledgeFolder | None:
    """獲取知識文件夾詳情"""

    return db.query(KnowledgeFolder).filter(KnowledgeFolder.id == folder_id).first()


def update_folder(
    db: Session,
    folder: KnowledgeFolder,
    name: str | None = None,
    parent_id: int | None = ...,
    department_id: int | None = ...,
) -> KnowledgeFolder:
    """更新知識文件夾信息"""

    if name is not None:
        folder.name = name
    if parent_id is not ...:
        folder.parent_id = parent_id
    if department_id is not ...:
        folder.department_id = department_id

    db.commit()
    db.refresh(folder)
    return folder


def delete_folder(db: Session, folder: KnowledgeFolder) -> None:
    """刪除知識文件夾"""

    db.delete(folder)
    db.commit()
