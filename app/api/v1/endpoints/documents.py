"""Document upload and status polling endpoints."""
import uuid

import boto3
from fastapi import APIRouter, File, HTTPException, UploadFile, status
from sqlalchemy import func, select

from app.api.deps import DBSession, RedisClient
from app.core.config import get_settings
from app.core.exceptions import FileTooLargeError, PlanLimitError, UnsupportedMediaError
from app.middleware.auth import RatedContext, AuthedContext
from app.models.db import Document, DocumentStatus
from app.schemas.document import DocumentStatusResponse, DocumentUploadResponse
from app.workers.ingestion import process_document

settings = get_settings()

router = APIRouter(prefix="/documents", tags=["documents"])

ALLOWED_TYPES = {
    "application/pdf",
    "text/html",
    "text/markdown",
    "text/plain",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
}
MAX_FILE_SIZE_MB = 100


@router.post("", status_code=status.HTTP_202_ACCEPTED, response_model=DocumentUploadResponse)
async def ingest_document(
    ctx:   RatedContext,
    db:    DBSession,
    file:  UploadFile = File(...),
):
    """
    Upload a document for async processing.
    Returns immediately with document_id; poll /v1/documents/{id} for status.
    """
    ctx.require_role("owner", "admin", "member")

    if file.content_type not in ALLOWED_TYPES:
        raise UnsupportedMediaError(file.content_type)

    content = await file.read()
    size_mb = len(content) / (1024 * 1024)
    if size_mb > MAX_FILE_SIZE_MB:
        raise FileTooLargeError(size_mb, MAX_FILE_SIZE_MB)

    # Enforce plan document quota
    doc_count_result = await db.execute(
        select(func.count(Document.id)).where(
            Document.tenant_id == ctx.tenant_id,
            Document.deleted_at.is_(None),
        )
    )
    doc_count = doc_count_result.scalar()
    max_docs  = ctx.limits.get("max_docs")
    if max_docs and doc_count >= max_docs:
        raise PlanLimitError(f"Document limit ({max_docs}) reached for your plan")

    # Upload to MinIO
    doc_id = str(uuid.uuid4())
    s3_key = f"{settings.S3_PREFIX}/{ctx.tenant_id}/{doc_id}/{file.filename}"
    s3 = boto3.client(
        "s3",
        endpoint_url=settings.MINIO_ENDPOINT,
        aws_access_key_id=settings.MINIO_ACCESS_KEY,
        aws_secret_access_key=settings.MINIO_SECRET_KEY,
    )
    s3.put_object(Bucket=settings.S3_BUCKET, Key=s3_key, Body=content, ContentType=file.content_type)

    # Create DB record
    doc = Document(
        id=uuid.UUID(doc_id),
        tenant_id=ctx.tenant_id,
        filename=file.filename,
        content_type=file.content_type,
        file_size=len(content),
        s3_key=s3_key,
    )
    db.add(doc)
    await db.commit()

    # Dispatch async processing task
    process_document.delay(
        document_id=doc_id,
        tenant_id=str(ctx.tenant_id),
        s3_key=s3_key,
        content_type=file.content_type,
        embedding_model=settings.EMBEDDING_MODEL.value,
    )

    return DocumentUploadResponse(document_id=doc_id, status="processing", filename=file.filename)


@router.get("/{document_id}", response_model=DocumentStatusResponse)
async def get_document_status(
    document_id: str,
    ctx:         AuthedContext,
    db:          DBSession,
):
    """Poll the processing status of an uploaded document."""
    result = await db.execute(
        select(Document).where(
            Document.id == uuid.UUID(document_id),
            Document.tenant_id == ctx.tenant_id,   # tenant isolation enforced
        )
    )
    doc = result.scalar_one_or_none()
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")

    return DocumentStatusResponse(
        document_id=str(doc.id),
        filename=doc.filename,
        status=doc.status,
        chunk_count=doc.chunk_count,
        processing_ms=doc.processing_ms,
        error=doc.error_msg,
        created_at=doc.created_at.isoformat() if doc.created_at else None,
    )
