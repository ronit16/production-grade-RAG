"""Regression tests: health, readiness, and detailed health endpoints."""
import pytest


class TestHealth:
    async def test_health_returns_200(self, client):
        resp = await client.get("/v1/health")
        assert resp.status_code == 200

    async def test_health_status_ok(self, client):
        data = (await client.get("/v1/health")).json()
        assert data["status"] == "ok"

    async def test_health_version_present(self, client):
        data = (await client.get("/v1/health")).json()
        assert "version" in data

    async def test_ready_returns_200(self, client):
        resp = await client.get("/v1/ready")
        assert resp.status_code == 200

    async def test_ready_status_field(self, client):
        data = (await client.get("/v1/ready")).json()
        assert data["status"] == "ready"

    async def test_detailed_health_returns_200(self, client):
        resp = await client.get("/v1/health/detailed")
        assert resp.status_code == 200

    async def test_detailed_health_all_services_ok(self, client):
        data = (await client.get("/v1/health/detailed")).json()
        assert data["status"] == "healthy"
        for svc in ("postgres", "redis", "rabbitmq", "qdrant", "minio"):
            assert data["checks"][svc]["status"] == "ok", (
                f"{svc} check failed: {data['checks'][svc]}"
            )

    async def test_detailed_health_latency_present(self, client):
        data = (await client.get("/v1/health/detailed")).json()
        for svc in ("postgres", "redis"):
            assert isinstance(data["checks"][svc]["latency_ms"], int)
            assert data["checks"][svc]["latency_ms"] >= 0

    async def test_detailed_health_schema_complete(self, client):
        data = (await client.get("/v1/health/detailed")).json()
        assert "status" in data
        assert "checks" in data
        assert "version" in data
        assert set(data["checks"].keys()) == {"postgres", "redis", "rabbitmq", "qdrant", "minio"}
