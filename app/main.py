"""
Production RAG System - Application Factory
Wires up middleware, lifespan, and all versioned routers.
"""
import logging
import logging.config
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from prometheus_fastapi_instrumentator import Instrumentator

from app.api.v1.router import router as v1_router
from app.core.config import get_settings
from app.core.database import init_db
from app.services.retriever import ensure_collection

settings = get_settings()


def _configure_logging(level: str) -> None:
    """Wire LOG_LEVEL into Python's logging system with structured JSON output."""
    logging.config.dictConfig({
        "version": 1,
        "disable_existing_loggers": False,
        "formatters": {
            "json": {
                "()": "pythonjsonlogger.jsonlogger.JsonFormatter",
                "format": "%(asctime)s %(name)s %(levelname)s %(message)s %(pathname)s %(lineno)d",
            },
        },
        "handlers": {
            "console": {
                "class": "logging.StreamHandler",
                "formatter": "json",
                "stream": "ext://sys.stdout",
            },
        },
        "root": {
            "handlers": ["console"],
            "level": level,
        },
        "loggers": {
            "uvicorn.error": {"propagate": True},
            "uvicorn.access": {"propagate": True},
            "sqlalchemy.engine": {"level": "WARNING", "propagate": True},
        },
    })


_configure_logging(settings.LOG_LEVEL)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Run DB migrations/create_all and Qdrant collection setup on startup."""
    await init_db()
    await ensure_collection()
    yield


app = FastAPI(
    title="Production RAG API",
    version="1.0.0",
    docs_url="/docs" if settings.APP_ENV != "production" else None,
    redoc_url=None,
    lifespan=lifespan,
)

# Prometheus /metrics — must be instrumented before routes are added
Instrumentator(
    should_group_status_codes=True,
    should_ignore_untemplated=True,
    should_group_untemplated=True,
    excluded_handlers=["/metrics", "/health", "/ready"],
).instrument(app).expose(app, endpoint="/metrics", include_in_schema=False)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=settings.ALLOWED_METHODS,
    allow_headers=settings.ALLOWED_HEADERS,
)

app.include_router(v1_router)
