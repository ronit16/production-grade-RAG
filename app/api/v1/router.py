"""Aggregate all v1 endpoint routers into a single APIRouter."""
from fastapi import APIRouter

from app.api.v1.endpoints import documents, health, query, sessions

router = APIRouter(prefix="/v1")

router.include_router(health.router)
router.include_router(documents.router)
router.include_router(sessions.router)
router.include_router(query.router)
