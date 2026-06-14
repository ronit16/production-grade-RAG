"""
Multi-user tests: two users in the same tenant.

The register endpoint always creates a new tenant, so the second_user_same_tenant
fixture inserts a second User row directly into the DB and mints a JWT for it
(see regression/conftest.py).  Both users share the same tenant_id.

Key invariants being tested:
  - Sessions are user-scoped: User A cannot see or delete User B's sessions.
  - Documents are tenant-scoped: both users can see/upload to the shared corpus.
  - Role claim is correctly embedded in the member JWT.
"""
import uuid
from pathlib import Path
from unittest.mock import MagicMock, patch

import jwt
import pytest

FIXTURE_FILE = Path(__file__).parent / "fixtures" / "sample.txt"


@pytest.fixture(autouse=True)
def mock_celery_task():
    """Prevent real Celery dispatch so document tests don't require a worker."""
    with patch("app.api.v1.endpoints.documents.process_document") as m:
        m.delay.return_value = MagicMock(id="fake-celery-task-id")
        yield m


def _txt_file():
    content = FIXTURE_FILE.read_bytes()
    return (FIXTURE_FILE.name, content, "text/plain")


# ── Session isolation between users in the same tenant ───────────────────────

class TestMultiUserSessionIsolation:
    async def test_user_a_sessions_not_in_user_b_list(
        self, client, auth_headers, member_headers
    ):
        """Owner's sessions must not appear in the member's session list."""
        resp = await client.post("/v1/sessions", headers=auth_headers)
        assert resp.status_code == 201
        sid = resp.json()["session_id"]
        try:
            list_resp = await client.get("/v1/sessions", headers=member_headers)
            assert list_resp.status_code == 200
            session_ids = [s["session_id"] for s in list_resp.json()]
            assert sid not in session_ids
        finally:
            await client.delete(f"/v1/sessions/{sid}", headers=auth_headers)

    async def test_user_b_sessions_not_in_user_a_list(
        self, client, auth_headers, member_headers
    ):
        """Member's sessions must not appear in the owner's session list."""
        resp = await client.post("/v1/sessions", headers=member_headers)
        assert resp.status_code == 201
        sid = resp.json()["session_id"]
        try:
            list_resp = await client.get("/v1/sessions", headers=auth_headers)
            assert list_resp.status_code == 200
            session_ids = [s["session_id"] for s in list_resp.json()]
            assert sid not in session_ids
        finally:
            await client.delete(f"/v1/sessions/{sid}", headers=member_headers)

    async def test_user_b_cannot_delete_user_a_session(
        self, client, auth_headers, member_headers
    ):
        """Member gets 403 when trying to close the owner's session (same tenant)."""
        resp = await client.post("/v1/sessions", headers=auth_headers)
        assert resp.status_code == 201
        sid = resp.json()["session_id"]
        try:
            del_resp = await client.delete(f"/v1/sessions/{sid}", headers=member_headers)
            assert del_resp.status_code == 403
        finally:
            await client.delete(f"/v1/sessions/{sid}", headers=auth_headers)

    async def test_owner_and_member_session_lists_are_disjoint(
        self, client, auth_headers, member_headers
    ):
        """Owner sees only their own sessions; member sees only theirs."""
        resp_a = await client.post("/v1/sessions", headers=auth_headers)
        sid_a = resp_a.json()["session_id"]
        resp_b = await client.post("/v1/sessions", headers=member_headers)
        sid_b = resp_b.json()["session_id"]
        try:
            owner_ids  = [s["session_id"] for s in
                          (await client.get("/v1/sessions", headers=auth_headers)).json()]
            member_ids = [s["session_id"] for s in
                          (await client.get("/v1/sessions", headers=member_headers)).json()]
            assert sid_a in owner_ids
            assert sid_b not in owner_ids
            assert sid_b in member_ids
            assert sid_a not in member_ids
        finally:
            await client.delete(f"/v1/sessions/{sid_a}", headers=auth_headers)
            await client.delete(f"/v1/sessions/{sid_b}", headers=member_headers)


# ── Document visibility within the same tenant ────────────────────────────────

class TestMultiUserDocumentVisibility:
    async def test_user_a_document_visible_to_user_b_same_tenant(
        self, client, auth_headers, member_headers
    ):
        """Documents are tenant-scoped — member can GET owner's document."""
        resp = await client.post(
            "/v1/documents",
            files={"file": _txt_file()},
            headers=auth_headers,
        )
        assert resp.status_code == 202
        doc_id = resp.json()["document_id"]

        resp_b = await client.get(f"/v1/documents/{doc_id}", headers=member_headers)
        assert resp_b.status_code == 200

    async def test_member_can_upload_document(self, client, member_headers):
        """member role is listed in require_role() — upload must succeed."""
        resp = await client.post(
            "/v1/documents",
            files={"file": _txt_file()},
            headers=member_headers,
        )
        assert resp.status_code == 202


# ── Role claim correctness ────────────────────────────────────────────────────

class TestMultiUserRoleDifferences:
    def test_member_token_has_correct_role_claim(self, second_user_same_tenant):
        """The minted JWT must carry role='member'."""
        token = second_user_same_tenant["access_token"]
        payload = jwt.decode(token, options={"verify_signature": False})
        assert payload["role"] == "member"

    def test_member_token_tenant_id_matches_owner(
        self, registered_user, second_user_same_tenant
    ):
        """Both users share the same tenant_id."""
        assert second_user_same_tenant["tenant_id"] == registered_user["tenant_id"]

    async def test_member_can_create_session(self, client, member_headers):
        """member role can create sessions."""
        resp = await client.post("/v1/sessions", headers=member_headers)
        assert resp.status_code == 201
        sid = resp.json()["session_id"]
        await client.delete(f"/v1/sessions/{sid}", headers=member_headers)
