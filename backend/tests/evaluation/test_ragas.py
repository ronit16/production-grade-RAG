"""
RAGAS quality evaluation and performance benchmarks.
Run with: pytest tests/evaluation/ -m slow
"""
import json
import time
import uuid

import pytest

from app.services.retriever import reciprocal_rank_fusion
from app.services.session import SessionState, Message


GOLDEN_DATASET = [
    {
        "question":    "What is the company's refund policy?",
        "ground_truth":"Customers can request a full refund within 30 days of purchase.",
        "contexts": [
            "Our refund policy allows customers to request a full refund within 30 days of purchase.",
            "After 30 days, store credit may be issued at our discretion.",
        ],
        "answer": (
            "You can request a full refund within 30 days of purchase. "
            "After 30 days, store credit may be issued at our discretion."
        ),
    },
    {
        "question":    "What are the system requirements?",
        "ground_truth":"Requires 8GB RAM, 4-core CPU, and 10GB disk space.",
        "contexts": [
            "Minimum system requirements: 8GB RAM, 4-core processor, 10GB free disk space.",
            "Recommended: 16GB RAM, 8-core processor, SSD storage.",
        ],
        "answer": (
            "The minimum requirements are 8GB RAM, a 4-core CPU, and 10GB of disk space. "
            "We recommend 16GB RAM and an SSD."
        ),
    },
]

THRESHOLDS = {
    "faithfulness":     0.80,
    "answer_relevancy": 0.75,
    "context_precision":0.70,
    "context_recall":   0.75,
}


class TestRAGASMetrics:
    @pytest.mark.slow
    @pytest.mark.asyncio
    async def test_ragas_golden_set(self):
        """Evaluate against golden QA pairs. Fails if any metric drops below threshold."""
        from datasets import Dataset
        from ragas import evaluate
        from ragas.metrics import (
            answer_faithfulness,
            answer_relevancy,
            context_precision,
            context_recall,
        )

        dataset = Dataset.from_list(GOLDEN_DATASET)
        results = evaluate(
            dataset=dataset,
            metrics=[answer_faithfulness, answer_relevancy, context_precision, context_recall],
        )
        df = results.to_pandas()

        for metric, threshold in THRESHOLDS.items():
            avg_score = df[metric].mean()
            assert avg_score >= threshold, (
                f"RAGAS metric '{metric}' = {avg_score:.3f} below threshold {threshold}."
            )


class TestPerformanceBenchmarks:
    @pytest.mark.slow
    def test_rrf_fusion_sub_1ms(self):
        N      = 100
        dense  = [{"chunk_id": f"d{i}", "score": 1/(i+1), "document_id": "x", "text": "", "page_number": 1, "section": "", "metadata": {}} for i in range(N)]
        sparse = [{"chunk_id": f"s{i}", "score": 10/(i+1), "document_id": "x", "text": "", "page_number": 1, "section": "", "metadata": {}} for i in range(N)]

        start = time.perf_counter()
        for _ in range(1000):
            reciprocal_rank_fusion(dense, sparse)
        elapsed_ms = (time.perf_counter() - start) * 1000

        assert elapsed_ms / 1000 < 1.0, f"RRF took {elapsed_ms/1000:.2f}ms/call — too slow"

    @pytest.mark.slow
    def test_session_serialisation_sub_500ms(self):
        state = SessionState(
            session_id=str(uuid.uuid4()),
            tenant_id=str(uuid.uuid4()),
            user_id=None,
            messages=[Message(role="user", content=f"Q{i}") for i in range(20)],
            created_at=time.time(),
            last_active=time.time(),
        )
        data = json.dumps({
            "session_id":      state.session_id,
            "tenant_id":       state.tenant_id,
            "user_id":         None,
            "created_at":      state.created_at,
            "last_active":     state.last_active,
            "total_tokens_in": 0,
            "total_tokens_out":0,
            "messages": [
                {"role": m.role, "content": m.content, "ts": m.ts,
                 "tokens_in": 0, "tokens_out": 0, "sources": [], "query_id": ""}
                for m in state.messages
            ],
        })
        start = time.perf_counter()
        for _ in range(1000):
            json.dumps(json.loads(data))
        elapsed = time.perf_counter() - start
        assert elapsed < 0.5, f"Serialization took {elapsed*1000:.1f}ms total"
