"""
Production RAG System - Database & Cache Connections
Provides async SQLAlchemy engine, session factory, and Redis pool.
"""
from typing import AsyncGenerator

import redis.asyncio as aioredis
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.config import get_settings

settings = get_settings()

# ── SQLAlchemy async engine ────────────────────────────────────────────────────

engine = create_async_engine(
    settings.DATABASE_URL,
    pool_size=settings.DATABASE_POOL_SIZE,
    max_overflow=settings.DATABASE_MAX_OVERFLOW,
    echo=settings.DB_ECHO_SQL,
    pool_pre_ping=True,
)

AsyncSessionFactory = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
)

# ── Redis connection pool ──────────────────────────────────────────────────────

_redis_pool: aioredis.Redis | None = None


def _get_redis_pool() -> aioredis.Redis:
    global _redis_pool
    if not _redis_pool:
        _redis_pool = aioredis.from_url(
            settings.REDIS_URL,
            decode_responses=False,  # raw bytes for pickle support
            max_connections=50,
        )
    return _redis_pool


# ── FastAPI dependency providers ───────────────────────────────────────────────

async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """Yield an async DB session; auto-rollback on exception."""
    async with AsyncSessionFactory() as session:
        try:
            yield session
        except Exception:
            await session.rollback()
            raise


async def get_redis() -> aioredis.Redis:
    """Return the shared Redis connection pool."""
    return _get_redis_pool()


# ── Startup initialisation ─────────────────────────────────────────────────────

async def init_db() -> None:
    """Create all tables on startup (idempotent)."""
    from app.models.db import Base  # import here to avoid circular deps
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
