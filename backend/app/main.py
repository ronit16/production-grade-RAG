"""
Production RAG System - Application Factory
Wires up middleware, lifespan, and all versioned routers.
"""
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.v1.router import router as v1_router
from app.core.config import get_settings
from app.core.database import init_db
from app.services.retriever import ensure_collection

settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Run DB migrations and Qdrant collection setup on startup."""
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

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(v1_router)
