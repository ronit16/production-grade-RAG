import os
from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    # Application variables
    PROJECT_NAME: str = "Production Grade RAG System"
    VERSION: str = "1.0.0"

    # API Keys
    GEMINI_API_KEY: str = ""

    # Database connections
    POSTGRES_URL: str = "postgresql+asyncpg://user:password@localhost:5432/rag_db"
    REDIS_URL: str = "redis://localhost:6379/0"
    
    # Chroma DB paths
    CHROMA_PERSIST_DIR: str = "./chroma_data"
    
    # RAG Settings
    CHUNK_SIZE: int = 800
    CHUNK_OVERLAP: int = 120
    TOP_K: int = 3

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

settings = Settings()
