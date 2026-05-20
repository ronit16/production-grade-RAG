"""Regression tests: document upload and status polling."""
import uuid
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

FIXTURE_FILE = Path(__file__).parent / "fixtures" / "sample.txt"


@pytest.fixture(autouse=True)
def mock_celery_task():
    """Prevent real Celery dispatch — we only test the HTTP layer here."""
    with patch("app.api.v1.endpoints.documents.process_document") as m:
        m.delay.return_value = MagicMock(id="fake-celery-task-id")
        yield m


def _txt_file():
    content = FIXTURE_FILE.read_bytes()
    return ("file", (FIXTURE_FILE.name, content, "text/plain"))


class TestDocumentUpload:
    async def test_upload_returns_202(self, client, auth_headers):
        resp = await client.post(
            "/v1/documents",
            files={"file": _txt_file()[1]},
            headers=auth_headers,
        )
        assert resp.status_code == 202

    async def test_upload_response_has_document_id(self, client, auth_headers):
        data = (await client.post(
            "/v1/documents",
            files={"file": _txt_file()[1]},
            headers=auth_headers,
        )).json()
        assert "document_id" in data
        uuid.UUID(data["document_id"])  # valid UUID

    async def test_upload_status_is_processing(self, client, auth_headers):
        data = (await client.post(
            "/v1/documents",
            files={"file": _txt_file()[1]},
            headers=auth_headers,
        )).json()
        assert data["status"] == "processing"

    async def test_upload_filename_in_response(self, client, auth_headers):
        data = (await client.post(
            "/v1/documents",
            files={"file": _txt_file()[1]},
            headers=auth_headers,
        )).json()
        assert data.get("filename") == FIXTURE_FILE.name

    async def test_upload_no_auth_returns_401(self, client):
        resp = await client.post(
            "/v1/documents",
            files={"file": _txt_file()[1]},
        )
        assert resp.status_code == 401

    async def test_upload_unsupported_type_returns_415(self, client, auth_headers):
        resp = await client.post(
            "/v1/documents",
            files={"file": ("evil.exe", b"\x4d\x5a\x00", "application/octet-stream")},
            headers=auth_headers,
        )
        assert resp.status_code == 415


class TestDocumentStatus:
    async def test_get_status_returns_200(self, client, auth_headers):
        doc_id = (await client.post(
            "/v1/documents",
            files={"file": _txt_file()[1]},
            headers=auth_headers,
        )).json()["document_id"]

        resp = await client.get(f"/v1/documents/{doc_id}", headers=auth_headers)
        assert resp.status_code == 200

    async def test_get_status_response_fields(self, client, auth_headers):
        doc_id = (await client.post(
            "/v1/documents",
            files={"file": _txt_file()[1]},
            headers=auth_headers,
        )).json()["document_id"]

        data = (await client.get(f"/v1/documents/{doc_id}", headers=auth_headers)).json()
        assert "document_id" in data
        assert "filename" in data
        assert "status" in data

    async def test_get_unknown_document_returns_404(self, client, auth_headers):
        resp = await client.get(f"/v1/documents/{uuid.uuid4()}", headers=auth_headers)
        assert resp.status_code == 404

    async def test_get_document_no_auth_returns_401(self, client, auth_headers):
        doc_id = (await client.post(
            "/v1/documents",
            files={"file": _txt_file()[1]},
            headers=auth_headers,
        )).json()["document_id"]
        resp = await client.get(f"/v1/documents/{doc_id}")
        assert resp.status_code == 401

    async def test_cross_tenant_document_returns_404(self, client, registered_user):
        """User B cannot read User A's document (tenant isolation)."""
        suffix = uuid.uuid4().hex[:8]
        resp_b = await client.post("/v1/auth/register", json={
            "username": f"docsb_{suffix}",
            "email":    f"docsb_{suffix}@regression.test",
            "password": "ValidPass1234!",
        })
        headers_b = {"Authorization": f"Bearer {resp_b.json()['access_token']}"}
        headers_a = {"Authorization": f"Bearer {registered_user['access_token']}"}

        doc_id = (await client.post(
            "/v1/documents",
            files={"file": _txt_file()[1]},
            headers=headers_a,
        )).json()["document_id"]

        resp = await client.get(f"/v1/documents/{doc_id}", headers=headers_b)
        assert resp.status_code == 404

    @pytest.mark.slow
    async def test_document_eventually_becomes_ready(self, client, auth_headers):
        """Requires a running Celery worker and real OpenAI key."""
        import asyncio

        doc_id = (await client.post(
            "/v1/documents",
            files={"file": _txt_file()[1]},
            headers=auth_headers,
        )).json()["document_id"]

        for _ in range(30):
            data = (await client.get(f"/v1/documents/{doc_id}", headers=auth_headers)).json()
            if data["status"] == "ready":
                return
            await asyncio.sleep(1)
        pytest.fail(f"Document {doc_id} did not become ready within 30s")
