"""Pydantic schemas for the RAG query endpoint."""
from typing import Optional
from pydantic import BaseModel, Field


class QueryRequest(BaseModel):
    session_id:     str
    question:       str = Field(..., min_length=1, max_length=4096)
    filter_doc_ids: Optional[list[str]] = None
    stream:         bool = True
