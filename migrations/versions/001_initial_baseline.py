"""Initial baseline — schema created by SQLAlchemy create_all on first deploy.

This revision is a no-op migration. The full schema (tenants, users, documents,
chunks, sessions, queries, usage_logs, api_keys) is created by
`Base.metadata.create_all()` in app/core/database.py during startup.

Alembic stamps the DB at this revision on first run so that subsequent
migrations (op.add_column, op.create_table, etc.) can be tracked cleanly.

Revision ID: 001
Revises:
Create Date: 2025-01-01 00:00:00.000000
"""
from typing import Sequence, Union

revision: str = "001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Schema is managed by SQLAlchemy metadata.create_all() for this baseline.
    # All subsequent schema changes must use alembic op.* operations so they
    # are tracked and reversible.
    pass


def downgrade() -> None:
    pass
