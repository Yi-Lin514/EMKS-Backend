import os

import chromadb

COLLECTION_NAME = "knowledge_chunks"

CHROMA_HOST = os.getenv("CHROMA_HOST", "")

if CHROMA_HOST:
    chroma_client = chromadb.HttpClient(host=CHROMA_HOST, port=8000)
else:
    chroma_client = chromadb.PersistentClient(path="chroma_data")


def get_collection() -> chromadb.Collection:
    """取得或建立向量儲存集合"""
    return chroma_client.get_or_create_collection(
        name=COLLECTION_NAME,
        metadata={"hnsw:space": "cosine"},
    )


def add_chunks(
    document_id: int,
    chunks: list[str],
    embeddings: list[list[float]],
    metadata: dict,
) -> int:
    """ 將文本片段及其向量資料加入集合中，並附帶相關的元資料 """
    collection = get_collection()

    ids = [f"doc{document_id}_chunk{i}" for i in range(len(chunks))]

    metadatas = [
        {
            "document_id": document_id,
            "document_title": metadata["document_title"],
            "chunk_index": i,
            "permission_level": metadata["permission_level"],
            "department_id": metadata.get("department_id") or 0,
        }
        for i in range(len(chunks))
    ]

    collection.add(
        ids=ids,
        documents=chunks,
        embeddings=embeddings,
        metadatas=metadatas,
    )

    return len(chunks)


def search_chunks(
    query_embedding: list[float],
    n_results: int = 5,
    where: dict | None = None,
) -> dict:
    """ 根據查詢向量搜尋相關的文本片段，並可選擇性地根據條件過濾結果 """
    collection = get_collection()

    params = {
        "query_embeddings": [query_embedding],
        "n_results": n_results,
    }
    if where:
        params["where"] = where

    return collection.query(**params)


def delete_document_chunks(document_id: int) -> None:
    """ 刪除指定文件的所有向量資料 """
    collection = get_collection()

    results = collection.get(
        where={"document_id": document_id},
    )

    if results["ids"]:
        collection.delete(ids=results["ids"])
