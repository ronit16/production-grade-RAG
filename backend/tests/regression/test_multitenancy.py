"""
Integration tests: HTTP-layer cross-tenant isolation.

These tests register two independent tenants (Tenant A = registered_user,
Tenant B = tenant_b_user) and verify that no data leaks across the
tenant boundary at the HTTP / database / Redis layers.

Qdrant-level isolation is already covered in tests/integration/test_tenant_isolation.py.
"""
import uuid
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

FIXTURE_FILE = Path(__file__).parent / "fixtures" / "sample.txt"


@pytest.fixture(autouse=True)
def mock_celery_task():
    """Prevent real Celery dispatch for document upload tests."""
    with patch("app.api.v1.endpoints.documents.process_document") as m:
        m.delay.return_value = MagicMock(id="fake-celery-task-id")
        yield m


def _txt_file():
    content = FIXTURE_FILE.read_bytes()
    return (FIXTURE_FILE.name, content, "text/plain")


# ── Cross-tenant document isolation ──────────────────────────────────────────

@pytest.mark.integration
class TestCrossTenantDocumentIsolation:
    async def test_tenant_a_doc_not_visible_to_tenant_b(
        self, client, auth_headers, tenant_b_headers
    ):
        """Tenant B cannot read a document that belongs to Tenant A."""
        resp = await client.post(
            "/v1/documents",
            files={"file": _txt_file()},
            headers=auth_headers,
        )
        assert resp.status_code == 202
        doc_id = resp.json()["document_id"]

        resp_b = await client.get(f"/v1/documents/{doc_id}", headers=tenant_b_headers)
        assert resp_b.status_code == 404

    async def test_tenant_b_doc_not_visible_to_tenant_a(
        self, client, auth_headers, tenant_b_headers
    ):
        """Tenant A cannot read a document that belongs to Tenant B."""
        resp = await client.post(
            "/v1/documents",
            files={"file": _txt_file()},
            headers=tenant_b_headers,
        )
        assert resp.status_code == 202
        doc_id = resp.json()["document_id"]

        resp_a = await client.get(f"/v1/documents/{doc_id}", headers=auth_headers)
        assert resp_a.status_code == 404


# ── Cross-tenant session isolation ────────────────────────────────────────────

@pytest.mark.integration
class TestCrossTenantSessionIsolation:
    async def test_tenant_a_session_not_listed_for_tenant_b(
        self, client, auth_headers, tenant_b_headers
    ):
        """Tenant B's session list must not include Tenant A's sessions."""
        resp = await client.post("/v1/sessions", headers=auth_headers)
        assert resp.status_code == 201
        sid = resp.json()["session_id"]
        try:
            list_resp = await client.get("/v1/sessions", headers=tenant_b_headers)
            assert list_resp.status_code == 200
            session_ids = [s["session_id"] for s in list_resp.json()]
            assert sid not in session_ids
        finally:
            await client.delete(f"/v1/sessions/{sid}", headers=auth_headers)

    async def test_tenant_b_session_not_listed_for_tenant_a(
        self, client, auth_headers, tenant_b_headers
    ):
        """Tenant A's session list must not include Tenant B's sessions."""
        resp = await client.post("/v1/sessions", headers=tenant_b_headers)
        assert resp.status_code == 201
        sid = resp.json()["session_id"]
        try:
            list_resp = await client.get("/v1/sessions", headers=auth_headers)
            assert list_resp.status_code == 200
            session_ids = [s["session_id"] for s in list_resp.json()]
            assert sid not in session_ids
        finally:
            await client.delete(f"/v1/sessions/{sid}", headers=tenant_b_headers)

    async def test_tenant_a_cannot_delete_tenant_b_session(
        self, client, auth_headers, tenant_b_headers
    ):
        """Tenant A using Tenant B's session_id gets 404 (different Redis namespace)."""
        resp = await client.post("/v1/sessions", headers=tenant_b_headers)
        assert resp.status_code == 201
        sid = resp.json()["session_id"]
        try:
            del_resp = await client.delete(f"/v1/sessions/{sid}", headers=auth_headers)
            assert del_resp.status_code == 404
        finally:
            await client.delete(f"/v1/sessions/{sid}", headers=tenant_b_headers)

    async def test_tenant_b_cannot_delete_tenant_a_session(
        self, client, auth_headers, tenant_b_headers
    ):
        """Tenant B using Tenant A's session_id gets 404 (different Redis namespace)."""
        resp = await client.post("/v1/sessions", headers=auth_headers)
        assert resp.status_code == 201
        sid = resp.json()["session_id"]
        try:
            del_resp = await client.delete(f"/v1/sessions/{sid}", headers=tenant_b_headers)
            assert del_resp.status_code == 404
        finally:
            await client.delete(f"/v1/sessions/{sid}", headers=auth_headers)


# ── Cross-tenant query isolation ──────────────────────────────────────────────

@pytest.mark.integration
class TestCrossTenantQueryIsolation:
    async def test_query_ctx_tenant_id_matches_requesting_tenant(
        self, client, auth_headers, registered_user, session_id
    ):
        """
        The retrieve() call must receive the requesting user's tenant_id, not
        any other tenant's.  We patch retrieve at the endpoint import level and
        capture the ctx argument.
        """
        from app.services.generator import GenerationChunk

        captured: list[str] = []

        async def _fake_retrieve(question, ctx, **kwargs):
            captured.append(str(ctx.tenant_id))
            return MagicMock(
                chunks=[],
                rewritten_query=question,
                retrieval_ms=1,
                candidate_count=0,
            )

        async def _fake_stream(gen_req, ctx):
            qid = str(uuid.uuid4())
            yield GenerationChunk(delta="ok", done=False, query_id=qid)
            yield GenerationChunk(delta="", done=True, sources=[], query_id=qid, usage={})

        with patch("app.api.v1.endpoints.query.retrieve", side_effect=_fake_retrieve), \
             patch("app.api.v1.endpoints.query.generate_stream", side_effect=_fake_stream):
            async with client.stream(
                "POST", "/v1/query",
                json={"session_id": session_id, "question": "What is this?"},
                headers=auth_headers,
            ) as resp:
                async for _ in resp.aiter_lines():
                    pass

        assert len(captured) == 1
        assert captured[0] == registered_user["tenant_id"]
