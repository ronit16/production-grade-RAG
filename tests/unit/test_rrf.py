"""
Unit tests: Qdrant hybrid search path.
RRF fusion is now delegated to Qdrant natively (Prefetch + Fusion.RRF).
These tests verify the retriever wires the request correctly and maps results.
"""
import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services.retriever import RetrievedChunk, RetrievalResult


def _mock_qdrant_point(chunk_id: str, score: float, text: str = "sample text") -> MagicMock:
    """Build a fake ScoredPoint as returned by Qdrant query_points."""
    p = MagicMock()
    p.id    = chunk_id
    p.score = score
    p.payload = {
        "tenant_id":   "test-tenant",
        "document_id": "doc-1",
        "text":        text,
        "page_number": 1,
        "section":     "intro",
        "token_count": 50,
    }
    return p


class TestHybridSearch:
    @pytest.mark.asyncio
    async def test_hybrid_search_calls_qdrant_with_both_prefetches(self):
        """hybrid_search must submit one dense Prefetch and one sparse Prefetch."""
        mock_client  = AsyncMock()
        mock_results = MagicMock()
        mock_results.points = [_mock_qdrant_point("chunk-1", 0.9)]
        mock_client.query_points = AsyncMock(return_value=mock_results)

        with patch("app.services.retriever._get_qdrant", return_value=mock_client), \
             patch("app.services.retriever._embed_dense",  AsyncMock(return_value=[0.1] * 1536)), \
             patch("app.services.retriever._embed_sparse", AsyncMock(return_value=MagicMock())):

            from app.services.retriever import hybrid_search
            results = await hybrid_search(
                query="what is the policy?",
                tenant_id=str(uuid.uuid4()),
                top_k=5,
            )

        call_kwargs = mock_client.query_points.call_args[1]
        # Two prefetch branches (dense + sparse)
        assert len(call_kwargs["prefetch"]) == 2
        # Fusion.RRF applied at merge
        from qdrant_client.models import Fusion
        assert call_kwargs["query"] == Fusion.RRF
        # Correct number of results mapped
        assert len(results) == 1
        assert results[0]["chunk_id"] == "chunk-1"

    @pytest.mark.asyncio
    async def test_hybrid_search_applies_tenant_filter(self):
        """The filter passed to Qdrant must include the tenant_id."""
        mock_client  = AsyncMock()
        mock_results = MagicMock()
        mock_results.points = []
        mock_client.query_points = AsyncMock(return_value=mock_results)

        tenant_id = str(uuid.uuid4())

        with patch("app.services.retriever._get_qdrant", return_value=mock_client), \
             patch("app.services.retriever._embed_dense",  AsyncMock(return_value=[0.0] * 1536)), \
             patch("app.services.retriever._embed_sparse", AsyncMock(return_value=MagicMock())):

            from app.services.retriever import hybrid_search
            await hybrid_search(query="query", tenant_id=tenant_id, top_k=5)

        call_kwargs = mock_client.query_points.call_args[1]
        # Both prefetches carry a filter
        for prefetch in call_kwargs["prefetch"]:
            conditions = prefetch.filter.must
            tenant_values = [c.match.value for c in conditions if c.key == "tenant_id"]
            assert tenant_id in tenant_values

    @pytest.mark.asyncio
    async def test_hybrid_search_doc_id_filter_propagates(self):
        """filter_doc_ids must be forwarded to both Prefetch branches."""
        mock_client  = AsyncMock()
        mock_results = MagicMock()
        mock_results.points = []
        mock_client.query_points = AsyncMock(return_value=mock_results)

        doc_ids = ["doc-A", "doc-B"]

        with patch("app.services.retriever._get_qdrant", return_value=mock_client), \
             patch("app.services.retriever._embed_dense",  AsyncMock(return_value=[0.0] * 1536)), \
             patch("app.services.retriever._embed_sparse", AsyncMock(return_value=MagicMock())):

            from app.services.retriever import hybrid_search
            await hybrid_search(
                query="query",
                tenant_id=str(uuid.uuid4()),
                top_k=5,
                filter_doc_ids=doc_ids,
            )

        call_kwargs = mock_client.query_points.call_args[1]
        for prefetch in call_kwargs["prefetch"]:
            conditions   = prefetch.filter.must
            doc_cond     = next((c for c in conditions if c.key == "document_id"), None)
            assert doc_cond is not None
            assert set(doc_cond.match.any) == set(doc_ids)

    @pytest.mark.asyncio
    async def test_empty_qdrant_result_returns_empty_list(self):
        mock_client  = AsyncMock()
        mock_results = MagicMock()
        mock_results.points = []
        mock_client.query_points = AsyncMock(return_value=mock_results)

        with patch("app.services.retriever._get_qdrant", return_value=mock_client), \
             patch("app.services.retriever._embed_dense",  AsyncMock(return_value=[0.0] * 1536)), \
             patch("app.services.retriever._embed_sparse", AsyncMock(return_value=MagicMock())):

            from app.services.retriever import hybrid_search
            results = await hybrid_search("q", str(uuid.uuid4()), top_k=5)

        assert results == []
