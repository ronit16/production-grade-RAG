"""Shared pytest fixtures for all test modules."""
import asyncio
import uuid
from typing import AsyncGenerator
from unittest.mock import AsyncMock, MagicMock

import pytest
import pytest_asyncio
from httpx import AsyncClient

from app.main import app
from app.core.config import get_settings
from app.middleware.auth import TenantContext
from app.models.db import Tenant, PlanTier

settings = get_settings()


@pytest.fixture(scope="session")
def event_loop():
    """Single event loop for the entire test session."""
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


@pytest_asyncio.fixture
async def client() -> AsyncGenerator[AsyncClient, None]:
    async with AsyncClient(app=app, base_url="http://test") as c:
        yield c


@pytest.fixture
def tenant_id() -> str:
    return str(uuid.uuid4())


@pytest.fixture
def tenant_namespace(tenant_id) -> str:
    return tenant_id   # namespace == tenant_id


@pytest.fixture
def mock_tenant_context(tenant_id, tenant_namespace) -> TenantContext:
    tenant = MagicMock(spec=Tenant)
    tenant.id               = uuid.UUID(tenant_id)
    tenant.slug             = "test-tenant"
    tenant.vector_namespace = tenant_namespace
    tenant.plan             = PlanTier.STARTER
    tenant.llm_config       = {}
    tenant.rag_config       = {}
    tenant.features         = {}
    return TenantContext(tenant=tenant, user_id=uuid.uuid4(), user_role="admin")
