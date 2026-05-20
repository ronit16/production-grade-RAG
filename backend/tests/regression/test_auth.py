"""Regression tests: auth register and login flows."""
import uuid

import pytest


def _unique_user():
    suffix = uuid.uuid4().hex[:8]
    return {
        "username": f"testauth_{suffix}",
        "email":    f"testauth_{suffix}@regression.test",
        "password": "ValidPass1234!",
    }


class TestRegister:
    async def test_register_returns_201(self, client):
        resp = await client.post("/v1/auth/register", json=_unique_user())
        assert resp.status_code == 201

    async def test_register_response_has_token(self, client):
        data = (await client.post("/v1/auth/register", json=_unique_user())).json()
        assert "access_token" in data
        assert len(data["access_token"]) > 20

    async def test_register_response_has_user_id_and_tenant_id(self, client):
        data = (await client.post("/v1/auth/register", json=_unique_user())).json()
        assert "user_id" in data
        assert "tenant_id" in data
        # both should be valid UUID strings
        uuid.UUID(data["user_id"])
        uuid.UUID(data["tenant_id"])

    async def test_register_token_type_is_bearer(self, client):
        data = (await client.post("/v1/auth/register", json=_unique_user())).json()
        assert data.get("token_type") == "bearer"

    async def test_register_duplicate_email_returns_400(self, client):
        user = _unique_user()
        await client.post("/v1/auth/register", json=user)
        # second attempt with same email, different username
        dup = {**user, "username": f"other_{uuid.uuid4().hex[:6]}"}
        resp = await client.post("/v1/auth/register", json=dup)
        assert resp.status_code == 400

    async def test_register_duplicate_username_returns_400(self, client):
        user = _unique_user()
        await client.post("/v1/auth/register", json=user)
        dup = {**user, "email": f"other_{uuid.uuid4().hex[:6]}@regression.test"}
        resp = await client.post("/v1/auth/register", json=dup)
        assert resp.status_code == 400

    async def test_register_short_password_returns_422(self, client):
        user = {**_unique_user(), "password": "short"}
        resp = await client.post("/v1/auth/register", json=user)
        assert resp.status_code == 422

    async def test_register_short_username_returns_422(self, client):
        user = {**_unique_user(), "username": "ab"}
        resp = await client.post("/v1/auth/register", json=user)
        assert resp.status_code == 422

    async def test_register_invalid_email_returns_422(self, client):
        user = {**_unique_user(), "email": "not-an-email"}
        resp = await client.post("/v1/auth/register", json=user)
        assert resp.status_code == 422


class TestLogin:
    async def test_login_returns_200(self, client):
        user = _unique_user()
        await client.post("/v1/auth/register", json=user)
        resp = await client.post("/v1/auth/login", json={
            "email": user["email"], "password": user["password"]
        })
        assert resp.status_code == 200

    async def test_login_returns_bearer_token(self, client):
        user = _unique_user()
        await client.post("/v1/auth/register", json=user)
        data = (await client.post("/v1/auth/login", json={
            "email": user["email"], "password": user["password"]
        })).json()
        assert data.get("token_type") == "bearer"
        assert len(data.get("access_token", "")) > 20

    async def test_login_wrong_password_returns_401(self, client):
        user = _unique_user()
        await client.post("/v1/auth/register", json=user)
        resp = await client.post("/v1/auth/login", json={
            "email": user["email"], "password": "WrongPassword99!"
        })
        assert resp.status_code == 401

    async def test_login_unknown_email_returns_401(self, client):
        resp = await client.post("/v1/auth/login", json={
            "email": f"nobody_{uuid.uuid4().hex[:8]}@regression.test",
            "password": "SomePassword123!",
        })
        assert resp.status_code == 401
