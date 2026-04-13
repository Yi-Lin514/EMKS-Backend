from openai import OpenAI
from app.config import settings

client = OpenAI(api_key=settings.OPENAI_API_KEY)


def chunk_text(text: str, chunk_size: int = settings.CHUNK_SIZE, overlap: int = settings.CHUNK_OVERLAP) -> list[str]:
    """長文本切塊，每個切塊的長度為 chunk_size，切塊之間有 overlap 的重疊部分"""
    chunks = []
    start = 0
    while start < len(text):
        end = start + chunk_size
        chunk = text[start:end]
        if chunk.strip():
            chunks.append(chunk.strip())
        start = end - overlap
    return chunks


def get_embeddings_batch(texts: list[str]) -> list[list[float]]:
    """取得一批文本的嵌入向量"""
    response = client.embeddings.create(
        input=texts,
        model=settings.EMBEDDING_MODEL,
    )
    return [item.embedding for item in response.data]


def get_embedding(text: str) -> list[float]:
    """取得單一文本的嵌入向量"""
    return get_embeddings_batch([text])[0]


def extract_text_from_file(file_path: str, file_type: str) -> str:
    """從文件中提取文本內容，支持 txt 和 pdf 格式"""
    if file_type == "txt":
        with open(file_path, "r", encoding="utf-8") as f:
            return f.read()

    if file_type == "pdf":
        import fitz
        doc = fitz.open(file_path)
        text = ""
        for page in doc:
            text += page.get_text()
        doc.close()
        return text

    raise ValueError(f"Unsupported file type: {file_type}")
