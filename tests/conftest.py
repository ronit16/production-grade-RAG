"""
Root conftest — starts real Docker containers for regression tests.

IMPORTANT: All imports from app.* must be INSIDE functions or fixtures,
never at module level. pytest_configure runs before any test module is
imported; setting os.environ here ensures Settings reads container URLs.
"""
import asyncio
import os
import time
import uuid

import boto3
import httpx
import pytest
import pytest_asyncio


# ─────────────────────────────────────────────────────────────────────────────
# Container lifecycle — runs once per test session
# ─────────────────────────────────────────────────────────────────────────────

def _wait_http(url: str, timeout: int = 30) -> None:
    """Poll url until it returns 2xx or timeout elapses."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            r = httpx.get(url, timeout=2)
            if r.status_code < 300:
                return
        except Exception:
            pass
        time.sleep(0.5)
    raise RuntimeError(f"Service at {url} did not become ready within {timeout}s")


def _wait_tcp(host: str, port: int, timeout: int = 30) -> None:
    """Poll TCP connection until it succeeds."""
    import socket
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            with socket.create_connection((host, port), timeout=1):
                return
        except OSError:
            pass
        time.sleep(0.5)
    raise RuntimeError(f"TCP {host}:{port} not ready within {timeout}s")


def pytest_configure(config: pytest.Config) -> None:
    """
    Start containers and inject URLs into os.environ BEFORE any app module
    is imported (module-level get_settings() calls in database.py, retriever.py, etc.).
    """
    # Allow skipping containers for pure unit tests
    if config.getoption("--no-containers", default=False):
        return

    from testcontainers.core.container import DockerContainer
    from testcontainers.postgres import PostgresContainer
    from testcontainers.redis import RedisContainer

    # PostgreSQL
    pg = PostgresContainer("postgres:15", driver="asyncpg")
    pg.start()

    # Redis
    redis_c = RedisContainer("redis:7")
    redis_c.start()

    # Qdrant
    qdrant_c = DockerContainer("qdrant/qdrant:latest")
    qdrant_c.with_exposed_ports(6333)
    qdrant_c.start()
    qdrant_host = qdrant_c.get_container_host_ip()
    qdrant_port = qdrant_c.get_exposed_port(6333)
    _wait_http(f"http://{qdrant_host}:{qdrant_port}/healthz")

    # MinIO
    minio_c = (
        DockerContainer("minio/minio:latest")
        .with_command("server /data --console-address :9001")
        .with_env("MINIO_ROOT_USER", "minioadmin")
        .with_env("MINIO_ROOT_PASSWORD", "minioadmin")
        .with_exposed_ports(9000)
    )
    minio_c.start()
    minio_host = minio_c.get_container_host_ip()
    minio_port = minio_c.get_exposed_port(9000)
    _wait_http(f"http://{minio_host}:{minio_port}/minio/health/live")

    # RabbitMQ
    rmq_c = DockerContainer("rabbitmq:3")
    rmq_c.with_exposed_ports(5672)
    rmq_c.start()
    rmq_host = rmq_c.get_container_host_ip()
    rmq_port = rmq_c.get_exposed_port(5672)
    _wait_tcp(rmq_host, int(rmq_port))

    redis_host = redis_c.get_container_host_ip()
    redis_port = redis_c.get_exposed_port(6379)

    # Inject container URLs — Settings (pydantic-settings) reads os.environ.
    # Preserve any real API keys already exported in the shell so that slow
    # evaluation tests (which need real LLM calls) work without modification.
    def _keep_or_stub(env_var: str, stub: str, stub_prefix: str = "") -> str:
        val = os.environ.get(env_var, "")
        if val and (not stub_prefix or not val.startswith(stub_prefix)):
            return val
        return stub

    os.environ.update({
        "APP_ENV":                   "test",
        "SECRET_KEY":                "test-secret-key-minimum-32-chars-x!",
        "DATABASE_URL":              pg.get_connection_url(),
        "REDIS_URL":                 f"redis://{redis_host}:{redis_port}/0",
        "QDRANT_URL":                f"http://{qdrant_host}:{qdrant_port}",
        "MINIO_ENDPOINT":            f"http://{minio_host}:{minio_port}",
        "MINIO_ACCESS_KEY":          "minioadmin",
        "MINIO_SECRET_KEY":          "minioadmin",
        "CELERY_BROKER_URL":         f"amqp://guest:guest@{rmq_host}:{rmq_port}//",
        "CELERY_RESULT_BACKEND":     f"redis://{redis_host}:{redis_port}/1",
        "OPENAI_API_KEY":            _keep_or_stub("OPENAI_API_KEY", "sk-test-fake-key-for-regression", "sk-test"),
        "GEMINI_API_KEY":            _keep_or_stub("GEMINI_API_KEY", "test-fake-gemini-key"),
        "JWT_PRIVATE_KEY_PATH":      "secrets/jwt_private.pem",
        "JWT_PUBLIC_KEY_PATH":       "secrets/jwt_public.pem",
        "ALLOWED_ORIGINS":           '["http://test"]',
        "LOG_LEVEL":                 "WARNING",
    })

    config._test_containers = [pg, redis_c, qdrant_c, minio_c, rmq_c]


def pytest_unconfigure(config: pytest.Config) -> None:
    for c in getattr(config, "_test_containers", []):
        try:
            c.stop()
        except Exception:
            pass


def pytest_addoption(parser: pytest.Parser) -> None:
    parser.addoption(
        "--no-containers",
        action="store_true",
        default=False,
        help="Skip container startup (for unit tests only)",
    )


def pytest_collection_modifyitems(items: list) -> None:
    """Force all async tests onto the session event loop.

    The session-scoped `client` fixture (and the asyncpg pool it creates) are
    bound to the session event loop.  If individual tests run on their own
    function-scoped loops, asyncpg connections leak across loops and produce
    'Future attached to a different loop' errors.  Marking every async test
    with loop_scope="session" keeps everything on one loop.
    """
    session_marker = pytest.mark.asyncio(loop_scope="session")
    for item in items:
        if isinstance(item, pytest.Function) and asyncio.iscoroutinefunction(item.obj):
            item.add_marker(session_marker, append=False)


# ─────────────────────────────────────────────────────────────────────────────
# Shared session-scoped fixtures
# ─────────────────────────────────────────────────────────────────────────────

@pytest.fixture(scope="session")
def event_loop():
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


@pytest_asyncio.fixture(scope="session")
async def client():
    """In-process httpx client connected to the FastAPI app with real services."""
    from httpx import ASGITransport, AsyncClient

    from app.core.database import init_db
    from app.main import app
    from app.services.retriever import ensure_collection

    await init_db()
    await ensure_collection()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test", timeout=60.0) as c:
        yield c


@pytest_asyncio.fixture(scope="session", autouse=True)
async def init_minio_bucket():
    """Create the rag-documents bucket in the test MinIO container."""
    minio_endpoint = os.environ.get("MINIO_ENDPOINT", "http://localhost:9000")
    s3 = boto3.client(
        "s3",
        endpoint_url=minio_endpoint,
        aws_access_key_id="minioadmin",
        aws_secret_access_key="minioadmin",
    )
    try:
        s3.create_bucket(Bucket="rag-documents")
    except Exception:
        pass  # bucket already exists


# ─────────────────────────────────────────────────────────────────────────────
# Legacy mock-based fixtures (used by unit/ and integration/ tests)
# ─────────────────────────────────────────────────────────────────────────────

@pytest.fixture
def tenant_id() -> str:
    return str(uuid.uuid4())


@pytest.fixture
def tenant_namespace(tenant_id) -> str:
    return tenant_id
