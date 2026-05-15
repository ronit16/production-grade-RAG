"""Session lifecycle endpoints (create, list, delete)."""
import uuid

from fastapi import APIRouter, HTTPException, Query, status

from app.api.deps import DBSession, RedisClient
from app.middleware.auth import AuthedContext, RatedContext
from app.schemas.session import SessionCloseResponse, SessionCreateResponse, SessionListItem
from app.services.session import SessionManager

router = APIRouter(prefix="/sessions", tags=["sessions"])


@router.post("", status_code=status.HTTP_201_CREATED, response_model=SessionCreateResponse)
async def create_session(
    ctx:   RatedContext,
    db:    DBSession,
    redis: RedisClient,
):
    """Create a new conversation session."""
    sm    = SessionManager(redis, db)
    state = await sm.create_session(
        tenant_id=str(ctx.tenant_id),
        user_id=str(ctx.user_id) if ctx.user_id else None,
    )
    return SessionCreateResponse(session_id=state.session_id, created_at=state.created_at)


@router.get("", response_model=list[SessionListItem])
async def list_sessions(
    ctx:    AuthedContext,
    db:     DBSession,
    redis:  RedisClient,
    limit:  int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
):
    """List active sessions for the authenticated tenant/user."""
    sm = SessionManager(redis, db)
    rows = await sm.list_sessions(
        tenant_id=str(ctx.tenant_id),
        user_id=str(ctx.user_id) if ctx.user_id else None,
        limit=limit,
        offset=offset,
    )
    return [SessionListItem(**r) for r in rows]


@router.delete("/{session_id}", response_model=SessionCloseResponse)
async def close_session(
    session_id: uuid.UUID,
    ctx:        AuthedContext,
    db:         DBSession,
    redis:      RedisClient,
):
    """Close and archive a conversation session."""
    sm    = SessionManager(redis, db)
    state = await sm.get_session(str(session_id), str(ctx.tenant_id))
    if not state:
        raise HTTPException(status_code=404, detail="Session not found")
    await sm.close_session(state)
    return SessionCloseResponse(closed=True)
