"""Pydantic schemas for session management endpoints."""
from typing import Optional
from pydantic import BaseModel


class SessionCreateResponse(BaseModel):
    session_id: str
    created_at: float


class SessionListItem(BaseModel):
    session_id: str
    title: Optional[str] = None
    message_count: int
    started_at: Optional[str] = None
    last_active: Optional[str] = None


class SessionCloseResponse(BaseModel):
    closed: bool
