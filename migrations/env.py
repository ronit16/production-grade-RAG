"""Alembic environment — async-aware, reads DATABASE_URL from app settings."""
import asyncio
from logging.config import fileConfig

from sqlalchemy.ext.asyncio import create_async_engine

from alembic import context

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# Import all models so Alembic can detect schema changes via autogenerate.
from app.models.db import Base  # noqa: E402
target_metadata = Base.metadata


def _get_url() -> str:
    """Read DATABASE_URL from app settings (overrides the blank alembic.ini value)."""
    from app.core.config import get_settings
    return get_settings().DATABASE_URL


def run_migrations_offline() -> None:
    """Generate SQL without a live DB connection (used for --sql flag)."""
    context.configure(
        url=_get_url(),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection) -> None:
    context.configure(
        connection=connection,
        target_metadata=target_metadata,
        compare_type=True,
    )
    with context.begin_transaction():
        context.run_migrations()


async def run_migrations_online() -> None:
    """Run migrations using a live async connection."""
    connectable = create_async_engine(_get_url())
    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)
    await connectable.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    asyncio.run(run_migrations_online())
