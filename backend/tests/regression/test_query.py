"""Regression tests: SSE streaming query endpoint."""
import json
import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest
import respx


# ── OpenAI mock helpers ───────────────────────────────────────────────────────

FAKE_EMBEDDING = [0.01] * 1536
FAKE_SPARSE = {"indices": [1, 2, 3], "values": [0.1, 0.2, 0.3]}

FAKE_STREAM_CHUNKS = (
    b'data: {"choices":[{"delta":{"content":"Hello"},"finish_reason":null}]}\n\n'
    b'data: {"choices":[{"delta":{"content":" world"},"finish_reason":null}]}\n\n'
    b"data: [DONE]\n\n"
)


@pytest.fixture
def mocked_openai():
    """Mock OpenAI HTTP calls at the httpx transport level via respx."""
    with respx.mock(base_url="https://api.openai.com", assert_all_called=False) as mock:
        mock.post("/v1/embeddings").mock(return_value=httpx.Response(
            200,
            json={
                "data": [{"embedding": FAKE_EMBEDDING, "index": 0}],
                "model": "text-embedding-3-large",
                "usage": {"prompt_tokens": 10, "total_tokens": 10},
            },
        ))
        mock.post("/v1/chat/completions").mock(return_value=httpx.Response(
            200,
            content=FAKE_STREAM_CHUNKS,
            headers={"content-type": "text/event-stream"},
        ))
        yield mock


@pytest.fixture
def mocked_retriever():
    """Return an empty retrieval result so Qdrant is not hit."""
    with patch("app.api.v1.endpoints.query.retrieve") as m:
        m.return_value = MagicMock(chunks=[], rewritten_query="test query", retrieval_ms=5)
        yield m


@pytest.fixture
def mocked_generator():
    """Return a minimal GenerationChunk stream from the generator."""
    from app.services.generator import GenerationChunk

    async def _fake_stream(*args, **kwargs):
        qid = str(uuid.uuid4())
        yield GenerationChunk(delta="Hello world", done=False, query_id=qid)
        yield GenerationChunk(delta="", done=True, sources=[], query_id=qid, usage={})

    with patch("app.api.v1.endpoints.query.generate_stream") as m:
        m.side_effect = _fake_stream
        yield m


# ── Helper to collect SSE lines ───────────────────────────────────────────────

async def _collect_sse(client, payload: dict, headers: dict) -> list[dict]:
    """POST /v1/query and collect all parsed SSE events."""
    events = []
    async with client.stream("POST", "/v1/query", json=payload, headers=headers) as resp:
        current_event: dict = {}
        async for line in resp.aiter_lines():
            line = line.strip()
            if line.startswith("event:"):
                current_event["event"] = line.split(":", 1)[1].strip()
            elif line.startswith("data:"):
                raw = line.split(":", 1)[1].strip()
                try:
                    current_event["data"] = json.loads(raw)
                except json.JSONDecodeError:
                    current_event["data"] = raw
            elif line == "" and current_event:
                events.append(current_event)
                current_event = {}
    return events


# ── Tests ─────────────────────────────────────────────────────────────────────

class TestQuerySSE:
    async def test_query_content_type_is_sse(
        self, client, auth_headers, session_id, mocked_retriever, mocked_generator
    ):
        async with client.stream(
            "POST", "/v1/query",
            json={"session_id": session_id, "question": "What is the refund policy?"},
            headers=auth_headers,
        ) as resp:
            assert "text/event-stream" in resp.headers.get("content-type", "")

    async def test_query_emits_done_event(
        self, client, auth_headers, session_id, mocked_retriever, mocked_generator
    ):
        events = await _collect_sse(
            client,
            {"session_id": session_id, "question": "What is the refund policy?"},
            auth_headers,
        )
        event_types = [e.get("event") for e in events]
        assert "done" in event_types

    async def test_done_event_has_query_id(
        self, client, auth_headers, session_id, mocked_retriever, mocked_generator
    ):
        events = await _collect_sse(
            client,
            {"session_id": session_id, "question": "What is the refund policy?"},
            auth_headers,
        )
        done_events = [e for e in events if e.get("event") == "done"]
        assert done_events, "No 'done' event found"
        query_id = done_events[0]["data"].get("query_id")
        assert query_id is not None
        uuid.UUID(query_id)  # must be a valid UUID

    async def test_query_no_auth_returns_401(self, client, session_id):
        async with client.stream(
            "POST", "/v1/query",
            json={"session_id": session_id, "question": "Hello?"},
        ) as resp:
            assert resp.status_code == 401

    async def test_query_invalid_session_emits_error_event(
        self, client, auth_headers
    ):
        events = await _collect_sse(
            client,
            {"session_id": str(uuid.uuid4()), "question": "Hello?"},
            auth_headers,
        )
        event_types = [e.get("event") for e in events]
        assert "error" in event_types

    async def test_query_empty_question_returns_422(self, client, auth_headers, session_id):
        async with client.stream(
            "POST", "/v1/query",
            json={"session_id": session_id, "question": ""},
            headers=auth_headers,
        ) as resp:
            assert resp.status_code == 422

    async def test_query_question_too_long_returns_422(self, client, auth_headers, session_id):
        async with client.stream(
            "POST", "/v1/query",
            json={"session_id": session_id, "question": "x" * 4097},
            headers=auth_headers,
        ) as resp:
            assert resp.status_code == 422
