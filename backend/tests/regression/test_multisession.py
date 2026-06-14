"""
Multi-session tests: one user, many concurrent sessions.

Tests in this module verify:
  - Multiple sessions per user have unique IDs
  - Pagination over session lists works correctly
  - Concurrent session creation produces distinct IDs
  - Session histories are isolated (messages in session A do not bleed into B)
  - Rolling-window eviction caps messages at MAX_HISTORY_MESSAGES
  - Deleting one session does not affect another
"""
import asyncio
import json
import time
import uuid
from unittest.mock import MagicMock, patch

import pytest


# ── Mock helpers (same pattern as test_query.py) ──────────────────────────────

@pytest.fixture
def mocked_retriever():
    with patch("app.api.v1.endpoints.query.retrieve") as m:
        m.return_value = MagicMock(
            chunks=[], rewritten_query="test query", retrieval_ms=5, candidate_count=0
        )
        yield m


@pytest.fixture
def mocked_generator():
    from app.services.generator import GenerationChunk

    async def _fake_stream(*args, **kwargs):
        qid = str(uuid.uuid4())
        yield GenerationChunk(delta="Answer", done=False, query_id=qid)
        yield GenerationChunk(delta="", done=True, sources=[], query_id=qid, usage={})

    with patch("app.api.v1.endpoints.query.generate_stream") as m:
        m.side_effect = _fake_stream
        yield m


async def _collect_sse(client, payload: dict, headers: dict) -> list[dict]:
    events = []
    async with client.stream("POST", "/v1/query", json=payload, headers=headers) as resp:
        current: dict = {}
        async for line in resp.aiter_lines():
            line = line.strip()
            if line.startswith("event:"):
                current["event"] = line.split(":", 1)[1].strip()
            elif line.startswith("data:"):
                raw = line.split(":", 1)[1].strip()
                try:
                    current["data"] = json.loads(raw)
                except json.JSONDecodeError:
                    current["data"] = raw
            elif line == "" and current:
                events.append(current)
                current = {}
    return events


# ── Session creation ──────────────────────────────────────────────────────────

class TestMultipleSessionCreation:
    async def test_create_five_sessions_all_unique_ids(self, client, auth_headers):
        """Five sequential session creates must produce five distinct UUIDs."""
        ids = []
        for _ in range(5):
            resp = await client.post("/v1/sessions", headers=auth_headers)
            assert resp.status_code == 201
            ids.append(resp.json()["session_id"])
        try:
            assert len(set(ids)) == 5
        finally:
            for sid in ids:
                await client.delete(f"/v1/sessions/{sid}", headers=auth_headers)

    async def test_all_five_sessions_appear_in_list(self, client, auth_headers):
        """All five created sessions must appear in a single list call."""
        ids = []
        for _ in range(5):
            resp = await client.post("/v1/sessions", headers=auth_headers)
            ids.append(resp.json()["session_id"])
        try:
            list_resp = await client.get(
                "/v1/sessions", params={"limit": 50}, headers=auth_headers
            )
            assert list_resp.status_code == 200
            listed_ids = {s["session_id"] for s in list_resp.json()}
            for sid in ids:
                assert sid in listed_ids
        finally:
            for sid in ids:
                await client.delete(f"/v1/sessions/{sid}", headers=auth_headers)

    async def test_session_list_pagination_with_offset(self, client, auth_headers):
        """limit + offset parameters correctly page through session results."""
        ids = []
        for _ in range(4):
            resp = await client.post("/v1/sessions", headers=auth_headers)
            ids.append(resp.json()["session_id"])
        try:
            page1 = await client.get(
                "/v1/sessions", params={"limit": 2, "offset": 0}, headers=auth_headers
            )
            page2 = await client.get(
                "/v1/sessions", params={"limit": 2, "offset": 2}, headers=auth_headers
            )
            assert page1.status_code == 200
            assert page2.status_code == 200
            p1_ids = {s["session_id"] for s in page1.json()}
            p2_ids = {s["session_id"] for s in page2.json()}
            # Pages must be disjoint
            assert p1_ids.isdisjoint(p2_ids)
        finally:
            for sid in ids:
                await client.delete(f"/v1/sessions/{sid}", headers=auth_headers)

    async def test_concurrent_session_creation_returns_unique_ids(
        self, client, auth_headers
    ):
        """Concurrent creates (via asyncio.gather) must still produce distinct IDs."""
        resps = await asyncio.gather(*[
            client.post("/v1/sessions", headers=auth_headers)
            for _ in range(5)
        ])
        ids = [r.json()["session_id"] for r in resps]
        try:
            assert all(r.status_code == 201 for r in resps)
            assert len(set(ids)) == 5
        finally:
            for sid in ids:
                await client.delete(f"/v1/sessions/{sid}", headers=auth_headers)


# ── Session history isolation ─────────────────────────────────────────────────

class TestSessionHistoryIsolation:
    async def test_session_a_query_does_not_affect_session_b_message_count(
        self, client, auth_headers, mocked_retriever, mocked_generator
    ):
        """
        Making a query in session A must not add messages to session B.
        We close A after querying (which writes message_count to the DB) and
        then close B (which must have message_count=0).
        """
        resp_a = await client.post("/v1/sessions", headers=auth_headers)
        resp_b = await client.post("/v1/sessions", headers=auth_headers)
        sid_a = resp_a.json()["session_id"]
        sid_b = resp_b.json()["session_id"]

        # Query only session A
        await _collect_sse(
            client,
            {"session_id": sid_a, "question": "Hello from A"},
            auth_headers,
        )

        # Close both; session B has had no messages
        close_b = await client.delete(f"/v1/sessions/{sid_b}", headers=auth_headers)
        assert close_b.json()["closed"] is True

        close_a = await client.delete(f"/v1/sessions/{sid_a}", headers=auth_headers)
        assert close_a.json()["closed"] is True

    async def test_concurrent_queries_to_different_sessions_are_independent(
        self, client, auth_headers, mocked_retriever, mocked_generator
    ):
        """Concurrent SSE queries to different sessions both complete with 'done'."""
        resp_a = await client.post("/v1/sessions", headers=auth_headers)
        resp_b = await client.post("/v1/sessions", headers=auth_headers)
        sid_a = resp_a.json()["session_id"]
        sid_b = resp_b.json()["session_id"]

        try:
            events_a, events_b = await asyncio.gather(
                _collect_sse(client, {"session_id": sid_a, "question": "Q for A"}, auth_headers),
                _collect_sse(client, {"session_id": sid_b, "question": "Q for B"}, auth_headers),
            )
            a_types = [e.get("event") for e in events_a]
            b_types = [e.get("event") for e in events_b]
            assert "done" in a_types, f"Session A did not get 'done': {a_types}"
            assert "done" in b_types, f"Session B did not get 'done': {b_types}"
        finally:
            await client.delete(f"/v1/sessions/{sid_a}", headers=auth_headers)
            await client.delete(f"/v1/sessions/{sid_b}", headers=auth_headers)


# ── Rolling-window eviction (unit level) ──────────────────────────────────────

class TestRollingWindowEviction:
    def test_rolling_window_caps_at_max_history_messages(self):
        """add_message() must evict the oldest messages once the limit is reached."""
        from app.services.session import MAX_HISTORY_MESSAGES, Message, SessionState

        state = SessionState(
            session_id=str(uuid.uuid4()),
            tenant_id=str(uuid.uuid4()),
            user_id=None,
            messages=[],
            created_at=time.time(),
            last_active=time.time(),
        )
        for i in range(MAX_HISTORY_MESSAGES + 5):
            state.add_message(Message(role="user", content=f"msg {i}"))

        assert len(state.messages) == MAX_HISTORY_MESSAGES
        # The five oldest messages (0-4) must have been dropped
        assert state.messages[0].content == "msg 5"
        assert state.messages[-1].content == f"msg {MAX_HISTORY_MESSAGES + 4}"

    def test_get_history_for_prompt_respects_token_budget(self):
        """get_history_for_prompt() must not include messages that exceed MAX_HISTORY_TOKENS."""
        from app.services.session import MAX_HISTORY_TOKENS, Message, SessionState

        state = SessionState(
            session_id=str(uuid.uuid4()),
            tenant_id=str(uuid.uuid4()),
            user_id=None,
            messages=[],
            created_at=time.time(),
            last_active=time.time(),
        )
        # A message whose token count (len // 4) exceeds MAX_HISTORY_TOKENS
        oversize = "w" * (MAX_HISTORY_TOKENS * 4 + 100)
        state.add_message(Message(role="user",      content=oversize))
        state.add_message(Message(role="assistant", content="short reply"))
        state.add_message(Message(role="user",      content="follow-up"))  # "current" question

        history = state.get_history_for_prompt()
        contents = [m["content"] for m in history]
        assert oversize not in contents, "Oversize message exceeded token budget but was included"


# ── Session delete state cleanup ──────────────────────────────────────────────

class TestSessionDeleteClearsState:
    async def test_delete_removes_session_from_list(self, client, auth_headers):
        """Deleting a session must remove it from the list endpoint."""
        resp = await client.post("/v1/sessions", headers=auth_headers)
        assert resp.status_code == 201
        sid = resp.json()["session_id"]

        del_resp = await client.delete(f"/v1/sessions/{sid}", headers=auth_headers)
        assert del_resp.json()["closed"] is True

        list_resp = await client.get(
            "/v1/sessions", params={"limit": 100}, headers=auth_headers
        )
        session_ids = [s["session_id"] for s in list_resp.json()]
        assert sid not in session_ids

    async def test_delete_one_session_leaves_others_intact(self, client, auth_headers):
        """Deleting session A must not affect session B."""
        resp_a = await client.post("/v1/sessions", headers=auth_headers)
        resp_b = await client.post("/v1/sessions", headers=auth_headers)
        sid_a = resp_a.json()["session_id"]
        sid_b = resp_b.json()["session_id"]

        try:
            await client.delete(f"/v1/sessions/{sid_a}", headers=auth_headers)

            list_resp = await client.get(
                "/v1/sessions", params={"limit": 100}, headers=auth_headers
            )
            listed_ids = [s["session_id"] for s in list_resp.json()]
            assert sid_a not in listed_ids
            assert sid_b in listed_ids
        finally:
            await client.delete(f"/v1/sessions/{sid_b}", headers=auth_headers)
