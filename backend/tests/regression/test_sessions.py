"""Regression tests: session create, list, and delete flows."""
import uuid

import pytest


class TestCreateSession:
    async def test_create_session_returns_201(self, client, auth_headers):
        resp = await client.post("/v1/sessions", headers=auth_headers)
        assert resp.status_code == 201

    async def test_create_session_has_session_id(self, client, auth_headers):
        data = (await client.post("/v1/sessions", headers=auth_headers)).json()
        assert "session_id" in data
        uuid.UUID(data["session_id"])  # must be a valid UUID

    async def test_create_session_has_created_at(self, client, auth_headers):
        data = (await client.post("/v1/sessions", headers=auth_headers)).json()
        assert "created_at" in data

    async def test_create_session_ids_are_unique(self, client, auth_headers):
        sid1 = (await client.post("/v1/sessions", headers=auth_headers)).json()["session_id"]
        sid2 = (await client.post("/v1/sessions", headers=auth_headers)).json()["session_id"]
        assert sid1 != sid2
        # cleanup
        await client.delete(f"/v1/sessions/{sid1}", headers=auth_headers)
        await client.delete(f"/v1/sessions/{sid2}", headers=auth_headers)

    async def test_create_session_no_auth_returns_401(self, client):
        resp = await client.post("/v1/sessions")
        assert resp.status_code == 401


class TestListSessions:
    async def test_list_sessions_returns_200(self, client, auth_headers, session_id):
        resp = await client.get("/v1/sessions", headers=auth_headers)
        assert resp.status_code == 200

    async def test_list_sessions_returns_list(self, client, auth_headers, session_id):
        data = (await client.get("/v1/sessions", headers=auth_headers)).json()
        assert isinstance(data, list)

    async def test_list_sessions_pagination_limit(self, client, auth_headers, session_id):
        resp = await client.get("/v1/sessions?limit=1&offset=0", headers=auth_headers)
        assert resp.status_code == 200
        assert len(resp.json()) <= 1

    async def test_list_sessions_no_auth_returns_401(self, client):
        resp = await client.get("/v1/sessions")
        assert resp.status_code == 401


class TestDeleteSession:
    async def test_delete_session_returns_200(self, client, auth_headers):
        sid = (await client.post("/v1/sessions", headers=auth_headers)).json()["session_id"]
        resp = await client.delete(f"/v1/sessions/{sid}", headers=auth_headers)
        assert resp.status_code == 200

    async def test_delete_session_closed_true(self, client, auth_headers):
        sid = (await client.post("/v1/sessions", headers=auth_headers)).json()["session_id"]
        data = (await client.delete(f"/v1/sessions/{sid}", headers=auth_headers)).json()
        assert data.get("closed") is True

    async def test_deleted_session_not_in_list(self, client, auth_headers):
        sid = (await client.post("/v1/sessions", headers=auth_headers)).json()["session_id"]
        await client.delete(f"/v1/sessions/{sid}", headers=auth_headers)
        sessions = (await client.get("/v1/sessions", headers=auth_headers)).json()
        ids = [s.get("session_id") for s in sessions]
        assert sid not in ids

    async def test_delete_nonexistent_session_returns_404(self, client, auth_headers):
        resp = await client.delete(f"/v1/sessions/{uuid.uuid4()}", headers=auth_headers)
        assert resp.status_code == 404

    async def test_delete_other_users_session_returns_404(self, client, registered_user):
        """User B cannot delete User A's session."""
        import uuid as _uuid
        suffix = _uuid.uuid4().hex[:8]
        # Register user B
        resp_b = await client.post("/v1/auth/register", json={
            "username": f"userb_{suffix}",
            "email":    f"userb_{suffix}@example.com",
            "password": "ValidPass1234!",
        })
        token_b = resp_b.json()["access_token"]
        headers_b = {"Authorization": f"Bearer {token_b}"}

        # User A creates a session
        headers_a = {"Authorization": f"Bearer {registered_user['access_token']}"}
        sid_a = (await client.post("/v1/sessions", headers=headers_a)).json()["session_id"]

        # User B tries to delete it
        resp = await client.delete(f"/v1/sessions/{sid_a}", headers=headers_b)
        assert resp.status_code in (403, 404)

        # cleanup
        await client.delete(f"/v1/sessions/{sid_a}", headers=headers_a)
