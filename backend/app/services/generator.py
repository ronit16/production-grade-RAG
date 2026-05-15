"""
Production RAG System - Generator Service
Context assembly → LLM call → streaming with citations.
Uses LiteLLM for provider-agnostic routing + automatic fallback.
"""
import os
import time
from dataclasses import dataclass, field
from typing import AsyncIterator, Optional

import litellm
from litellm import acompletion

from app.core.config import get_settings
from app.middleware.auth import TenantContext
from app.services.retriever import RetrievalResult, RetrievedChunk

settings = get_settings()

# Configure LiteLLM — each provider reads its key from os.environ
os.environ["OPENAI_API_KEY"] = settings.OPENAI_API_KEY
os.environ["GEMINI_API_KEY"] = settings.GEMINI_API_KEY
litellm.set_verbose = settings.DEBUG


# ─────────────────────────────────────────────────────────────────────────────
# Prompts
# ─────────────────────────────────────────────────────────────────────────────

BASE_SYSTEM = """You are a helpful AI assistant with access to a knowledge base.
Answer questions using ONLY the provided context chunks.
If the answer is not in the context, say so clearly — do not hallucinate.
When you use information from a chunk, cite it as [1], [2], etc.
Be concise, accurate, and professional."""

CONTEXT_TEMPLATE = """
--- Context [{idx}] (from: {section}, page {page}) ---
{text}
"""

FALLBACK_ANSWER = (
    "I couldn't find relevant information in your knowledge base to answer this question. "
    "Please try rephrasing, or upload additional documents."
)


# ─────────────────────────────────────────────────────────────────────────────
# Context assembly
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class GenerationRequest:
    query_id:   str
    question:   str
    chunks:     list[RetrievedChunk]
    history:    list[dict]   # OpenAI-format messages
    system_override: Optional[str] = None


def build_context(chunks: list[RetrievedChunk], max_tokens: int = 6000) -> tuple[str, list[dict]]:
    """
    Pack top chunks into a context string.
    Returns (context_text, source_metadata_list) for citation.
    """
    context_parts = []
    sources       = []
    token_budget  = max_tokens

    for idx, chunk in enumerate(chunks, start=1):
        approx_tokens = len(chunk.text) // 4
        if token_budget - approx_tokens < 100:
            break

        section  = chunk.section or "Unknown section"
        page     = chunk.page_number or "N/A"

        context_parts.append(CONTEXT_TEMPLATE.format(
            idx=idx, section=section, page=page, text=chunk.text
        ))
        sources.append({
            "index":       idx,
            "chunk_id":    chunk.chunk_id,
            "document_id": chunk.document_id,
            "section":     section,
            "page_number": chunk.page_number,
            "score":       round(chunk.score, 4),
            "excerpt":     chunk.text[:200] + "..." if len(chunk.text) > 200 else chunk.text,
        })
        token_budget -= approx_tokens

    return "\n".join(context_parts), sources


def build_messages(req: GenerationRequest) -> list[dict]:
    """Assemble full message list for the LLM."""
    context_text, _ = build_context(req.chunks)

    system_content = req.system_override or BASE_SYSTEM
    if context_text:
        system_content += f"\n\n=== Knowledge Base Context ===\n{context_text}"

    messages = [{"role": "system", "content": system_content}]
    messages.extend(req.history)
    messages.append({"role": "user", "content": req.question})

    return messages


# ─────────────────────────────────────────────────────────────────────────────
# Generation with streaming
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class GenerationChunk:
    delta:    str             # streamed text fragment
    done:     bool = False
    sources:  list = field(default_factory=list)
    query_id: str  = ""
    usage:    dict = field(default_factory=dict)
    error:    Optional[str] = None


async def generate_stream(
    req: GenerationRequest,
    ctx: TenantContext,
) -> AsyncIterator[GenerationChunk]:
    """
    Stream LLM response with automatic provider fallback.
    Yields GenerationChunk objects; final chunk has done=True + sources.
    """
    messages     = build_messages(req)
    _, sources   = build_context(req.chunks)

    # Resolve model (tenant override > env default)
    model = ctx.llm_config.get("model") or settings.PRIMARY_LLM.value
    temp  = ctx.llm_config.get("temperature", 0.1)

    start_ms     = time.monotonic()
    full_response = []
    usage        = {}

    try:
        stream = await acompletion(
            model=model,
            messages=messages,
            temperature=temp,
            max_tokens=settings.MAX_TOKENS,
            stream=True,
            timeout=settings.LLM_TIMEOUT_SECONDS,
            # LiteLLM fallback — automatically tries FALLBACK_LLM on error
            fallbacks=[settings.FALLBACK_LLM.value],
        )

        async for chunk in stream:
            delta = chunk.choices[0].delta.content or ""
            if delta:
                full_response.append(delta)
                yield GenerationChunk(delta=delta, query_id=req.query_id)

            # Capture usage from final chunk
            if chunk.usage:
                usage = {
                    "input_tokens":  chunk.usage.prompt_tokens,
                    "output_tokens": chunk.usage.completion_tokens,
                    "model":         model,
                }

        generation_ms = int((time.monotonic() - start_ms) * 1000)

        # Final chunk with metadata
        yield GenerationChunk(
            delta="",
            done=True,
            sources=sources,
            query_id=req.query_id,
            usage={**usage, "generation_ms": generation_ms},
        )

    except litellm.Timeout:
        yield GenerationChunk(
            delta=FALLBACK_ANSWER,
            done=True,
            error="LLM timeout",
            query_id=req.query_id,
            sources=[],
        )

    except Exception as exc:
        yield GenerationChunk(
            delta=f"Generation error: {exc}",
            done=True,
            error=str(exc),
            query_id=req.query_id,
            sources=[],
        )


async def generate_sync(
    req: GenerationRequest,
    ctx: TenantContext,
) -> tuple[str, list[dict], dict]:
    """
    Non-streaming generation — returns (answer, sources, usage).
    Used for batch evaluation and background tasks.
    """
    full_text = []
    final_sources = []
    final_usage   = {}

    async for chunk in generate_stream(req, ctx):
        if not chunk.done:
            full_text.append(chunk.delta)
        else:
            final_sources = chunk.sources or []
            final_usage   = chunk.usage   or {}

    return "".join(full_text), final_sources, final_usage
