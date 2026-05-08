"""
Production RAG System - Core Configuration
All settings loaded from environment variables with Pydantic validation.
"""
from enum import Enum
from functools import lru_cache
from typing import Optional
from pydantic import AnyUrl, Field, field_validator
from pydantic_settings import BaseSettings


class EmbeddingModel(str, Enum):
    OPENAI_LARGE   = "text-embedding-3-large"   # 1536-dim
    OPENAI_SMALL   = "text-embedding-3-small"   # 1536-dim
    BGE_M3         = "BAAI/bge-m3"              # 1024-dim (open-source)


class LLMProvider(str, Enum):
    OPENAI  = "openai/gpt-4o"
    GEMINI  = "gemini/gemini-1.5-pro"


class Settings(BaseSettings):
    # ── App ────────────────────────────────────────────────────────────────
    APP_NAME: str            = "ProductionRAG"
    APP_ENV: str             = "production"   # development | staging | production
    DEBUG: bool              = False
    SECRET_KEY: str          = Field(..., min_length=32)
    ALLOWED_ORIGINS: list[str] = ["https://yourdomain.com"]

    # ── Database ───────────────────────────────────────────────────────────
    DATABASE_URL: str        = Field(...)      # postgres://user:pass@host/db
    DATABASE_POOL_SIZE: int  = 20
    DATABASE_MAX_OVERFLOW: int = 40
    DB_ECHO_SQL: bool        = False

    # ── Redis ──────────────────────────────────────────────────────────────
    REDIS_URL: str           = "redis://localhost:6379/0"
    SESSION_TTL_SECONDS: int = 3600           # 1 hour idle expiry
    CACHE_TTL_SECONDS: int   = 300            # 5 min semantic cache

    # ── Object Storage ─────────────────────────────────────────────────────
    # ── Object Storage (MinIO — S3-compatible, self-hosted) ────────────────────
    S3_BUCKET: str           = "rag-documents"
    S3_PREFIX: str           = "rag-documents"
    MINIO_ENDPOINT: str      = "http://localhost:9000"
    MINIO_ACCESS_KEY: str    = Field(...)
    MINIO_SECRET_KEY: str    = Field(...)

    # ── Qdrant (vector DB — dense + sparse + hybrid fusion) ───────────────────
    QDRANT_URL: str          = "http://localhost:6333"
    QDRANT_API_KEY: Optional[str] = None       # required for Qdrant Cloud
    QDRANT_COLLECTION: str   = "rag_chunks"
    QDRANT_DENSE_DIM: int    = 1536            # must match EMBEDDING_MODEL dims
    QDRANT_SPARSE_MODEL: str = "Qdrant/bm25"  # fastembed BM25 sparse model

    # ── Embedding ──────────────────────────────────────────────────────────
    EMBEDDING_MODEL: EmbeddingModel = EmbeddingModel.OPENAI_LARGE
    EMBEDDING_BATCH_SIZE: int = 256
    EMBEDDING_CACHE_ENABLED: bool = True

    # ── LLM ───────────────────────────────────────────────────────────────
    OPENAI_API_KEY: str      = Field(...)
    GEMINI_API_KEY: str      = Field(...)
    PRIMARY_LLM: LLMProvider  = LLMProvider.OPENAI
    FALLBACK_LLM: LLMProvider = LLMProvider.GEMINI
    LLM_TIMEOUT_SECONDS: int = 30
    MAX_TOKENS: int          = 2048

    # ── Retrieval ──────────────────────────────────────────────────────────
    RETRIEVAL_TOP_K: int     = 20       # candidates fetched per vector type (pre-rerank)
    RERANK_TOP_K: int        = 5        # final chunks sent to LLM after rerank
    HYBRID_ALPHA: float      = 0.7      # reserved — Qdrant uses equal-weight RRF natively
    CHUNK_SIZE: int          = 512      # tokens per chunk
    CHUNK_OVERLAP: int       = 50       # token overlap

    # ── Celery (async workers) ─────────────────────────────────────────────
    CELERY_BROKER_URL: str   = "amqp://guest:guest@localhost:5672//"
    CELERY_RESULT_BACKEND: str = "redis://localhost:6379/1"
    INGEST_CONCURRENCY: int  = 8

    # ── Auth ───────────────────────────────────────────────────────────────
    JWT_ALGORITHM: str       = "RS256"
    JWT_PRIVATE_KEY_PATH: str = "/secrets/jwt_private.pem"
    JWT_PUBLIC_KEY_PATH: str  = "/secrets/jwt_public.pem"
    ACCESS_TOKEN_EXPIRE_MINUTES: int  = 15
    REFRESH_TOKEN_EXPIRE_DAYS: int    = 7

    # ── Rate limiting ──────────────────────────────────────────────────────
    DEFAULT_RATE_LIMIT_RPS: int = 10     # requests per second per tenant
    DEFAULT_DAILY_TOKEN_LIMIT: int = 500_000

    # ── Observability ──────────────────────────────────────────────────────
    OTEL_ENDPOINT: str       = "http://jaeger:4318"
    LOG_LEVEL: str           = "INFO"
    SENTRY_DSN: Optional[str] = None

    @field_validator("APP_ENV")
    @classmethod
    def validate_env(cls, v: str) -> str:
        allowed = {"development", "staging", "production"}
        if v not in allowed:
            raise ValueError(f"APP_ENV must be one of {allowed}")
        return v

    class Config:
        env_file = ".env"
        case_sensitive = True


@lru_cache
def get_settings() -> Settings:
    """Cached settings singleton — loaded once at startup."""
    return Settings()
