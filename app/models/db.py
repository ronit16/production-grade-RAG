"""
Production RAG System - Database Models
All tables include tenant_id for row-level isolation.
"""
import uuid
from datetime import datetime
from typing import Optional
import enum

from sqlalchemy import (
    Column, String, Text, Integer, BigInteger, Float,
    Boolean, DateTime, ForeignKey, Enum as SAEnum,
    UniqueConstraint, Index, JSON, func
)
from sqlalchemy.dialects.postgresql import UUID, JSONB, ARRAY
from sqlalchemy.orm import DeclarativeBase, relationship


class Base(DeclarativeBase):
    pass


# ─────────────────────────────────────────────────────────────────────────────
# Tenant & Plan
# ─────────────────────────────────────────────────────────────────────────────

class PlanTier(str, enum.Enum):
    FREE       = "free"
    STARTER    = "starter"
    PROFESSIONAL = "professional"
    ENTERPRISE = "enterprise"


PLAN_LIMITS = {
    PlanTier.FREE:         {"max_docs": 100,   "tokens_day": 50_000,   "rps": 2,   "max_sessions": 10},
    PlanTier.STARTER:      {"max_docs": 2_000,  "tokens_day": 500_000,  "rps": 10,  "max_sessions": 100},
    PlanTier.PROFESSIONAL: {"max_docs": 20_000, "tokens_day": 5_000_000,"rps": 50,  "max_sessions": 500},
    PlanTier.ENTERPRISE:   {"max_docs": None,   "tokens_day": None,     "rps": 200, "max_sessions": None},
}


class Tenant(Base):
    __tablename__ = "tenants"

    id         = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    slug       = Column(String(64), unique=True, nullable=False)     # url-safe name
    name       = Column(String(256), nullable=False)
    plan       = Column(SAEnum(PlanTier), nullable=False, default=PlanTier.FREE)
    is_active  = Column(Boolean, nullable=False, default=True)

    # Pinecone namespace (isolated vector space)
    vector_namespace = Column(String(128), nullable=False)  # = str(id)

    # Custom LLM config (optional override)
    llm_config = Column(JSONB, nullable=True)              # {"model": "gpt-4o", "temp": 0.1}
    rag_config = Column(JSONB, nullable=True)               # {"top_k": 8, "hybrid_alpha": 0.6}

    # Feature flags
    features   = Column(JSONB, nullable=False, default=dict)

    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    users      = relationship("User", back_populates="tenant", cascade="all, delete-orphan")
    documents  = relationship("Document", back_populates="tenant", cascade="all, delete-orphan")
    sessions   = relationship("Session", back_populates="tenant", cascade="all, delete-orphan")
    api_keys   = relationship("APIKey", back_populates="tenant", cascade="all, delete-orphan")


class User(Base):
    __tablename__ = "users"

    id         = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id  = Column(UUID(as_uuid=True), ForeignKey("tenants.id"), nullable=False)
    email      = Column(String(320), nullable=False)
    hashed_password = Column(String(128), nullable=True)   # null for SSO-only users
    role       = Column(String(32), nullable=False, default="member")  # owner|admin|member
    is_active  = Column(Boolean, nullable=False, default=True)

    created_at = Column(DateTime(timezone=True), server_default=func.now())
    last_login = Column(DateTime(timezone=True), nullable=True)

    tenant     = relationship("Tenant", back_populates="users")
    sessions   = relationship("Session", back_populates="user")

    __table_args__ = (
        UniqueConstraint("tenant_id", "email", name="uq_user_tenant_email"),
        Index("ix_users_tenant_email", "tenant_id", "email"),
    )


class APIKey(Base):
    __tablename__ = "api_keys"

    id         = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id  = Column(UUID(as_uuid=True), ForeignKey("tenants.id"), nullable=False)
    name       = Column(String(128), nullable=False)
    key_hash   = Column(String(128), unique=True, nullable=False)  # SHA-256 of raw key
    key_prefix = Column(String(12), nullable=False)                # first 12 chars for display
    scopes     = Column(ARRAY(String), nullable=False, default=list)
    is_active  = Column(Boolean, nullable=False, default=True)
    expires_at = Column(DateTime(timezone=True), nullable=True)
    last_used  = Column(DateTime(timezone=True), nullable=True)

    created_at = Column(DateTime(timezone=True), server_default=func.now())
    tenant     = relationship("Tenant", back_populates="api_keys")


# ─────────────────────────────────────────────────────────────────────────────
# Documents & Chunks
# ─────────────────────────────────────────────────────────────────────────────

class DocumentStatus(str, enum.Enum):
    PENDING    = "pending"
    PROCESSING = "processing"
    READY      = "ready"
    FAILED     = "failed"


class Document(Base):
    __tablename__ = "documents"
    __table_args__ = (
        Index("ix_docs_tenant_status", "tenant_id", "status"),
        Index("ix_docs_tenant_created", "tenant_id", "created_at"),
    )

    id         = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id  = Column(UUID(as_uuid=True), ForeignKey("tenants.id"), nullable=False)
    filename   = Column(String(512), nullable=False)
    content_type = Column(String(128), nullable=False)  # application/pdf, text/html, ...
    file_size  = Column(BigInteger, nullable=False)
    s3_key     = Column(String(1024), nullable=False)

    status     = Column(SAEnum(DocumentStatus), nullable=False, default=DocumentStatus.PENDING)
    error_msg  = Column(Text, nullable=True)

    # Metadata extracted during processing
    title      = Column(String(512), nullable=True)
    page_count = Column(Integer, nullable=True)
    word_count = Column(Integer, nullable=True)
    language   = Column(String(10), nullable=True)
    doc_metadata = Column(JSONB, nullable=False, default=dict)

    # Processing metrics
    chunk_count    = Column(Integer, nullable=True)
    embedding_model = Column(String(128), nullable=True)  # model used for embeddings
    processing_ms  = Column(Integer, nullable=True)

    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    deleted_at = Column(DateTime(timezone=True), nullable=True)  # soft delete

    tenant = relationship("Tenant", back_populates="documents")
    chunks = relationship("Chunk", back_populates="document", cascade="all, delete-orphan")


class Chunk(Base):
    """Stores chunk metadata. Raw text in S3, vectors in Pinecone."""
    __tablename__ = "chunks"
    __table_args__ = (
        Index("ix_chunks_tenant_doc", "tenant_id", "document_id"),
        Index("ix_chunks_vector_id", "vector_id"),
    )

    id          = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id   = Column(UUID(as_uuid=True), ForeignKey("tenants.id"), nullable=False)
    document_id = Column(UUID(as_uuid=True), ForeignKey("documents.id"), nullable=False)

    vector_id   = Column(String(256), unique=True, nullable=False)  # Pinecone vector ID
    text        = Column(Text, nullable=False)                       # raw chunk text
    text_hash   = Column(String(64), nullable=False)                 # SHA-256 for dedup

    chunk_index = Column(Integer, nullable=False)
    page_number = Column(Integer, nullable=True)
    section     = Column(String(256), nullable=True)
    chunk_metadata = Column(JSONB, nullable=False, default=dict)

    token_count = Column(Integer, nullable=False)
    created_at  = Column(DateTime(timezone=True), server_default=func.now())

    document = relationship("Document", back_populates="chunks")


# ─────────────────────────────────────────────────────────────────────────────
# Sessions & Queries
# ─────────────────────────────────────────────────────────────────────────────

class Session(Base):
    """Persistent session record (live state in Redis)."""
    __tablename__ = "sessions"
    __table_args__ = (
        Index("ix_sessions_tenant_user", "tenant_id", "user_id"),
    )

    id         = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id  = Column(UUID(as_uuid=True), ForeignKey("tenants.id"), nullable=False)
    user_id    = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)  # null = anon
    title      = Column(String(256), nullable=True)                  # auto-generated from first Q
    is_active  = Column(Boolean, nullable=False, default=True)

    # Aggregate stats
    message_count  = Column(Integer, nullable=False, default=0)
    token_count_in = Column(Integer, nullable=False, default=0)
    token_count_out= Column(Integer, nullable=False, default=0)

    started_at = Column(DateTime(timezone=True), server_default=func.now())
    last_active= Column(DateTime(timezone=True), server_default=func.now())
    ended_at   = Column(DateTime(timezone=True), nullable=True)

    tenant  = relationship("Tenant", back_populates="sessions")
    user    = relationship("User", back_populates="sessions")
    queries = relationship("Query", back_populates="session", cascade="all, delete-orphan")


class Query(Base):
    """Full audit log of every query with sources and metrics."""
    __tablename__ = "queries"
    __table_args__ = (
        Index("ix_queries_tenant_created", "tenant_id", "created_at"),
        Index("ix_queries_session", "session_id"),
    )

    id         = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id  = Column(UUID(as_uuid=True), ForeignKey("tenants.id"), nullable=False)
    session_id = Column(UUID(as_uuid=True), ForeignKey("sessions.id"), nullable=False)

    question   = Column(Text, nullable=False)
    answer     = Column(Text, nullable=True)   # null while streaming
    sources    = Column(JSONB, nullable=True)   # [{chunk_id, score, excerpt}]

    # Rewrite
    rewritten_question = Column(Text, nullable=True)

    # Metrics
    retrieval_ms   = Column(Integer, nullable=True)
    generation_ms  = Column(Integer, nullable=True)
    total_ms       = Column(Integer, nullable=True)
    tokens_in      = Column(Integer, nullable=True)
    tokens_out     = Column(Integer, nullable=True)
    llm_model      = Column(String(128), nullable=True)
    embedding_model= Column(String(128), nullable=True)

    # Evaluation (populated async by eval workers)
    faithfulness_score   = Column(Float, nullable=True)
    relevancy_score      = Column(Float, nullable=True)
    user_rating          = Column(Integer, nullable=True)  # 1-5 thumbs

    error      = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    session = relationship("Session", back_populates="queries")


# ─────────────────────────────────────────────────────────────────────────────
# Usage tracking
# ─────────────────────────────────────────────────────────────────────────────

class UsageLog(Base):
    """Daily rollup of token usage per tenant for billing."""
    __tablename__ = "usage_logs"
    __table_args__ = (
        UniqueConstraint("tenant_id", "date", name="uq_usage_tenant_date"),
    )

    id         = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id  = Column(UUID(as_uuid=True), ForeignKey("tenants.id"), nullable=False)
    date       = Column(DateTime(timezone=True), nullable=False)   # truncated to day
    tokens_in  = Column(BigInteger, nullable=False, default=0)
    tokens_out = Column(BigInteger, nullable=False, default=0)
    query_count= Column(Integer, nullable=False, default=0)
    doc_count  = Column(Integer, nullable=False, default=0)
