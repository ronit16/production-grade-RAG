"""
Production RAG System - Document Ingestion Pipeline
Async Celery workers: parse → chunk → embed (dense + sparse) → Qdrant upsert → DB persist
"""
import hashlib
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterator, Optional

import boto3
from celery.utils.log import get_task_logger
from fastembed import SparseTextEmbedding
from openai import OpenAI
from qdrant_client import QdrantClient
from qdrant_client.models import PointStruct, SparseVector
from sqlalchemy import create_engine
from sqlalchemy.orm import Session as DBSession
from unstructured.partition.auto import partition

from app.core.config import get_settings
from app.models.db import Chunk, Document, DocumentStatus
from app.workers.celery_app import celery_app

settings = get_settings()
logger   = get_task_logger(__name__)

# ── Clients (initialized once per worker process) ─────────────────────────────
oai          = OpenAI(api_key=settings.OPENAI_API_KEY)
qdrant       = QdrantClient(url=settings.QDRANT_URL, api_key=settings.QDRANT_API_KEY)
sparse_model = SparseTextEmbedding(model_name=settings.QDRANT_SPARSE_MODEL)
s3           = boto3.client(
    "s3",
    endpoint_url=settings.MINIO_ENDPOINT,
    aws_access_key_id=settings.MINIO_ACCESS_KEY,
    aws_secret_access_key=settings.MINIO_SECRET_KEY,
)
engine       = create_engine(settings.DATABASE_URL, pool_size=5)


# ─────────────────────────────────────────────────────────────────────────────
# Data classes
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class ChunkRecord:
    chunk_index: int
    text:        str
    text_hash:   str
    token_count: int
    page_number: Optional[int]
    section:     Optional[str]
    metadata:    dict           = field(default_factory=dict)
    vector_id:   str            = field(default_factory=lambda: str(uuid.uuid4()))


# ─────────────────────────────────────────────────────────────────────────────
# Step 1: Parsing & chunking
# ─────────────────────────────────────────────────────────────────────────────

def _estimate_tokens(text: str) -> int:
    """Fast approximation: ~4 chars per token."""
    return max(1, len(text) // 4)


def parse_and_chunk(s3_key: str, content_type: str) -> list[ChunkRecord]:
    """
    Download from S3, parse with Unstructured, apply semantic chunking.
    Returns a list of ChunkRecord objects ready for embedding.
    """
    tmp_path = Path(f"/tmp/{uuid.uuid4()}")
    s3.download_file(settings.S3_BUCKET, s3_key, str(tmp_path))

    try:
        elements = partition(
            filename=str(tmp_path),
            strategy="fast",
            include_metadata=True,
            chunking_strategy="by_title",
            max_characters=settings.CHUNK_SIZE * 4,
            overlap=settings.CHUNK_OVERLAP * 4,
        )
    finally:
        tmp_path.unlink(missing_ok=True)

    records: list[ChunkRecord] = []
    for idx, el in enumerate(elements):
        text = str(el).strip()
        if not text or len(text) < 20:
            continue

        meta        = getattr(el, "metadata", None)
        page_number = getattr(meta, "page_number", None) if meta else None
        section     = getattr(meta, "section", None)     if meta else None

        records.append(ChunkRecord(
            chunk_index=idx,
            text=text,
            text_hash=hashlib.sha256(text.encode()).hexdigest(),
            token_count=_estimate_tokens(text),
            page_number=page_number,
            section=section or "",
            metadata={
                "content_type": content_type,
                "element_type": type(el).__name__,
            },
        ))

    return records


# ─────────────────────────────────────────────────────────────────────────────
# Step 2a: Dense embedding (OpenAI, batched)
# ─────────────────────────────────────────────────────────────────────────────

def _batch(items: list, size: int) -> Iterator[list]:
    for i in range(0, len(items), size):
        yield items[i : i + size]


def embed_dense(chunks: list[ChunkRecord], model: str) -> list[list[float]]:
    """Batch-embed chunk texts with OpenAI and return vectors in input order."""
    all_vectors: list[list[float]] = []

    for batch in _batch(chunks, settings.EMBEDDING_BATCH_SIZE):
        texts    = [c.text for c in batch]
        response = oai.embeddings.create(input=texts, model=model)
        vecs     = [item.embedding for item in sorted(response.data, key=lambda x: x.index)]
        all_vectors.extend(vecs)

    return all_vectors


# ─────────────────────────────────────────────────────────────────────────────
# Step 2b: Sparse embedding (BM25 via fastembed)
# ─────────────────────────────────────────────────────────────────────────────

def embed_sparse(chunks: list[ChunkRecord]) -> list[SparseVector]:
    """Generate BM25 sparse vectors for all chunks using fastembed."""
    texts   = [c.text for c in chunks]
    results = list(sparse_model.embed(texts))
    return [
        SparseVector(indices=r.indices.tolist(), values=r.values.tolist())
        for r in results
    ]


# ─────────────────────────────────────────────────────────────────────────────
# Step 3: Upsert to Qdrant (both dense and sparse vectors)
# ─────────────────────────────────────────────────────────────────────────────

def upsert_to_qdrant(
    tenant_id:        str,
    document_id:      str,
    chunks:           list[ChunkRecord],
    dense_vectors:    list[list[float]],
    sparse_vectors:   list[SparseVector],
) -> None:
    """
    Upsert each chunk as a Qdrant point with:
      - 'dense'  named vector  (OpenAI embedding)
      - 'sparse' named vector  (BM25 from fastembed)
    Tenant isolation is enforced via the `tenant_id` payload field + query-time filter.
    """
    points = [
        PointStruct(
            id=chunk.vector_id,
            vector={
                "dense":  dense,
                "sparse": sparse,
            },
            payload={
                "tenant_id":   tenant_id,
                "document_id": document_id,
                "chunk_index": chunk.chunk_index,
                "page_number": chunk.page_number or 0,
                "section":     chunk.section or "",
                "token_count": chunk.token_count,
                # Store full text in payload (no separate text store needed)
                "text":        chunk.text,
            },
        )
        for chunk, dense, sparse in zip(chunks, dense_vectors, sparse_vectors)
    ]

    # Qdrant recommends batches of ≤100 for upsert
    for batch in _batch(points, 100):
        qdrant.upsert(collection_name=settings.QDRANT_COLLECTION, points=batch)


# ─────────────────────────────────────────────────────────────────────────────
# Step 4: Persist chunk metadata to PostgreSQL
# ─────────────────────────────────────────────────────────────────────────────

def persist_chunks(
    tenant_id:   str,
    document_id: str,
    chunks:      list[ChunkRecord],
) -> None:
    with DBSession(engine) as db:
        db_chunks = [
            Chunk(
                id=uuid.uuid4(),
                tenant_id=tenant_id,
                document_id=document_id,
                vector_id=c.vector_id,
                text=c.text,
                text_hash=c.text_hash,
                chunk_index=c.chunk_index,
                page_number=c.page_number,
                section=c.section,
                chunk_metadata=c.metadata,
                token_count=c.token_count,
            )
            for c in chunks
        ]
        db.add_all(db_chunks)
        db.commit()


# ─────────────────────────────────────────────────────────────────────────────
# Celery task: full ingestion pipeline
# ─────────────────────────────────────────────────────────────────────────────

@celery_app.task(
    bind=True,
    max_retries=3,
    default_retry_delay=30,
    autoretry_for=(Exception,),
    name="ingest.process_document",
)
def process_document(
    self,
    document_id:      str,
    tenant_id:        str,
    s3_key:           str,
    content_type:     str,
    embedding_model:  str,
) -> dict:
    """
    Full ingestion pipeline for a single document. Retries up to 3 times.
    Steps: parse → chunk → embed dense → embed sparse → Qdrant upsert → DB persist
    """
    start_ms = time.monotonic()

    with DBSession(engine) as db:
        doc = db.get(Document, document_id)
        if not doc:
            raise ValueError(f"Document {document_id} not found")
        doc.status = DocumentStatus.PROCESSING
        db.commit()

    try:
        # Step 1: Parse & chunk
        logger.info(f"[{document_id}] Parsing {s3_key}")
        chunks = parse_and_chunk(s3_key, content_type)
        logger.info(f"[{document_id}] Created {len(chunks)} chunks")

        # Step 2a: Dense embedding
        logger.info(f"[{document_id}] Dense embedding with {embedding_model}")
        dense_vecs = embed_dense(chunks, embedding_model)

        # Step 2b: Sparse embedding (BM25)
        logger.info(f"[{document_id}] Sparse embedding (BM25)")
        sparse_vecs = embed_sparse(chunks)

        # Step 3: Upsert to Qdrant
        logger.info(f"[{document_id}] Upserting {len(chunks)} points to Qdrant")
        upsert_to_qdrant(tenant_id, document_id, chunks, dense_vecs, sparse_vecs)

        # Step 4: Persist chunk metadata to PostgreSQL
        persist_chunks(tenant_id, document_id, chunks)

        total_ms = int((time.monotonic() - start_ms) * 1000)

        with DBSession(engine) as db:
            doc = db.get(Document, document_id)
            doc.status          = DocumentStatus.READY
            doc.chunk_count     = len(chunks)
            doc.embedding_model = embedding_model
            doc.processing_ms   = total_ms
            db.commit()

        logger.info(f"[{document_id}] Done in {total_ms}ms")
        return {"document_id": document_id, "chunks": len(chunks), "ms": total_ms}

    except Exception as exc:
        logger.exception(f"[{document_id}] Ingestion failed: {exc}")
        with DBSession(engine) as db:
            doc = db.get(Document, document_id)
            doc.status    = DocumentStatus.FAILED
            doc.error_msg = str(exc)[:500]
            db.commit()
        raise
