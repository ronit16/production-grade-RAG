"""
Production RAG System - Session Manager
Redis-backed multi-turn conversation state with PostgreSQL persistence.
"""
import json
import time
import uuid
from dataclasses import asdict, dataclass
from typing import Optional
from uuid import UUID

import redis.asyncio as aioredis
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update, func

from app.core.config import get_settings
from app.models.db import Session as DBSession, Query

settings = get_settings()

# Max messages to keep in active context (rolling window)
MAX_HISTORY_MESSAGES = 20
# Max token budget for history in the prompt
MAX_HISTORY_TOKENS   = 2000


@dataclass
class Message:
    role:       str         # "user" | "assistant"
    content:    str
    ts:         float       = 0.0
    tokens_in:  int         = 0
    tokens_out: int         = 0
    sources:    list        = None   # list of source dicts (assistant only)
    query_id:   str         = ""

    def __post_init__(self):
        if self.ts == 0.0:
            self.ts = time.time()
        if self.sources is None:
            self.sources = []


@dataclass
class SessionState:
    session_id:  str
    tenant_id:   str
    user_id:     Optional[str]
    messages:    list[Message]
    created_at:  float
    last_active: float
    total_tokens_in:  int = 0
    total_tokens_out: int = 0

    def add_message(self, msg: Message) -> None:
        self.messages.append(msg)
        self.last_active = time.time()
        if msg.role == "user":
            self.total_tokens_in += msg.tokens_in
        else:
            self.total_tokens_out += msg.tokens_out
        # Rolling window — drop oldest beyond limit
        if len(self.messages) > MAX_HISTORY_MESSAGES:
            self.messages = self.messages[-MAX_HISTORY_MESSAGES:]

    def get_history_for_prompt(self) -> list[dict]:
        """Return messages formatted for OpenAI/Claude chat API."""
        history = []
        budget  = MAX_HISTORY_TOKENS
        # Iterate backwards and include until token budget exhausted
        for msg in reversed(self.messages[:-1]):  # exclude latest (the current question)
            approx_tokens = len(msg.content) // 4
            if budget - approx_tokens < 0:
                break
            budget -= approx_tokens
            history.insert(0, {"role": msg.role, "content": msg.content})
        return history


class SessionManager:
    """
    Manages session lifecycle.
    Hot state lives in Redis; cold state persisted to PostgreSQL.
    """

    def __init__(self, redis: aioredis.Redis, db: AsyncSession):
        self._redis = redis
        self._db    = db

    def _redis_key(self, session_id: str, tenant_id: str) -> str:
        """Namespaced Redis key prevents cross-tenant collision."""
        return f"rag:session:{tenant_id}:{session_id}"

    async def create_session(
        self,
        tenant_id: str,
        user_id: Optional[str] = None,
    ) -> SessionState:
        """Create a new session and persist it to DB."""
        sid  = str(uuid.uuid4())
        now  = time.time()
        state = SessionState(
            session_id=sid,
            tenant_id=str(tenant_id),
            user_id=str(user_id) if user_id else None,
            messages=[],
            created_at=now,
            last_active=now,
        )

        # Persist skeleton to PostgreSQL
        db_session = DBSession(
            id=UUID(sid),
            tenant_id=UUID(tenant_id),
            user_id=UUID(user_id) if user_id else None,
        )
        self._db.add(db_session)
        await self._db.flush()
        await self._db.commit()

        # Store hot state in Redis
        await self._save_to_redis(state)
        return state

    async def get_session(
        self,
        session_id: str,
        tenant_id: str,
    ) -> Optional[SessionState]:
        """Load session from Redis (fast path) or PostgreSQL (cold)."""
        key    = self._redis_key(session_id, tenant_id)
        cached = await self._redis.get(key)

        if cached:
            data  = json.loads(cached)
            msgs  = [Message(**m) for m in data.pop("messages")]
            state = SessionState(messages=msgs, **data)
            return state

        # Cold path: rebuild from DB queries
        return await self._load_from_db(session_id, tenant_id)

    async def add_message(
        self,
        state: SessionState,
        message: Message,
    ) -> None:
        """Add a message to the session and refresh Redis TTL."""
        state.add_message(message)
        await self._save_to_redis(state)

        # Async persist to DB (don't block the hot path)
        await self._persist_message(state.session_id, message)

    async def close_session(self, state: SessionState) -> None:
        """Mark session as ended in DB. Clean up Redis."""
        key = self._redis_key(state.session_id, state.tenant_id)
        await self._redis.delete(key)

        await self._db.execute(
            update(DBSession)
            .where(DBSession.id == UUID(state.session_id))
            .values(
                is_active=False,
                ended_at=func.now(),
                message_count=len(state.messages),
                token_count_in=state.total_tokens_in,
                token_count_out=state.total_tokens_out,
            )
        )
        await self._db.commit()

    async def list_sessions(
        self,
        tenant_id: str,
        user_id: Optional[str] = None,
        limit: int = 20,
        offset: int = 0,
    ) -> list[dict]:
        """List sessions for a tenant (or specific user)."""
        q = (
            select(DBSession)
            .where(
                DBSession.tenant_id == UUID(tenant_id),
                DBSession.is_active == True,
            )
            .order_by(DBSession.last_active.desc())
            .limit(limit)
            .offset(offset)
        )
        if user_id:
            q = q.where(DBSession.user_id == UUID(user_id))

        result = await self._db.execute(q)
        sessions = result.scalars().all()

        return [
            {
                "session_id":    str(s.id),
                "title":         s.title,
                "message_count": s.message_count,
                "started_at":    s.started_at.isoformat() if s.started_at else None,
                "last_active":   s.last_active.isoformat() if s.last_active else None,
            }
            for s in sessions
        ]

    # ── Private helpers ────────────────────────────────────────────────────

    async def _save_to_redis(self, state: SessionState) -> None:
        key  = self._redis_key(state.session_id, state.tenant_id)
        data = {
            "session_id":       state.session_id,
            "tenant_id":        state.tenant_id,
            "user_id":          state.user_id,
            "created_at":       state.created_at,
            "last_active":      state.last_active,
            "total_tokens_in":  state.total_tokens_in,
            "total_tokens_out": state.total_tokens_out,
            "messages": [asdict(m) for m in state.messages],
        }
        await self._redis.setex(key, settings.SESSION_TTL_SECONDS, json.dumps(data))

    async def _load_from_db(
        self,
        session_id: str,
        tenant_id: str,
    ) -> Optional[SessionState]:
        """Rebuild session state from PostgreSQL query history."""
        result = await self._db.execute(
            select(DBSession).where(
                DBSession.id == UUID(session_id),
                DBSession.tenant_id == UUID(tenant_id),
            )
        )
        db_session = result.scalar_one_or_none()
        if not db_session:
            return None

        # Load queries for this session
        q_result = await self._db.execute(
            select(Query)
            .where(Query.session_id == UUID(session_id))
            .order_by(Query.created_at)
            .limit(MAX_HISTORY_MESSAGES)
        )
        queries = q_result.scalars().all()

        messages: list[Message] = []
        for q in queries:
            messages.append(Message(role="user",      content=q.question, ts=q.created_at.timestamp()))
            if q.answer:
                messages.append(Message(role="assistant", content=q.answer, sources=q.sources or []))

        state = SessionState(
            session_id=session_id,
            tenant_id=tenant_id,
            user_id=str(db_session.user_id) if db_session.user_id else None,
            messages=messages,
            created_at=db_session.started_at.timestamp(),
            last_active=db_session.last_active.timestamp(),
            total_tokens_in=db_session.token_count_in,
            total_tokens_out=db_session.token_count_out,
        )
        # Warm up the cache
        await self._save_to_redis(state)
        return state

    async def _persist_message(self, session_id: str, msg: Message) -> None:
        """Persist a completed exchange (user + assistant pair) to queries table."""
        if msg.role != "assistant" or not msg.query_id:
            return
        # Update the existing Query row with the assistant's answer
        await self._db.execute(
            update(Query)
            .where(Query.id == UUID(msg.query_id))
            .values(answer=msg.content, sources=msg.sources)
        )
        await self._db.commit()
