"""Pydantic schemas for document upload and status endpoints."""
from typing import Optional
from pydantic import BaseModel
from app.models.db import DocumentStatus


class DocumentUploadResponse(BaseModel):
    document_id: str
    status: str
    filename: str


class DocumentStatusResponse(BaseModel):
    document_id: str
    filename: str
    status: DocumentStatus
    chunk_count: Optional[int] = None
    processing_ms: Optional[int] = None
    error: Optional[str] = None
    created_at: Optional[str] = None
