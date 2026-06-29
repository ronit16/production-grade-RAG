# scripts/run_eval.py
import asyncio, os, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from dotenv import load_dotenv
load_dotenv(Path(__file__).resolve().parent.parent / ".env")

from app.services.evaluator import EvaluationPipeline
from tests.evaluation.golden_dataset import GOLDEN_SAMPLES, METRIC_THRESHOLDS

async def main():
    # Minimal ctx — replace with a real TenantContext from a live DB if running live
    from unittest.mock import MagicMock
    import uuid
    ctx = MagicMock()
    ctx.tenant_id  = uuid.uuid4()
    ctx.llm_config = {}
    ctx.rag_config = {}

    pipeline = EvaluationPipeline(ctx)
    results  = await pipeline.run_dataset(GOLDEN_SAMPLES)
    agg      = EvaluationPipeline.aggregate(results)

    print(f"\n{'Metric':<22} {'Score':>8}  {'Threshold':>10}  {'Status':>6}")
    print("─" * 55)
    upper = {"hallucination_rate"}
    for metric, threshold in METRIC_THRESHOLDS.items():
        val = agg.get(metric)
        if val is None or val != val:
            print(f"  {metric:<20}  {'N/A':>8}  {threshold:>10.2f}  {'–':>6}")
            continue
        ok  = (val <= threshold) if metric in upper else (val >= threshold)
        tag = "PASS" if ok else "FAIL"
        print(f"  {metric:<20}  {val:>8.4f}  {threshold:>10.2f}  {tag:>6}")

    print(f"\n  sample_count = {int(agg['sample_count'])}")
    print(f"  avg retrieval_ms  = {agg['retrieval_ms']:.0f} ms")
    print(f"  avg generation_ms = {agg['generation_ms']:.0f} ms")
    print(f"  avg total_ms      = {agg['total_ms']:.0f} ms")

asyncio.run(main())
