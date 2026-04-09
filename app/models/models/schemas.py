from pydantic import BaseModel, Field
from typing import List, Optional
from datetime import datetime
from uuid import UUID
from app.models.db import DocumentStatus

# --- Document Schemas ---

class DocumentResponse(BaseModel):
    id: UUID
    tenant_id: UUID
    filename: str
    source_type: str  # e.g., pdf, md, docx, txt, html, url
    upload_time: datetime
    status: DocumentStatus
    error_message: Optional[str] = None

    class Config:
        from_attributes = True

class DeleteResponse(BaseModel):
    message: str
    document_id: UUID
    tenant_id: UUID

# --- Chat Schemas ---

class Citation(BaseModel):
    source: str
    content_snippet: str
    page: Optional[int] = None

class ChatRequest(BaseModel):
    query: str
    session_id: Optional[UUID] = None
    tenant_id: UUID

class ChatResponse(BaseModel):
    session_id: UUID
    tenant_id: UUID
    answer: str
    citations: List[Citation] = []

    class Config:
        from_attributes = True
