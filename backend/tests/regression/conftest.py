"""Regression-test fixtures: auth helpers and per-test session management."""
import uuid

import pytest
import pytest_asyncio


@pytest_asyncio.fixture(scope="session")
async def registered_user(client):
    """Register a unique test user once per session. Yields auth payload dict."""
    suffix = uuid.uuid4().hex[:8]
    payload = {
        "username": f"testregr_{suffix}",
        "email":    f"testregr_{suffix}@example.com",
        "password": "Regression1234!",
    }
    resp = await client.post("/v1/auth/register", json=payload)
    assert resp.status_code == 201, resp.text
    data = resp.json()
    return {**data, "password": payload["password"], "email": payload["email"]}


@pytest.fixture(scope="session")
def auth_headers(registered_user):
    return {"Authorization": f"Bearer {registered_user['access_token']}"}


@pytest_asyncio.fixture
async def session_id(client, auth_headers):
    """Create a fresh session before the test and close it after."""
    resp = await client.post("/v1/sessions", headers=auth_headers)
    assert resp.status_code == 201, resp.text
    sid = resp.json()["session_id"]
    yield sid
    await client.delete(f"/v1/sessions/{sid}", headers=auth_headers)
