from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # 資料庫設定
    DB_HOST: str = "localhost"
    DB_PORT: int = 3306
    DB_USER: str = "root"
    DB_PASSWORD: str = ""
    DB_NAME: str = "AI_G2_DB"

    # JWT 設定
    JWT_SECRET_KEY: str = "your-secret-key"
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30
    REFRESH_TOKEN_EXPIRE_DAYS: int = 7

    # Email 設定
    EMAIL_MODE: str = "console"  # console 或 smtp
    SMTP_HOST: str = "smtp.gmail.com"
    SMTP_PORT: int = 587
    SMTP_USER: str = ""
    SMTP_PASSWORD: str = ""
    EMAIL_FROM: str = ""
    EMAIL_FROM_NAME: str = "知識管理系統"

    # OpenAI 設定
    OPENAI_API_KEY: str = ""
    LLM_MODEL: str = "gpt-4o-mini"
    LLM_TEMPERATURE: float = 0
    LLM_MAX_TOKENS: int = 1024
    EMBEDDING_MODEL: str = "text-embedding-3-small"

    # RAG 設定
    CHUNK_SIZE: int = 500
    CHUNK_OVERLAP: int = 50
    RAG_SEARCH_RESULTS: int = 5
    RAG_RELEVANCE_THRESHOLD: float = 0.2

    # 檔案上傳設定
    UPLOAD_DIR: str = "uploads/knowledge"
    ALLOWED_EXTENSIONS: str = "txt,pdf"

    # 重設密碼設定
    PASSWORD_RESET_EXPIRE_HOURS: int = 1
    FRONTEND_URL: str = "http://localhost:5173"

    @property
    def DATABASE_URL(self) -> str:
        return f"mysql+pymysql://{self.DB_USER}:{self.DB_PASSWORD}@{self.DB_HOST}:{self.DB_PORT}/{self.DB_NAME}"

    class Config:
        env_file = ".env"


settings = Settings()
