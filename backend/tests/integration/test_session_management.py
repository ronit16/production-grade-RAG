"""Integration tests: session creation, retrieval, and lifecycle."""
import time
import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.services.session import SessionManager, SessionState, Message


class TestSessionManagement:
    @pytest.mark.asyncio
    async def test_session_created_with_unique_id(self):
        mock_redis = AsyncMock()
        mock_redis.setex = AsyncMock()
        mock_db    = AsyncMock()
        mock_db.add   = MagicMock()
        mock_db.flush = AsyncMock()

        sm = SessionManager(redis=mock_redis, db=mock_db)
        tenant_id = str(uuid.uuid4())
        state1    = await sm.create_session(tenant_id=tenant_id)
        state2    = await sm.create_session(tenant_id=tenant_id)
        assert state1.session_id != state2.session_id

    @pytest.mark.asyncio
    async def test_session_get_returns_none_for_unknown(self):
        mock_redis = AsyncMock()
        mock_redis.get = AsyncMock(return_value=None)

        mock_result = AsyncMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_db = AsyncMock()
        mock_db.execute = AsyncMock(return_value=mock_result)

        sm        = SessionManager(redis=mock_redis, db=mock_db)
        result    = await sm.get_session(str(uuid.uuid4()), str(uuid.uuid4()))
        assert result is None

    @pytest.mark.asyncio
    async def test_close_session_marks_redis_and_db(self):
        mock_redis = AsyncMock()
        mock_redis.delete = AsyncMock()
        mock_db    = AsyncMock()
        mock_db.execute = AsyncMock()
        mock_db.commit  = AsyncMock()

        sm    = SessionManager(redis=mock_redis, db=mock_db)
        state = SessionState(
            session_id=str(uuid.uuid4()),
            tenant_id=str(uuid.uuid4()),
            user_id=None,
            messages=[],
            created_at=time.time(),
            last_active=time.time(),
        )
        await sm.close_session(state)
        mock_redis.delete.assert_called_once()
        mock_db.commit.assert_called_once()
