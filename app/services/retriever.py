"""
Production RAG System - Hybrid Retrieval Service
Dense (OpenAI) + Sparse (BM25 via fastembed) → Qdrant native RRF fusion → Cross-encoder rerank

Architecture:
  - One Qdrant collection shared across all tenants, isolated by `tenant_id` payload filter
  - Each point stores both a "dense" named vector and a "sparse" named vector
  - Qdrant's query_points Prefetch + Fusion.RRF handles hybrid fusion natively — no manual RRF
  - Cross-encoder reranking runs on the fused top-K for precision improvement
"""
import asyncio
import time
from dataclasses import dataclass
from typing import Optional

from fastembed import SparseTextEmbedding
from openai import AsyncOpenAI
from qdrant_client import AsyncQdrantClient
from qdrant_client.models import (
    Distance,
    FieldCondition,
    Filter,
    Fusion,
    HnswConfigDiff,
    MatchValue,
    PayloadSchemaType,
    Prefetch,
    SparseVector,
    SparseVectorParams,
    VectorParams,
)
from sentence_transformers import CrossEncoder

from app.core.config import get_settings
from app.middleware.auth import TenantContext

settings = get_settings()


# ─────────────────────────────────────────────────────────────────────────────
# Result types
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class RetrievedChunk:
    chunk_id:    str
    document_id: str
    text:        str
    score:       float
    page_number: Optional[int]
    section:     Optional[str]
    metadata:    dict


@dataclass
class RetrievalResult:
    chunks:          list[RetrievedChunk]
    query:           str
    rewritten_query: Optional[str]
    retrieval_ms:    int
    candidate_count: int   # how many Qdrant returned before rerank


# ─────────────────────────────────────────────────────────────────────────────
# Client singletons
# ─────────────────────────────────────────────────────────────────────────────

_oai_client:     Optional[AsyncOpenAI]         = None
_qdrant_client:  Optional[AsyncQdrantClient]   = None
_sparse_model:   Optional[SparseTextEmbedding] = None
_cross_encoder:  Optional[CrossEncoder]        = None


def _get_openai() -> AsyncOpenAI:
    global _oai_client
    if not _oai_client:
        _oai_client = AsyncOpenAI(api_key=settings.OPENAI_API_KEY)
    return _oai_client


def _get_qdrant() -> AsyncQdrantClient:
    global _qdrant_client
    if not _qdrant_client:
        _qdrant_client = AsyncQdrantClient(
            url=settings.QDRANT_URL,
            api_key=settings.QDRANT_API_KEY,
            timeout=30,
        )
    return _qdrant_client


def _get_sparse_model() -> SparseTextEmbedding:
    """Lazy-load the BM25 fastembed model (downloads once, cached on disk)."""
    global _sparse_model
    if not _sparse_model:
        _sparse_model = SparseTextEmbedding(model_name=settings.QDRANT_SPARSE_MODEL)
    return _sparse_model


def _get_cross_encoder() -> CrossEncoder:
    global _cross_encoder
    if not _cross_encoder:
        _cross_encoder = CrossEncoder("cross-encoder/ms-marco-MiniLM-L-6-v2")
    return _cross_encoder


# ─────────────────────────────────────────────────────────────────────────────
# Collection management
# ─────────────────────────────────────────────────────────────────────────────

async def ensure_collection() -> None:
    """
    Idempotently create the Qdrant collection with named dense + sparse vectors
    and a keyword payload index on tenant_id for fast filtering.
    Called once at application startup.
    """
    client = _get_qdrant()
    exists = await client.collection_exists(settings.QDRANT_COLLECTION)
    if exists:
        return

    await client.create_collection(
        collection_name=settings.QDRANT_COLLECTION,
        vectors_config={
            "dense": VectorParams(
                size=settings.QDRANT_DENSE_DIM,
                distance=Distance.COSINE,
                hnsw_config=HnswConfigDiff(m=16, ef_construct=100),
            )
        },
        sparse_vectors_config={
            "sparse": SparseVectorParams()
        },
    )

    # Payload index so tenant_id filtering uses an inverted index, not a scan
    await client.create_payload_index(
        collection_name=settings.QDRANT_COLLECTION,
        field_name="tenant_id",
        field_schema=PayloadSchemaType.KEYWORD,
    )
    await client.create_payload_index(
        collection_name=settings.QDRANT_COLLECTION,
        field_name="document_id",
        field_schema=PayloadSchemaType.KEYWORD,
    )


# ─────────────────────────────────────────────────────────────────────────────
# Query rewriting (standalone question from chat history)
# ─────────────────────────────────────────────────────────────────────────────

REWRITE_SYSTEM = """You are a query rewriter for a RAG system.
Given a conversation history and a follow-up question, rewrite the question
so it is fully self-contained (no pronouns referring to prior context).
Return ONLY the rewritten question — no explanation."""


async def rewrite_query(question: str, history: list[dict]) -> str:
    if not history:
        return question

    history_str = "\n".join(
        f"{m['role'].capitalize()}: {m['content']}"
        for m in history[-6:]
    )
    prompt = f"Conversation:\n{history_str}\n\nFollow-up: {question}"

    response = await _get_openai().chat.completions.create(
        model="gpt-4o-mini",
        messages=[
            {"role": "system", "content": REWRITE_SYSTEM},
            {"role": "user",   "content": prompt},
        ],
        temperature=0,
        max_tokens=256,
    )
    return response.choices[0].message.content.strip()


# ─────────────────────────────────────────────────────────────────────────────
# Embedding helpers
# ─────────────────────────────────────────────────────────────────────────────

async def _embed_dense(text: str) -> list[float]:
    response = await _get_openai().embeddings.create(
        input=text,
        model=settings.EMBEDDING_MODEL,
    )
    return response.data[0].embedding


def _embed_sparse_sync(text: str) -> SparseVector:
    """Generate a BM25 sparse vector. Runs sync; call via run_in_executor."""
    result = next(iter(_get_sparse_model().embed([text])))
    return SparseVector(indices=result.indices.tolist(), values=result.values.tolist())


async def _embed_sparse(text: str) -> SparseVector:
    """Async wrapper — fastembed is CPU-bound, keeps the event loop unblocked."""
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, _embed_sparse_sync, text)


# ─────────────────────────────────────────────────────────────────────────────
# Hybrid search via Qdrant Prefetch + native RRF
# ─────────────────────────────────────────────────────────────────────────────

def _tenant_filter(tenant_id: str, filter_doc_ids: Optional[list[str]] = None) -> Filter:
    conditions = [FieldCondition(key="tenant_id", match=MatchValue(value=str(tenant_id)))]
    if filter_doc_ids:
        from qdrant_client.models import MatchAny
        conditions.append(FieldCondition(key="document_id", match=MatchAny(any=filter_doc_ids)))
    return Filter(must=conditions)


async def hybrid_search(
    query: str,
    tenant_id: str,
    top_k: int,
    filter_doc_ids: Optional[list[str]] = None,
) -> list[dict]:
    """
    Run dense + sparse searches in parallel, then fuse with Qdrant's native RRF.
    Returns raw result dicts ready for reranking.
    """
    payload_filter = _tenant_filter(str(tenant_id), filter_doc_ids)

    # Build both query vectors concurrently
    dense_vec, sparse_vec = await asyncio.gather(
        _embed_dense(query),
        _embed_sparse(query),
    )

    client  = _get_qdrant()
    results = await client.query_points(
        collection_name=settings.QDRANT_COLLECTION,
        prefetch=[
            # Dense (ANN cosine) branch
            Prefetch(
                query=dense_vec,
                using="dense",
                filter=payload_filter,
                limit=top_k,
            ),
            # Sparse (BM25) branch
            Prefetch(
                query=sparse_vec,
                using="sparse",
                filter=payload_filter,
                limit=top_k,
            ),
        ],
        # Qdrant merges both branches with Reciprocal Rank Fusion
        query=Fusion.RRF,
        limit=top_k,
        with_payload=True,
    )

    return [
        {
            "chunk_id":    str(r.id),
            "score":       r.score,
            "document_id": r.payload.get("document_id", ""),
            "text":        r.payload.get("text", ""),
            "page_number": r.payload.get("page_number"),
            "section":     r.payload.get("section"),
            "metadata":    {k: v for k, v in r.payload.items()
                            if k not in ("text", "tenant_id")},
        }
        for r in results.points
    ]


# ─────────────────────────────────────────────────────────────────────────────
# Cross-encoder reranking
# ─────────────────────────────────────────────────────────────────────────────

def rerank(query: str, candidates: list[dict], top_k: int) -> list[dict]:
    """
    Re-score fused candidates with a cross-encoder for precision improvement.
    Runs sync inside run_in_executor to avoid blocking the event loop.
    """
    if not candidates:
        return []

    encoder = _get_cross_encoder()
    pairs   = [(query, c["text"]) for c in candidates]
    scores  = encoder.predict(pairs, apply_softmax=True, show_progress_bar=False)

    for candidate, score in zip(candidates, scores):
        candidate["rerank_score"] = float(score)

    return sorted(candidates, key=lambda x: x["rerank_score"], reverse=True)[:top_k]


# ─────────────────────────────────────────────────────────────────────────────
# Main retrieval entry point
# ─────────────────────────────────────────────────────────────────────────────

async def retrieve(
    question: str,
    ctx: TenantContext,
    history: list[dict] | None = None,
    filter_doc_ids: list[str] | None = None,
) -> RetrievalResult:
    """
    Full hybrid retrieval pipeline:
    1. Rewrite query for standalone retrieval
    2. Qdrant hybrid search (dense + sparse → RRF fusion)
    3. Cross-encoder reranking
    """
    start_ms = time.monotonic()

    top_k  = ctx.rag_config.get("top_k",        settings.RETRIEVAL_TOP_K)
    rk_top = ctx.rag_config.get("rerank_top_k", settings.RERANK_TOP_K)

    # Step 1: Query rewrite
    rewritten = await rewrite_query(question, history or [])

    # Step 2: Qdrant hybrid search (dense + sparse + RRF)
    candidates = await hybrid_search(
        query=rewritten,
        tenant_id=ctx.tenant_id,
        top_k=top_k,
        filter_doc_ids=filter_doc_ids,
    )

    # Step 3: Cross-encoder reranking (sync → executor)
    loop     = asyncio.get_event_loop()
    reranked = await loop.run_in_executor(
        None, rerank, rewritten, candidates, rk_top
    )

    retrieval_ms = int((time.monotonic() - start_ms) * 1000)

    chunks = [
        RetrievedChunk(
            chunk_id=    r["chunk_id"],
            document_id= r["document_id"],
            text=        r["text"],
            score=       r["rerank_score"],
            page_number= r.get("page_number"),
            section=     r.get("section"),
            metadata=    r.get("metadata", {}),
        )
        for r in reranked
    ]

    return RetrievalResult(
        chunks=chunks,
        query=question,
        rewritten_query=rewritten if rewritten != question else None,
        retrieval_ms=retrieval_ms,
        candidate_count=len(candidates),
    )
