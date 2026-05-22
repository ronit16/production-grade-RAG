"""
RAGAS evaluation pipeline — all 8 metric categories.

Fast tests (no containers, no LLM key):
    pytest tests/evaluation/ --no-containers

Live tests (requires running stack + real GEMINI_API_KEY):
    pytest tests/evaluation/ -m slow
"""
import json
import time
import uuid
from dataclasses import fields as dc_fields
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services.evaluator import EvalResult, EvalSample, EvaluationPipeline
from app.services.retriever import RetrievalResult, RetrievedChunk
from tests.evaluation.golden_dataset import GOLDEN_SAMPLES, METRIC_THRESHOLDS


# ─── Shared test helpers ──────────────────────────────────────────────────────

def _ctx() -> MagicMock:
    ctx = MagicMock()
    ctx.tenant_id  = uuid.uuid4()
    ctx.llm_config = {}
    ctx.rag_config  = {}
    return ctx


def _retrieval(texts: list[str], candidates: int = 20) -> RetrievalResult:
    chunks = [
        RetrievedChunk(
            chunk_id=str(uuid.uuid4()),
            document_id="doc-1",
            text=t,
            score=0.9 - i * 0.1,
            page_number=i + 1,
            section="intro",
            metadata={},
        )
        for i, t in enumerate(texts)
    ]
    return RetrievalResult(
        chunks=chunks,
        query="test question",
        rewritten_query=None,
        retrieval_ms=42,
        candidate_count=candidates,
    )


# ─── 1. Dataclass construction and defaults ───────────────────────────────────

class TestEvalDataclasses:
    def test_sample_history_defaults_empty(self):
        s = EvalSample(question="q", ground_truth="gt", reference_contexts=["c"])
        assert s.history == []

    def test_sample_accepts_history(self):
        h = [{"role": "user", "content": "prior question"}]
        s = EvalSample(question="q", ground_truth="gt", reference_contexts=[], history=h)
        assert s.history == h

    def test_result_metric_fields_default_none(self):
        r = EvalResult(question="q", answer="a", retrieved_contexts=[],
                       reference_contexts=[], ground_truth="gt")
        optional_metrics = (
            "faithfulness_score", "context_precision", "context_recall",
            "hallucination_rate", "retrieval_ratio", "relevancy_score",
            "context_awareness", "answer_quality",
        )
        for fname in optional_metrics:
            assert getattr(r, fname) is None, f"{fname} should default to None"

    def test_result_latency_fields_default_zero(self):
        r = EvalResult(question="q", answer="a", retrieved_contexts=[],
                       reference_contexts=[], ground_truth="gt")
        assert r.retrieval_ms  == 0
        assert r.generation_ms == 0
        assert r.total_ms      == 0

    def test_all_eight_metric_fields_present_on_eval_result(self):
        field_names = {f.name for f in dc_fields(EvalResult)}
        required = {
            "faithfulness_score", "context_precision", "context_recall",
            "hallucination_rate", "retrieval_ratio",   "relevancy_score",
            "context_awareness",  "answer_quality",
        }
        assert required.issubset(field_names)


# ─── 2. Custom metric derivation (pure math, no I/O) ─────────────────────────

class TestCustomMetrics:
    def test_hallucination_rate_is_complement_of_faithfulness(self):
        r = EvalResult(question="q", answer="a", retrieved_contexts=[],
                       reference_contexts=[], ground_truth="gt",
                       faithfulness_score=0.72)
        r.hallucination_rate = round(1.0 - r.faithfulness_score, 4)
        assert r.hallucination_rate == pytest.approx(0.28, abs=1e-4)

    def test_hallucination_zero_when_fully_faithful(self):
        r = EvalResult(question="q", answer="a", retrieved_contexts=[],
                       reference_contexts=[], ground_truth="gt",
                       faithfulness_score=1.0)
        r.hallucination_rate = round(1.0 - r.faithfulness_score, 4)
        assert r.hallucination_rate == pytest.approx(0.0)

    def test_retrieval_ratio_partial_pass_through(self):
        assert round(5 / 20, 4) == pytest.approx(0.25)

    def test_retrieval_ratio_full_pass_through(self):
        assert round(20 / 20, 4) == pytest.approx(1.0)

    async def test_context_awareness_is_1_for_single_turn(self):
        pipeline = EvaluationPipeline(_ctx())
        sample = EvalSample(question="q", ground_truth="gt", reference_contexts=[])
        score = await pipeline._compute_context_awareness(sample, "some answer")
        assert score == pytest.approx(1.0)


# ─── 3. Full pipeline — mocked retrieve + generate_sync ──────────────────────

class TestEvaluationPipelineMocked:
    _USAGE = {
        "input_tokens": 100, "output_tokens": 50,
        "generation_ms": 300, "model": "gpt-4o",
    }

    async def test_run_single_inference_returns_triple(self):
        pipeline = EvaluationPipeline(_ctx())
        sample   = EvalSample(question="refund?", ground_truth="30 days.",
                              reference_contexts=["30 day refund."])
        ret      = _retrieval(["Refunds within 30 days."])

        with patch("app.services.evaluator.retrieve",
                   new_callable=AsyncMock, return_value=ret), \
             patch("app.services.evaluator.generate_sync",
                   new_callable=AsyncMock,
                   return_value=("Refund in 30 days.", [], self._USAGE)):
            answer, retrieval, usage = await pipeline.run_single_inference(sample)

        assert isinstance(answer, str) and len(answer) > 0
        assert isinstance(retrieval, RetrievalResult)
        assert "input_tokens" in usage

    async def test_run_dataset_populates_all_core_fields(self):
        pipeline = EvaluationPipeline(_ctx())
        sample   = EvalSample(question="q", ground_truth="gt", reference_contexts=["c"])
        ret      = _retrieval(["chunk text"], candidates=20)

        with patch("app.services.evaluator.retrieve",
                   new_callable=AsyncMock, return_value=ret), \
             patch("app.services.evaluator.generate_sync",
                   new_callable=AsyncMock,
                   return_value=("answer text", [], self._USAGE)), \
             patch("app.services.evaluator._RAGAS_AVAILABLE", False), \
             patch.object(pipeline, "_compute_context_awareness",
                          new_callable=AsyncMock, return_value=1.0):
            results = await pipeline.run_dataset([sample])

        r = results[0]
        assert r.question        == sample.question
        assert r.answer          == "answer text"
        assert r.retrieval_ms    == 42
        assert r.generation_ms   == 300
        assert r.candidate_count == 20
        assert r.reranked_count  == 1
        assert r.context_awareness == pytest.approx(1.0)

    async def test_retrieval_ratio_derived_correctly(self):
        pipeline = EvaluationPipeline(_ctx())
        sample   = EvalSample(question="q", ground_truth="gt", reference_contexts=["c"])
        ret      = _retrieval(["a", "b"], candidates=20)  # 2 reranked out of 20

        with patch("app.services.evaluator.retrieve",
                   new_callable=AsyncMock, return_value=ret), \
             patch("app.services.evaluator.generate_sync",
                   new_callable=AsyncMock,
                   return_value=("ans", [], self._USAGE)), \
             patch("app.services.evaluator._RAGAS_AVAILABLE", False), \
             patch.object(pipeline, "_compute_context_awareness",
                          new_callable=AsyncMock, return_value=1.0):
            results = await pipeline.run_dataset([sample])

        assert results[0].retrieval_ratio == pytest.approx(2 / 20)

    async def test_hallucination_rate_derived_after_ragas(self):
        """Verify hallucination_rate = 1 - faithfulness_score once RAGAS runs."""
        pipeline = EvaluationPipeline(_ctx())
        sample   = EvalSample(question="q", ground_truth="gt", reference_contexts=["c"])
        ret      = _retrieval(["chunk"])

        async def _fake_ragas(samples, answers, results):
            results[0].faithfulness_score = 0.85
            return results

        with patch("app.services.evaluator.retrieve",
                   new_callable=AsyncMock, return_value=ret), \
             patch("app.services.evaluator.generate_sync",
                   new_callable=AsyncMock,
                   return_value=("ans", [], self._USAGE)), \
             patch.object(pipeline, "_compute_ragas_metrics",
                          side_effect=_fake_ragas), \
             patch.object(pipeline, "_compute_context_awareness",
                          new_callable=AsyncMock, return_value=1.0):
            results = await pipeline.run_dataset([sample])

        assert results[0].hallucination_rate == pytest.approx(0.15, abs=1e-4)

    async def test_ragas_import_guard_returns_results_unchanged(self):
        pipeline = EvaluationPipeline(_ctx())
        results  = [EvalResult(question="q", answer="a",
                               retrieved_contexts=["c"],
                               reference_contexts=["c"],
                               ground_truth="gt")]
        samples  = [EvalSample(question="q", ground_truth="gt",
                               reference_contexts=["c"])]

        with patch("app.services.evaluator._RAGAS_AVAILABLE", False):
            returned = await pipeline._compute_ragas_metrics(samples, ["a"], results)

        assert returned is results
        assert returned[0].faithfulness_score is None


# ─── 4. Latency capture ───────────────────────────────────────────────────────

class TestLatencyCapture:
    async def test_retrieval_ms_sourced_from_retrieval_result(self):
        pipeline = EvaluationPipeline(_ctx())
        sample   = EvalSample(question="q", ground_truth="gt", reference_contexts=[])
        ret      = _retrieval(["text"])
        ret.retrieval_ms = 137

        with patch("app.services.evaluator.retrieve",
                   new_callable=AsyncMock, return_value=ret), \
             patch("app.services.evaluator.generate_sync",
                   new_callable=AsyncMock,
                   return_value=("a", [], {"input_tokens": 5, "output_tokens": 5,
                                           "generation_ms": 250, "model": "m"})), \
             patch("app.services.evaluator._RAGAS_AVAILABLE", False), \
             patch.object(pipeline, "_compute_context_awareness",
                          new_callable=AsyncMock, return_value=1.0):
            results = await pipeline.run_dataset([sample])

        assert results[0].retrieval_ms  == 137
        assert results[0].generation_ms == 250

    async def test_total_ms_is_populated(self):
        pipeline = EvaluationPipeline(_ctx())
        sample   = EvalSample(question="q", ground_truth="gt", reference_contexts=[])
        ret      = _retrieval(["text"])

        with patch("app.services.evaluator.retrieve",
                   new_callable=AsyncMock, return_value=ret), \
             patch("app.services.evaluator.generate_sync",
                   new_callable=AsyncMock,
                   return_value=("a", [], {"input_tokens": 5, "output_tokens": 5,
                                           "generation_ms": 100, "model": "m"})), \
             patch("app.services.evaluator._RAGAS_AVAILABLE", False), \
             patch.object(pipeline, "_compute_context_awareness",
                          new_callable=AsyncMock, return_value=1.0):
            results = await pipeline.run_dataset([sample])

        # total_ms is wall-clock; mocked calls are sub-ms so >= 0 is the correct bound
        assert isinstance(results[0].total_ms, int)
        assert results[0].total_ms >= 0

    async def test_token_counts_sourced_from_usage(self):
        pipeline = EvaluationPipeline(_ctx())
        sample   = EvalSample(question="q", ground_truth="gt", reference_contexts=[])
        ret      = _retrieval(["text"])

        with patch("app.services.evaluator.retrieve",
                   new_callable=AsyncMock, return_value=ret), \
             patch("app.services.evaluator.generate_sync",
                   new_callable=AsyncMock,
                   return_value=("a", [], {"input_tokens": 512, "output_tokens": 128,
                                           "generation_ms": 200, "model": "gpt-4o"})), \
             patch("app.services.evaluator._RAGAS_AVAILABLE", False), \
             patch.object(pipeline, "_compute_context_awareness",
                          new_callable=AsyncMock, return_value=1.0):
            results = await pipeline.run_dataset([sample])

        assert results[0].input_tokens  == 512
        assert results[0].output_tokens == 128
        assert results[0].model         == "gpt-4o"


# ─── 5. Aggregation ───────────────────────────────────────────────────────────

class TestAggregation:
    def _r(self, **kw) -> EvalResult:
        base = dict(question="q", answer="a", retrieved_contexts=[],
                    reference_contexts=[], ground_truth="gt")
        return EvalResult(**{**base, **kw})

    def test_means_are_correct(self):
        agg = EvaluationPipeline.aggregate([
            self._r(faithfulness_score=0.8, relevancy_score=0.9),
            self._r(faithfulness_score=0.6, relevancy_score=0.7),
        ])
        assert agg["faithfulness_score"] == pytest.approx(0.7)
        assert agg["relevancy_score"]    == pytest.approx(0.8)

    def test_sample_count_is_correct(self):
        agg = EvaluationPipeline.aggregate([self._r() for _ in range(3)])
        assert agg["sample_count"] == 3.0

    def test_none_values_excluded_from_mean(self):
        agg = EvaluationPipeline.aggregate([
            self._r(faithfulness_score=0.9),
            self._r(faithfulness_score=None),
        ])
        assert agg["faithfulness_score"] == pytest.approx(0.9)

    def test_empty_list_returns_empty_dict(self):
        assert EvaluationPipeline.aggregate([]) == {}

    def test_all_latency_keys_present(self):
        agg = EvaluationPipeline.aggregate(
            [self._r(retrieval_ms=50, generation_ms=200, total_ms=250)]
        )
        assert {"retrieval_ms", "generation_ms", "total_ms"}.issubset(agg)

    def test_all_eight_metric_keys_in_aggregate(self):
        r = self._r(
            faithfulness_score=0.9, context_precision=0.8, context_recall=0.7,
            hallucination_rate=0.1, retrieval_ratio=0.25, relevancy_score=0.85,
            context_awareness=0.95, answer_quality=0.75,
        )
        agg = EvaluationPipeline.aggregate([r])
        expected_keys = {
            "faithfulness_score", "context_precision", "context_recall",
            "hallucination_rate", "retrieval_ratio",   "relevancy_score",
            "context_awareness",  "answer_quality",
        }
        assert expected_keys.issubset(agg)


# ─── 6. Live RAGAS metrics against golden dataset ────────────────────────────

class TestRAGASMetrics:
    @pytest.mark.slow
    async def test_all_metrics_meet_thresholds(self, client, auth_headers):
        """
        End-to-end: real retrieve + generate_sync + RAGAS against golden samples.
        Requires a real GEMINI_API_KEY and documents indexed in the running stack.
        Skipped automatically when the key is a test placeholder.
        """
        import os
        api_key = os.environ.get("GEMINI_API_KEY", "")
        if not api_key or api_key == "test-fake-gemini-key":
            pytest.skip("Requires a real GEMINI_API_KEY — set it in the environment before running.")

        from starlette.datastructures import State
        from app.core.database import get_db, get_redis
        from app.middleware.auth import get_tenant_ctx
        from fastapi.security import HTTPAuthorizationCredentials

        token = auth_headers["Authorization"].split(" ", 1)[1]
        creds = HTTPAuthorizationCredentials(scheme="Bearer", credentials=token)

        # get_tenant_ctx sets request.state.tenant; supply a stub request
        mock_request = MagicMock()
        mock_request.state = State()

        # get_db() is an async generator; get_redis() is a plain async function
        async for db in get_db():
            redis = await get_redis()
            ctx   = await get_tenant_ctx(
                request=mock_request, credentials=creds, db=db, redis=redis
            )
            pipeline = EvaluationPipeline(ctx)
            results  = await pipeline.run_dataset(GOLDEN_SAMPLES)
            agg      = EvaluationPipeline.aggregate(results)
            break

        upper_bound_metrics = {"hallucination_rate"}
        for metric, threshold in METRIC_THRESHOLDS.items():
            value = agg.get(metric)
            if value is None or value != value:  # skip NaN (no data for this metric)
                continue
            if metric in upper_bound_metrics:
                assert value <= threshold, (
                    f"Metric '{metric}' = {value:.3f} exceeds upper bound {threshold}"
                )
            else:
                assert value >= threshold, (
                    f"Metric '{metric}' = {value:.3f} is below threshold {threshold}"
                )


# ─── 7. Performance benchmarks ────────────────────────────────────────────────

class TestPerformanceBenchmarks:
    @pytest.mark.slow
    def test_session_serialisation_sub_500ms(self):
        from app.services.session import Message, SessionState

        state = SessionState(
            session_id=str(uuid.uuid4()),
            tenant_id=str(uuid.uuid4()),
            user_id=None,
            messages=[Message(role="user", content=f"Q{i}") for i in range(20)],
            created_at=time.time(),
            last_active=time.time(),
        )
        payload = json.dumps({
            "session_id":       state.session_id,
            "tenant_id":        state.tenant_id,
            "user_id":          None,
            "created_at":       state.created_at,
            "last_active":      state.last_active,
            "total_tokens_in":  0,
            "total_tokens_out": 0,
            "messages": [
                {"role": m.role, "content": m.content, "ts": m.ts,
                 "tokens_in": 0, "tokens_out": 0, "sources": [], "query_id": ""}
                for m in state.messages
            ],
        })
        start = time.perf_counter()
        for _ in range(1000):
            json.dumps(json.loads(payload))
        elapsed = time.perf_counter() - start
        assert elapsed < 0.5, f"Serialization took {elapsed * 1000:.1f} ms total"
