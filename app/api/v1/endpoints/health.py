"""Health and readiness probe endpoints."""
from fastapi import APIRouter, HTTPException

from app.api.deps import DBSession, RedisClient

router = APIRouter(tags=["ops"])


@router.get("/health")
async def health():
    return {"status": "ok", "version": "1.0.0"}


@router.get("/ready")
async def ready(db: DBSession, redis: RedisClient):
    """Readiness probe — checked by k8s before routing traffic."""
    try:
        await db.execute("SELECT 1")
        await redis.ping()
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"Not ready: {exc}")
    return {"status": "ready"}
