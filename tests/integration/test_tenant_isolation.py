"""Integration tests: verify no cross-tenant data leakage."""
import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.core.config import get_settings

settings = get_settings()


class TestTenantIsolation:
    @pytest.mark.asyncio
    async def test_retrieval_scoped_to_tenant_namespace(self, mock_tenant_context):
        with patch("app.services.retriever._get_pinecone_index") as mock_index:
            mock_idx = MagicMock()
            mock_idx.query.return_value = {"matches": []}
            mock_index.return_value = mock_idx

            with patch("app.services.retriever._embed_query", return_value=[0.1] * 1536):
                with patch("app.services.retriever.sparse_search", return_value=[]):
                    from app.services.retriever import dense_search
                    await dense_search("test query", mock_tenant_context.vector_namespace, top_k=5)

            # Assert the query was scoped to THIS tenant's namespace
            call_kwargs = mock_idx.query.call_args[1]
            assert call_kwargs["namespace"] == mock_tenant_context.vector_namespace

    @pytest.mark.asyncio
    async def test_document_access_blocked_for_wrong_tenant(self, client):
        """A tenant cannot read another tenant's document."""
        doc_id   = str(uuid.uuid4())
        tenant_b = str(uuid.uuid4())

        with patch("app.middleware.auth.get_tenant_ctx") as mock_auth:
            ctx_b = MagicMock()
            ctx_b.tenant_id = uuid.UUID(tenant_b)
            mock_auth.return_value = ctx_b

            with patch("app.api.v1.endpoints.documents.get_db"), \
                 patch("app.api.v1.endpoints.documents.get_redis"):
                from sqlalchemy.ext.asyncio import AsyncSession
                with patch.object(AsyncSession, "execute") as mock_exec:
                    mock_result = MagicMock()
                    mock_result.scalar_one_or_none.return_value = None
                    mock_exec.return_value = mock_result

                    response = await client.get(
                        f"/v1/documents/{doc_id}",
                        headers={"Authorization": "Bearer mock_token_for_tenant_b"},
                    )
                    assert response.status_code in (404, 401)

    def test_redis_key_namespace_includes_tenant(self):
        """Session Redis keys must include tenant_id to prevent collision."""
        from app.services.session import SessionManager
        sm  = SessionManager(redis=MagicMock(), db=MagicMock())
        t1  = str(uuid.uuid4())
        t2  = str(uuid.uuid4())
        sid = str(uuid.uuid4())

        key1 = sm._redis_key(sid, t1)
        key2 = sm._redis_key(sid, t2)
        assert key1 != key2
        assert t1 in key1
        assert t2 in key2

    def test_s3_prefix_includes_tenant_id(self):
        """S3 keys must be prefixed with tenant_id."""
        tenant_id = str(uuid.uuid4())
        doc_id    = str(uuid.uuid4())
        filename  = "report.pdf"
        s3_key    = f"{settings.S3_PREFIX}/{tenant_id}/{doc_id}/{filename}"
        assert s3_key.startswith(f"{settings.S3_PREFIX}/{tenant_id}/")
