"""
Production RAG System - Celery Application Factory
Shared Celery instance imported by workers and the FastAPI app (for .delay() calls).
"""
from celery import Celery
from app.core.config import get_settings

settings = get_settings()

celery_app = Celery(
    "rag_ingest",
    broker=settings.CELERY_BROKER_URL,
    backend=settings.CELERY_RESULT_BACKEND,
    include=["app.workers.ingestion"],
)

celery_app.conf.update(
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    task_acks_late=True,           # ack only after successful completion
    task_reject_on_worker_lost=True,
    worker_prefetch_multiplier=1,  # one task at a time per worker
    task_track_started=True,
)
