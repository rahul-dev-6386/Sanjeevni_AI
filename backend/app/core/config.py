import os
from pydantic_settings import BaseSettings
from typing import Optional


class Settings(BaseSettings):
    DATABASE_URL: str = "postgresql://postgres:postgres@localhost:5432/health_assistant"
    JWT_SECRET: str = "change-this-secret-in-production"
    JWT_ALGORITHM: str = "HS256"
    JWT_EXPIRATION_MINUTES: int = 60
    JWT_REFRESH_EXPIRATION_DAYS: int = 7
    GOOGLE_CLIENT_ID: Optional[str] = None
    GOOGLE_CLIENT_SECRET: Optional[str] = None
    OPENROUTER_API_KEY: Optional[str] = None
    OPENROUTER_MODELS: str = "openrouter/free,google/gemma-4-31b-it:free,nvidia/nemotron-3-ultra-550b-a55b:free,inclusionai/ling-3.0-flash:free"
    RAG_FORMATTING_MODELS: str = "openrouter/free,google/gemma-4-31b-it:free,nvidia/nemotron-3-ultra-550b-a55b:free,inclusionai/ling-3.0-flash:free"
    GEMINI_API_KEY: Optional[str] = None
    STORAGE_BACKEND: str = "local"
    UPLOAD_DIR: str = "./uploads"
    AWS_ACCESS_KEY_ID: Optional[str] = None
    AWS_SECRET_ACCESS_KEY: Optional[str] = None
    AWS_S3_BUCKET: Optional[str] = None
    AWS_REGION: Optional[str] = None

    QDRANT_URL: Optional[str] = "http://localhost:6333"
    QDRANT_API_KEY: Optional[str] = None
    QDRANT_COLLECTION: str = "medical_knowledge"
    EMBEDDING_PROVIDER: str = "openrouter"
    EMBEDDING_MODEL: str = "nvidia/llama-nemotron-embed-vl-1b-v2:free"
    EMBEDDING_DIMENSION: int = 2048

    REDIS_URL: str = "redis://localhost:6379/0"
    CHUNK_SIZE: int = 500
    CHUNK_OVERLAP: int = 100
    MAX_EMBEDDING_BATCH: int = 10
    GUIDELINES_DIR: str = "./data/medical_guidelines"
    MODELS_DIR: str = "./data/models"
    DATASETS_DIR: str = "./data/datasets"
    CACHE_DIR: str = "./data/cache"
    SARVAM_API_KEY: Optional[str] = None

    # Reranker — use Jina AI free API instead of a local model
    # Get a free key at: https://jina.ai (no credit card needed, 1M tokens/month)
    JINA_API_KEY: Optional[str] = None

    # BM25 keyword search — disable on memory-constrained hosts (e.g. Render free).
    # When "1", keyword search returns nothing and retrieval is vector-only,
    # avoiding the ~300MB spike from building the in-memory BM25 index.
    DISABLE_BM25: str = "0"

    # CORS
    CORS_ORIGINS: str = "http://localhost:3000,http://localhost:3001"

    # Email / SMTP
    EMAIL_USER: Optional[str] = None
    EMAIL_APP_PASSWORD: Optional[str] = None
    SMTP_HOST: str = "smtp.gmail.com"
    SMTP_PORT: int = 587
    MAIL_FROM: str = "Sanjeevni AI <noreply@sanjeevni.ai>"

    # OTP
    OTP_EXPIRY_MINUTES: int = 10
    OTP_LENGTH: int = 6
    OTP_MAX_ATTEMPTS: int = 5
    OTP_RESEND_COOLDOWN_SECONDS: int = 60

    class Config:
        env_file = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.realpath(__file__))))), ".env")
        extra = "allow"


settings = Settings()
