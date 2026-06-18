"""
Multi-tenant evaluation tests.

Fast (always-run) tests verify that two EvaluationPipeline instances with
different TenantContext objects are fully independent — they don't share state
and each pipeline's retrieve() calls use the correct tenant_id.

Slow tests (require GEMINI_API_KEY + running Celery worker) provision two
real tenants with different document corpora, run RAGAS evaluation on each,
and verify:
  1. Answers diverge (each tenant sees only its own documents).
  2. Both pipelines meet the same quality thresholds.
  3. Multi-turn context_awareness metric works for the RFC corpus.
"""
import os
import uuid
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
import pytest_asyncio

from app.services.evaluator import EvalResult, EvalSample, EvaluationPipeline
from tests.evaluation.golden_dataset import (
    GOLDEN_SAMPLES,
    GOLDEN_SAMPLES_RFC,
    METRIC_THRESHOLDS,
)

FIXTURE_ACME = Path(__file__).parent.parent / "regression" / "fixtures" / "sample.txt"
FIXTURE_RFC  = Path(__file__).parent.parent / "regression" / "fixtures" / "tech_specs.txt"


# ── Helpers ───────────────────────────────────────────────────────────────────

def _mock_ctx(tenant_id: str | None = None) -> MagicMock:
    ctx = MagicMock()
    ctx.tenant_id = uuid.UUID(tenant_id) if tenant_id else uuid.uuid4()
    ctx.user_id   = uuid.uuid4()
    ctx.llm_config = {}
    ctx.rag_config = {}
    return ctx


def _fake_retrieval(texts: list[str] = (), candidate_count: int = 20) -> MagicMock:
    chunk = MagicMock()
    chunk.text = "Mocked chunk text"
    return MagicMock(
        chunks=[chunk] * len(texts),
        rewritten_query="rewritten",
        retrieval_ms=10,
        candidate_count=candidate_count,
    )


# ── Fast mocked tests (always run) ───────────────────────────────────────────

class TestEvalPipelineMockedMultiTenant:
    async def test_two_pipeline_instances_with_different_ctxs_are_independent(self):
        """
        Two EvaluationPipeline instances must each use only their own ctx.tenant_id.
        If they shared state, the second call would overwrite the first.
        """
        tid_a = str(uuid.uuid4())
        tid_b = str(uuid.uuid4())
        ctx_a = _mock_ctx(tid_a)
        ctx_b = _mock_ctx(tid_b)

        captured_a: list[str] = []
        captured_b: list[str] = []

        async def _retrieve_a(question, ctx, **kwargs):
            captured_a.append(str(ctx.tenant_id))
            return _fake_retrieval()

        async def _retrieve_b(question, ctx, **kwargs):
            captured_b.append(str(ctx.tenant_id))
            return _fake_retrieval()

        async def _gen_sync(req, ctx):
            return "Answer", [], {"input_tokens": 10, "output_tokens": 5, "model": "mock"}

        sample = EvalSample(
            question="What is this?",
            ground_truth="A test answer.",
            reference_contexts=["Some context text."],
        )

        # Run pipeline A
        with patch("app.services.evaluator.retrieve", side_effect=_retrieve_a), \
             patch("app.services.evaluator.generate_sync", side_effect=_gen_sync):
            pipeline_a = EvaluationPipeline(ctx_a)
            await pipeline_a.run_dataset([sample])

        # Run pipeline B
        with patch("app.services.evaluator.retrieve", side_effect=_retrieve_b), \
             patch("app.services.evaluator.generate_sync", side_effect=_gen_sync):
            pipeline_b = EvaluationPipeline(ctx_b)
            await pipeline_b.run_dataset([sample])

        assert captured_a == [tid_a], f"Pipeline A used wrong tenant_id: {captured_a}"
        assert captured_b == [tid_b], f"Pipeline B used wrong tenant_id: {captured_b}"

    async def test_divergent_answers_detected_correctly(self):
        """
        When two pipelines return different mocked answers for the same question,
        the divergence assertion logic must detect it.  This validates the test
        logic used in the slow TestAnswerDivergenceByTenant tests below.
        """
        sample = EvalSample(
            question="What is the main topic?",
            ground_truth="Topic X.",
            reference_contexts=["Context."],
        )

        async def _retrieval_stub(q, ctx, **kw):
            return _fake_retrieval()

        answers = []
        for answer_text in (
            "Refund is available within 30 days.",
            "The GET method requests a resource representation.",
        ):
            async def _gen_sync(req, ctx, _text=answer_text):
                return _text, [], {}

            pipeline = EvaluationPipeline(_mock_ctx())
            with patch("app.services.evaluator.retrieve", side_effect=_retrieval_stub), \
                 patch("app.services.evaluator.generate_sync", side_effect=_gen_sync):
                results = await pipeline.run_dataset([sample])
            answers.append(results[0].answer)

        assert answers[0] != answers[1], (
            "Test expects divergent answers but got identical responses"
        )


# ── Slow multi-tenant eval tests (require real API keys + Celery) ─────────────

def _skip_if_no_gemini():
    key = os.environ.get("GEMINI_API_KEY", "")
    if not key or key == "test-fake-gemini-key":
        pytest.skip("Requires a real GEMINI_API_KEY — export it before running.")


async def _build_ctx_for_token(client, token: str):
    """Build a real TenantContext from a bearer token using the auth middleware."""
    from starlette.datastructures import State
    from fastapi.security import HTTPAuthorizationCredentials
    from app.core.database import get_db, get_redis
    from app.middleware.auth import get_tenant_ctx

    creds = HTTPAuthorizationCredentials(scheme="Bearer", credentials=token)
    mock_req = MagicMock()
    mock_req.state = State()

    async for db in get_db():
        redis = await get_redis()
        ctx   = await get_tenant_ctx(
            request=mock_req, credentials=creds, db=db, redis=redis
        )
        return ctx


@pytest_asyncio.fixture(scope="module")
async def eval_tenant_a(client):
    """
    Register Tenant A, upload the Acme Corp fixture, wait up to 60 s for indexing.
    Returns (ctx, token) for use in slow evaluation tests.
    Requires a running Celery worker with a real OpenAI embedding key.
    """
    import asyncio
    suffix = uuid.uuid4().hex[:8]
    reg = await client.post("/v1/auth/register", json={
        "username": f"evalA_{suffix}",
        "email":    f"evalA_{suffix}@example.com",
        "password": "EvalTenantA1!",
    })
    assert reg.status_code == 201, reg.text
    token   = reg.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    content = FIXTURE_ACME.read_bytes()
    up = await client.post(
        "/v1/documents",
        files={"file": (FIXTURE_ACME.name, content, "text/plain")},
        headers=headers,
    )
    assert up.status_code == 202
    doc_id = up.json()["document_id"]

    for _ in range(30):
        await asyncio.sleep(2)
        status_resp = await client.get(f"/v1/documents/{doc_id}", headers=headers)
        if status_resp.json().get("status") == "ready":
            break

    return {"token": token, "headers": headers}


@pytest_asyncio.fixture(scope="module")
async def eval_tenant_b(client):
    """
    Register Tenant B, upload the RFC 7231 fixture, wait up to 60 s for indexing.
    Returns (token, headers) for use in slow evaluation tests.
    Requires a running Celery worker with a real OpenAI embedding key.
    """
    import asyncio
    suffix = uuid.uuid4().hex[:8]
    reg = await client.post("/v1/auth/register", json={
        "username": f"evalB_{suffix}",
        "email":    f"evalB_{suffix}@example.com",
        "password": "EvalTenantB1!",
    })
    assert reg.status_code == 201, reg.text
    token   = reg.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    content = FIXTURE_RFC.read_bytes()
    up = await client.post(
        "/v1/documents",
        files={"file": (FIXTURE_RFC.name, content, "text/plain")},
        headers=headers,
    )
    assert up.status_code == 202
    doc_id = up.json()["document_id"]

    for _ in range(30):
        await asyncio.sleep(2)
        status_resp = await client.get(f"/v1/documents/{doc_id}", headers=headers)
        if status_resp.json().get("status") == "ready":
            break

    return {"token": token, "headers": headers}


class TestAnswerDivergenceByTenant:
    @pytest.mark.slow
    async def test_same_question_different_tenants_yields_different_answers(
        self, client, eval_tenant_a, eval_tenant_b
    ):
        """
        Both tenants are asked the same vague question.  Because they have
        different document corpora, their answers must differ in topic.
        """
        _skip_if_no_gemini()

        ctx_a = await _build_ctx_for_token(client, eval_tenant_a["token"])
        ctx_b = await _build_ctx_for_token(client, eval_tenant_b["token"])

        sample = EvalSample(
            question="What is the main topic discussed in the documents?",
            ground_truth="The main topic.",
            reference_contexts=["Any context."],
        )

        results_a = await EvaluationPipeline(ctx_a).run_dataset([sample])
        results_b = await EvaluationPipeline(ctx_b).run_dataset([sample])

        answer_a = results_a[0].answer.lower()
        answer_b = results_b[0].answer.lower()

        assert answer_a != answer_b, (
            f"Expected different answers per tenant but got identical responses.\n"
            f"Tenant A: {answer_a[:100]}\nTenant B: {answer_b[:100]}"
        )
        # Tenant A's corpus is the Acme refund policy
        assert any(kw in answer_a for kw in ("refund", "acme", "30 day", "return", "policy")), (
            f"Tenant A answer does not reference its Acme corpus: {answer_a[:200]}"
        )
        # Tenant B's corpus is the RFC 7231 HTTP semantics document
        assert any(kw in answer_b for kw in ("http", "get", "post", "status", "rfc", "method")), (
            f"Tenant B answer does not reference its RFC corpus: {answer_b[:200]}"
        )


class TestMultiTenantRAGASScores:
    @pytest.mark.slow
    async def test_tenant_a_scores_meet_thresholds(self, client, eval_tenant_a):
        """Acme corpus pipeline must meet all 8 metric thresholds."""
        _skip_if_no_gemini()
        ctx     = await _build_ctx_for_token(client, eval_tenant_a["token"])
        results = await EvaluationPipeline(ctx).run_dataset(GOLDEN_SAMPLES)
        agg     = EvaluationPipeline.aggregate(results)
        _assert_thresholds(agg, label="Tenant A (Acme corpus)")

    @pytest.mark.slow
    async def test_tenant_b_scores_meet_thresholds(self, client, eval_tenant_b):
        """RFC corpus pipeline must meet all 8 metric thresholds."""
        _skip_if_no_gemini()
        ctx     = await _build_ctx_for_token(client, eval_tenant_b["token"])
        results = await EvaluationPipeline(ctx).run_dataset(GOLDEN_SAMPLES_RFC)
        agg     = EvaluationPipeline.aggregate(results)
        _assert_thresholds(agg, label="Tenant B (RFC corpus)")


class TestMultiTurnEvaluation:
    @pytest.mark.slow
    async def test_context_awareness_above_threshold_for_rfc_multiturn(
        self, client, eval_tenant_b
    ):
        """
        GOLDEN_SAMPLES_RFC[2] is a multi-turn sample (status codes follow-up).
        Its context_awareness must reach 0.70 (same threshold as existing tests).
        """
        _skip_if_no_gemini()
        multiturn_sample = GOLDEN_SAMPLES_RFC[2]
        assert multiturn_sample.history, "Expected a multi-turn sample at index 2"

        ctx     = await _build_ctx_for_token(client, eval_tenant_b["token"])
        results = await EvaluationPipeline(ctx).run_dataset([multiturn_sample])
        assert len(results) == 1
        ca = results[0].context_awareness
        assert ca is not None
        assert ca >= METRIC_THRESHOLDS["context_awareness"], (
            f"context_awareness = {ca:.3f} below threshold "
            f"{METRIC_THRESHOLDS['context_awareness']}"
        )


# ── Threshold assertion helper ────────────────────────────────────────────────

def _assert_thresholds(agg: dict, label: str = "") -> None:
    upper_bound = {"hallucination_rate"}
    for metric, threshold in METRIC_THRESHOLDS.items():
        value = agg.get(metric)
        if value is None or value != value:  # skip NaN
            continue
        if metric in upper_bound:
            assert value <= threshold, (
                f"[{label}] '{metric}' = {value:.3f} exceeds upper bound {threshold}"
            )
        else:
            assert value >= threshold, (
                f"[{label}] '{metric}' = {value:.3f} is below threshold {threshold}"
            )
