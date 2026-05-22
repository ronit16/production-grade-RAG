"""Fixtures for evaluation tests: auth helpers needed by the live slow test."""
import uuid

import pytest
import pytest_asyncio


@pytest_asyncio.fixture(scope="session")
async def registered_user(client):
    """Register a unique test user once per session. Returns auth payload dict."""
    suffix = uuid.uuid4().hex[:8]
    payload = {
        "username": f"testeval_{suffix}",
        "email":    f"testeval_{suffix}@example.com",
        "password": "Evaluation1234!",
    }
    resp = await client.post("/v1/auth/register", json=payload)
    assert resp.status_code == 201, resp.text
    data = resp.json()
    return {**data, "password": payload["password"], "email": payload["email"]}


@pytest.fixture(scope="session")
def auth_headers(registered_user):
    return {"Authorization": f"Bearer {registered_user['access_token']}"}
