"""RAG query endpoint — streams response via Server-Sent Events."""
import json
import uuid
from typing import AsyncIterator

from fastapi import APIRouter
from fastapi.responses import StreamingResponse
from sqlalchemy import update

from app.api.deps import DBSession, RedisClient
from app.middleware.auth import RatedContext, TenantContext
from app.models.db import Query as DBQuery
from app.schemas.query import QueryRequest
from app.services.generator import GenerationRequest, generate_stream
from app.services.retriever import retrieve
from app.services.session import Message, SessionManager

router = APIRouter(prefix="/query", tags=["query"])


async def _sse_stream(
    req:   QueryRequest,
    ctx:   TenantContext,
    db:    DBSession,
    redis: RedisClient,
) -> AsyncIterator[str]:
    """SSE event generator for streaming RAG responses."""
    sm     = SessionManager(redis, db)
    state  = await sm.get_session(req.session_id, str(ctx.tenant_id))
    if not state:
        yield f"event: error\ndata: {json.dumps({'error': 'Session not found'})}\n\n"
        return

    query_id = str(uuid.uuid4())

    # Save user message immediately
    user_msg = Message(role="user", content=req.question, tokens_in=len(req.question) // 4)
    await sm.add_message(state, user_msg)

    # Create DB query record (answer filled in after generation)
    db_query = DBQuery(
        id=uuid.UUID(query_id),
        tenant_id=ctx.tenant_id,
        session_id=uuid.UUID(req.session_id),
        question=req.question,
    )
    db.add(db_query)
    await db.flush()

    # Step 1: Retrieve
    yield f"event: status\ndata: {json.dumps({'status': 'retrieving'})}\n\n"

    retrieval = await retrieve(
        question=req.question,
        ctx=ctx,
        history=state.get_history_for_prompt(),
        filter_doc_ids=req.filter_doc_ids,
    )

    yield f"event: retrieval\ndata: {json.dumps({'chunk_count': len(retrieval.chunks), 'rewritten_query': retrieval.rewritten_query})}\n\n"

    # Step 2: Generate (stream tokens)
    yield f"event: status\ndata: {json.dumps({'status': 'generating'})}\n\n"

    gen_req = GenerationRequest(
        query_id=query_id,
        question=req.question,
        chunks=retrieval.chunks,
        history=state.get_history_for_prompt(),
    )

    full_answer   = []
    final_sources = []
    final_usage   = {}

    async for chunk in generate_stream(gen_req, ctx):
        if not chunk.done:
            full_answer.append(chunk.delta)
            yield f"event: delta\ndata: {json.dumps({'text': chunk.delta})}\n\n"
        else:
            final_sources = chunk.sources or []
            final_usage   = chunk.usage   or {}

    answer_text = "".join(full_answer)

    # Step 3: Persist answer + update session
    assistant_msg = Message(
        role="assistant",
        content=answer_text,
        sources=final_sources,
        query_id=query_id,
        tokens_out=final_usage.get("output_tokens", 0),
    )
    await sm.add_message(state, assistant_msg)

    await db.execute(
        update(DBQuery)
        .where(DBQuery.id == uuid.UUID(query_id))
        .values(
            answer=answer_text,
            sources=final_sources,
            rewritten_question=retrieval.rewritten_query,
            retrieval_ms=retrieval.retrieval_ms,
            tokens_in=final_usage.get("input_tokens"),
            tokens_out=final_usage.get("output_tokens"),
            llm_model=final_usage.get("model"),
        )
    )
    await db.commit()

    yield f"event: done\ndata: {json.dumps({'sources': final_sources, 'query_id': query_id})}\n\n"


@router.post("")
async def query(
    req:   QueryRequest,
    ctx:   RatedContext,
    db:    DBSession,
    redis: RedisClient,
):
    """
    Stream a RAG response via Server-Sent Events.
    Event types: status | retrieval | delta | done | error
    """
    return StreamingResponse(
        _sse_stream(req, ctx, db, redis),
        media_type="text/event-stream",
        headers={
            "Cache-Control":    "no-cache",
            "X-Accel-Buffering": "no",   # disable NGINX buffering
        },
    )
