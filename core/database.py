import redis.asyncio as aioredis
from typing import AsyncGenerator
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.orm import declarative_base
import chromadb

from core.config import settings

# SQLAlchemy setup (PostgreSQL)
engine = create_async_engine(settings.POSTGRES_URL, echo=False)
async_session_maker = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
Base = declarative_base()

async def get_db() -> AsyncGenerator[AsyncSession, None]:
    async with async_session_maker() as session:
        yield session

# Redis setup
redis_client = aioredis.from_url(settings.REDIS_URL, decode_responses=True)

# ChromaDB setup
chroma_client = chromadb.PersistentClient(path=settings.CHROMA_PERSIST_DIR)

# Note: We configure the specific langchain-chroma vectorstore inside rag_service.py or document_processor
