"""
Production RAG System - Database & Cache Connections
Provides async SQLAlchemy engine, session factory, and Redis pool.
"""
from typing import AsyncGenerator

import redis.asyncio as aioredis
from sqlalchemy import text
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
    """Create tables idempotently, then ensure Alembic version tracking is live."""
    from app.models.db import Base
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    await _ensure_alembic_stamped()


async def _ensure_alembic_stamped() -> None:
    """Stamp the DB at Alembic 'head' on first run.

    Bridges the gap between create_all() (which creates tables but doesn't
    touch alembic_version) and future incremental Alembic migrations.
    Idempotent: does nothing if the DB is already stamped.
    """
    from pathlib import Path
    import asyncio
    from sqlalchemy import text

    async with engine.connect() as conn:
        try:
            row = await conn.execute(
                text("SELECT version_num FROM alembic_version LIMIT 1")
            )
            if row.fetchone():
                return  # already stamped — nothing to do
        except Exception:
            pass  # alembic_version table not yet created; fall through to stamp

    from alembic.config import Config
    from alembic import command as alembic_command

    alembic_ini = Path(__file__).parents[2] / "alembic.ini"

    def _stamp() -> None:
        cfg = Config(str(alembic_ini))
        alembic_command.stamp(cfg, "head")

    await asyncio.get_event_loop().run_in_executor(None, _stamp)