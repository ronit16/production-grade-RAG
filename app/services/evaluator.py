"""
RAG Evaluation Pipeline — RAGAS metrics + custom derived metrics.

Three-phase design:
  Phase 1: batch inference — retrieve + generate_sync for every sample.
  Phase 2: single RAGAS evaluate() call for the full batch (not per-sample).
  Phase 3: derive hallucination_rate, retrieval_ratio, context_awareness.

Usage:
    pipeline = EvaluationPipeline(ctx)
    results  = await pipeline.run_dataset(samples)
    report   = EvaluationPipeline.aggregate(results)
"""
from __future__ import annotations

import asyncio
import time
import uuid
from dataclasses import dataclass, field
from statistics import mean
from typing import Optional

import litellm

from app.middleware.auth import TenantContext
from app.services.generator import GenerationRequest, generate_sync
from app.services.retriever import RetrievalResult, retrieve

try:
    from datasets import Dataset
    from ragas import evaluate as _ragas_evaluate
    from ragas.metrics.collections import (
        answer_correctness,
        answer_relevancy,
        context_precision,
        context_recall,
        faithfulness,
    )
    _RAGAS_AVAILABLE = True
except ImportError:
    _RAGAS_AVAILABLE = False


# ─── Data contracts ───────────────────────────────────────────────────────────

@dataclass
class EvalSample:
    question:           str
    ground_truth:       str
    reference_contexts: list[str]
    history:            list[dict] = field(default_factory=list)


@dataclass
class EvalResult:
    question:           str
    answer:             str
    retrieved_contexts: list[str]
    reference_contexts: list[str]
    ground_truth:       str

    # RAGAS metrics — None until _compute_ragas_metrics fills them
    faithfulness_score: Optional[float] = None
    context_precision:  Optional[float] = None
    context_recall:     Optional[float] = None
    relevancy_score:    Optional[float] = None
    answer_quality:     Optional[float] = None

    # Derived metrics — computed after RAGAS
    hallucination_rate: Optional[float] = None   # = 1 - faithfulness_score
    retrieval_ratio:    Optional[float] = None   # = reranked_count / candidate_count
    context_awareness:  Optional[float] = None   # LLM judge (multi-turn) or 1.0

    # Latency & efficiency
    retrieval_ms:   int = 0
    generation_ms:  int = 0
    total_ms:       int = 0
    input_tokens:   int = 0
    output_tokens:  int = 0
    model:          str = ""
    candidate_count: int = 0
    reranked_count:  int = 0


# ─── Context-awareness LLM judge ─────────────────────────────────────────────

_CA_SYSTEM = (
    "You are an evaluator for multi-turn RAG systems. "
    "Score how well the answer uses the conversation history. "
    "Reply with a single float 0.0–1.0. No other text."
)
_CA_USER = (
    "History:\n{history}\n\n"
    "Follow-up question: {question}\n\n"
    "Answer: {answer}\n\n"
    "Score (0.0–1.0):"
)


# ─── Pipeline ────────────────────────────────────────────────────────────────

class EvaluationPipeline:
    def __init__(self, ctx: TenantContext) -> None:
        self._ctx = ctx

    # ── public API ────────────────────────────────────────────────────────────

    async def run_single_inference(
        self, sample: EvalSample
    ) -> tuple[str, RetrievalResult, dict]:
        """Run retrieve + generate_sync for one sample."""
        retrieval = await retrieve(
            question=sample.question,
            ctx=self._ctx,
            history=sample.history or [],
        )
        req = GenerationRequest(
            query_id=str(uuid.uuid4()),
            question=sample.question,
            chunks=retrieval.chunks,
            history=sample.history or [],
        )
        answer, _sources, usage = await generate_sync(req, self._ctx)
        return answer, retrieval, usage

    async def run_dataset(self, samples: list[EvalSample]) -> list[EvalResult]:
        """
        Full evaluation over a list of samples.
        Returns one EvalResult per sample with all 8 metric categories populated.
        """
        # Phase 1: inference (sequential to respect rate limits)
        partial: list[tuple[EvalSample, str, RetrievalResult, dict, int]] = []
        for sample in samples:
            t0 = time.monotonic()
            answer, retrieval, usage = await self.run_single_inference(sample)
            total_ms = int((time.monotonic() - t0) * 1000)
            partial.append((sample, answer, retrieval, usage, total_ms))

        results = [
            EvalResult(
                question=s.question,
                answer=answer,
                retrieved_contexts=[c.text for c in ret.chunks],
                reference_contexts=s.reference_contexts,
                ground_truth=s.ground_truth,
                retrieval_ms=ret.retrieval_ms,
                generation_ms=usage.get("generation_ms", 0),
                total_ms=total_ms,
                input_tokens=usage.get("input_tokens", 0),
                output_tokens=usage.get("output_tokens", 0),
                model=usage.get("model", ""),
                candidate_count=ret.candidate_count,
                reranked_count=len(ret.chunks),
            )
            for (s, answer, ret, usage, total_ms) in partial
        ]

        # Phase 2: RAGAS batch (one call for all samples)
        results = await self._compute_ragas_metrics(
            [p[0] for p in partial],
            [p[1] for p in partial],
            results,
        )

        # Phase 3: derived metrics
        for i, (sample, answer, _ret, _usage, _ms) in enumerate(partial):
            if results[i].faithfulness_score is not None:
                results[i].hallucination_rate = round(
                    1.0 - results[i].faithfulness_score, 4
                )
            if results[i].candidate_count > 0:
                results[i].retrieval_ratio = round(
                    results[i].reranked_count / results[i].candidate_count, 4
                )
            results[i].context_awareness = await self._compute_context_awareness(
                sample, answer
            )

        return results

    @staticmethod
    def aggregate(results: list[EvalResult]) -> dict[str, float]:
        """Return per-metric mean across all results, skipping None values."""
        if not results:
            return {}

        metric_fields = [
            "faithfulness_score", "context_precision", "context_recall",
            "hallucination_rate", "retrieval_ratio",   "relevancy_score",
            "context_awareness",  "answer_quality",
            "retrieval_ms",       "generation_ms",      "total_ms",
            "input_tokens",       "output_tokens",
        ]
        agg: dict[str, float] = {"sample_count": float(len(results))}
        for fname in metric_fields:
            vals = [v for r in results if (v := getattr(r, fname)) is not None]
            agg[fname] = round(mean(vals), 4) if vals else float("nan")
        return agg

    # ── private helpers ───────────────────────────────────────────────────────

    async def _compute_ragas_metrics(
        self,
        samples: list[EvalSample],
        answers: list[str],
        results: list[EvalResult],
    ) -> list[EvalResult]:
        """Single RAGAS evaluate() call covering the full batch."""
        if not _RAGAS_AVAILABLE:
            return results

        data = {
            "question":     [r.question for r in results],
            "answer":       [r.answer for r in results],
            "contexts":     [r.retrieved_contexts for r in results],
            "ground_truth": [s.ground_truth for s in samples],
        }
        dataset = Dataset.from_dict(data)
        metrics = [
            faithfulness,
            answer_relevancy,
            context_precision,
            context_recall,
            answer_correctness,
        ]

        import litellm
        from ragas.embeddings import LiteLLMEmbeddings
        from ragas.llms.litellm_llm import LiteLLMStructuredLLM

        ragas_llm = LiteLLMStructuredLLM(
            client=litellm.completion,
            model="openai/gpt-4o-mini",
            provider="openai",
        )
        ragas_emb = LiteLLMEmbeddings(model="openai/text-embedding-3-small")

        # evaluate() is synchronous — offload to executor to avoid blocking the loop
        loop = asyncio.get_event_loop()
        ragas_result = await loop.run_in_executor(
            None,
            lambda: _ragas_evaluate(
                dataset=dataset,
                metrics=metrics,
                llm=ragas_llm,
                embeddings=ragas_emb,
                show_progress=False,
            ),
        )
        df = ragas_result.to_pandas()

        for i, result in enumerate(results):
            row = df.iloc[i]
            result.faithfulness_score = float(row.get("faithfulness")       or 0.0)
            result.relevancy_score    = float(row.get("answer_relevancy")   or 0.0)
            result.context_precision  = float(row.get("context_precision")  or 0.0)
            result.context_recall     = float(row.get("context_recall")     or 0.0)
            result.answer_quality     = float(row.get("answer_correctness") or 0.0)

        return results

    async def _compute_context_awareness(
        self,
        sample: EvalSample,
        answer: str,
    ) -> float:
        """
        LLM judge for multi-turn samples: score how well the answer
        uses conversation history.  Returns 1.0 for single-turn samples.
        """
        if not sample.history:
            return 1.0

        history_str = "\n".join(
            f"{m['role'].capitalize()}: {m['content']}"
            for m in sample.history[-6:]
        )
        resp = await litellm.acompletion(
            model="openai/gpt-4o-mini",
            messages=[
                {"role": "system", "content": _CA_SYSTEM},
                {"role": "user",   "content": _CA_USER.format(
                    history=history_str,
                    question=sample.question,
                    answer=answer,
                )},
            ],
            temperature=0,
            max_tokens=8,
        )
        raw = resp.choices[0].message.content.strip()
        try:
            return max(0.0, min(1.0, float(raw)))
        except ValueError:
            return 0.0
