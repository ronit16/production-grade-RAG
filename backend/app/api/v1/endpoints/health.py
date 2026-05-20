"""Health and readiness probe endpoints."""
import asyncio
import time
from urllib.parse import urlparse

import boto3
from fastapi import APIRouter, HTTPException
from fastapi.responses import JSONResponse
from sqlalchemy import text

from app.api.deps import DBSession, RedisClient
from app.core.config import get_settings

router = APIRouter(tags=["ops"])
settings = get_settings()


@router.get("/health")
async def health():
    return {"status": "ok", "version": "1.0.0"}


@router.get("/ready")
async def ready(db: DBSession, redis: RedisClient):
    """Readiness probe — checked by k8s before routing traffic."""
    try:
        await db.execute(text("SELECT 1"))
        await redis.ping()
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"Not ready: {exc}")
    return {"status": "ready"}


@router.get("/health/detailed")
async def health_detailed(db: DBSession, redis: RedisClient):
    """Deep health check for all 5 backing services with per-check latency."""
    checks: dict[str, dict] = {}

    # PostgreSQL
    t0 = time.monotonic()
    try:
        await db.execute(text("SELECT 1"))
        checks["postgres"] = {"status": "ok", "latency_ms": round((time.monotonic() - t0) * 1000)}
    except Exception as exc:
        checks["postgres"] = {"status": f"error: {exc}", "latency_ms": None}

    # Redis
    t0 = time.monotonic()
    try:
        await redis.ping()
        checks["redis"] = {"status": "ok", "latency_ms": round((time.monotonic() - t0) * 1000)}
    except Exception as exc:
        checks["redis"] = {"status": f"error: {exc}", "latency_ms": None}

    # RabbitMQ — TCP probe (avoids heavy amqp dependency)
    t0 = time.monotonic()
    try:
        parsed = urlparse(settings.CELERY_BROKER_URL)
        host = parsed.hostname or "rabbitmq"
        port = parsed.port or 5672
        _, writer = await asyncio.wait_for(
            asyncio.open_connection(host, port), timeout=2.0
        )
        writer.close()
        await writer.wait_closed()
        checks["rabbitmq"] = {"status": "ok", "latency_ms": round((time.monotonic() - t0) * 1000)}
    except Exception as exc:
        checks["rabbitmq"] = {"status": f"error: {exc}", "latency_ms": None}

    # Qdrant
    t0 = time.monotonic()
    try:
        from app.services.retriever import _get_qdrant
        await asyncio.wait_for(_get_qdrant().get_collections(), timeout=2.0)
        checks["qdrant"] = {"status": "ok", "latency_ms": round((time.monotonic() - t0) * 1000)}
    except Exception as exc:
        checks["qdrant"] = {"status": f"error: {exc}", "latency_ms": None}

    # MinIO — head_bucket via executor (boto3 is sync)
    t0 = time.monotonic()
    try:
        s3 = boto3.client(
            "s3",
            endpoint_url=settings.MINIO_ENDPOINT,
            aws_access_key_id=settings.MINIO_ACCESS_KEY,
            aws_secret_access_key=settings.MINIO_SECRET_KEY,
        )
        loop = asyncio.get_event_loop()
        await asyncio.wait_for(
            loop.run_in_executor(None, lambda: s3.head_bucket(Bucket=settings.S3_BUCKET)),
            timeout=2.0,
        )
        checks["minio"] = {"status": "ok", "latency_ms": round((time.monotonic() - t0) * 1000)}
    except Exception as exc:
        checks["minio"] = {"status": f"error: {exc}", "latency_ms": None}

    # Aggregate: unhealthy if postgres or redis are down, degraded if others fail
    critical_down = any(
        checks[svc]["status"] != "ok" for svc in ("postgres", "redis")
    )
    any_down = any(v["status"] != "ok" for v in checks.values())

    if critical_down:
        overall = "unhealthy"
        status_code = 503
    elif any_down:
        overall = "degraded"
        status_code = 200
    else:
        overall = "healthy"
        status_code = 200

    return JSONResponse(
        {"status": overall, "checks": checks, "version": "1.0.0"},
        status_code=status_code,
    )
