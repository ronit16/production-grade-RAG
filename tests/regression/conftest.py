"""Regression-test fixtures: auth helpers and per-test session management."""
import time
import uuid
from pathlib import Path

import jwt
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


# ── Multi-tenant fixtures ─────────────────────────────────────────────────────

@pytest_asyncio.fixture(scope="session")
async def tenant_b_user(client) -> dict:
    """Register a fully independent Tenant B for cross-tenant isolation tests."""
    suffix = uuid.uuid4().hex[:8]
    resp = await client.post("/v1/auth/register", json={
        "username": f"tenantb_{suffix}",
        "email":    f"tenantb_{suffix}@example.com",
        "password": "TenantB1234!",
    })
    assert resp.status_code == 201, resp.text
    return resp.json()


@pytest.fixture(scope="session")
def tenant_b_headers(tenant_b_user) -> dict:
    return {"Authorization": f"Bearer {tenant_b_user['access_token']}"}


# ── Multi-user fixtures ───────────────────────────────────────────────────────

@pytest_asyncio.fixture(scope="session")
async def second_user_same_tenant(registered_user) -> dict:
    """
    Insert a second user into the same tenant as registered_user.

    The register endpoint always creates a new tenant, so the only way to add a
    second user to an existing tenant is a direct DB insert + JWT mint.
    hashed_password=None is valid — User.hashed_password is nullable (SSO path).
    """
    from app.core.config import get_settings
    from app.core.database import AsyncSessionFactory
    from app.models.db import User

    settings = get_settings()
    tenant_id = uuid.UUID(registered_user["tenant_id"])
    user_id   = uuid.uuid4()
    suffix    = uuid.uuid4().hex[:8]

    async with AsyncSessionFactory() as db:
        db.add(User(
            id=user_id,
            tenant_id=tenant_id,
            username=f"member_{suffix}",
            email=f"member_{suffix}@example.com",
            role="member",
            hashed_password=None,
            is_active=True,
        ))
        await db.commit()

    with open(settings.JWT_PRIVATE_KEY_PATH) as fh:
        private_key = fh.read()

    token = jwt.encode(
        {
            "sub":       str(user_id),
            "tenant_id": str(tenant_id),
            "role":      "member",
            "exp":       int(time.time()) + 86400,
            "iat":       int(time.time()),
        },
        private_key,
        algorithm=settings.JWT_ALGORITHM,
    )
    return {
        "user_id":      str(user_id),
        "tenant_id":    str(tenant_id),
        "access_token": token,
        "role":         "member",
    }


@pytest.fixture(scope="session")
def member_headers(second_user_same_tenant) -> dict:
    return {"Authorization": f"Bearer {second_user_same_tenant['access_token']}"}


# ── Document fixture ──────────────────────────────────────────────────────────

@pytest.fixture(scope="session")
def tech_specs_fixture_path() -> Path:
    """
    Return path to tech_specs.txt in the fixtures directory.
    Downloads first 8 KB of RFC 7231 if the file is not already present;
    falls back to synthetic content if the network is unavailable.
    """
    target = Path(__file__).parent / "fixtures" / "tech_specs.txt"
    if target.exists():
        return target
    try:
        import httpx
        r = httpx.get(
            "https://www.rfc-editor.org/rfc/rfc7231.txt",
            timeout=10,
            follow_redirects=True,
        )
        r.raise_for_status()
        target.write_bytes(r.content[:8192])
    except Exception:
        target.write_text(
            "HTTP/1.1 Semantics and Content\n\n"
            "The GET method requests transfer of a current selected representation "
            "for the target resource. GET is the primary mechanism of information "
            "retrieval and the focus of almost all performance optimizations.\n\n"
            "The POST method requests that the target resource process the representation "
            "enclosed in the request according to the resource's own specific semantics.\n\n"
            "4xx (Client Error): The 4xx class of status code indicates that the client "
            "seems to have erred. 400 Bad Request. 401 Unauthorized. 404 Not Found. "
            "429 Too Many Requests.\n\n"
            "5xx (Server Error): The 5xx class indicates cases in which the server is "
            "aware that it has erred. 500 Internal Server Error. 503 Service Unavailable.\n"
        )
    return target
