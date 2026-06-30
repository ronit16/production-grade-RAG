#!/usr/bin/env python3
"""
Read eval_summary.json (written by test_ragas.py) and print a Markdown table
to stdout for GitHub Actions Job Summary.

Usage (in CI):
    python scripts/ci_eval_summary.py eval_summary.json >> $GITHUB_STEP_SUMMARY
"""
import json
import sys
from pathlib import Path

METRIC_LABELS = {
    "faithfulness_score": "Faithfulness",
    "context_precision":  "Context Precision",
    "context_recall":     "Context Recall",
    "relevancy_score":    "Answer Relevancy",
    "answer_quality":     "Answer Correctness",
    "hallucination_rate": "Hallucination Rate ↓",
    "retrieval_ratio":    "Retrieval Ratio",
    "context_awareness":  "Context Awareness",
}

# Upper-bound metrics: PASS when value <= threshold
UPPER_BOUND = {"hallucination_rate"}

# Must match METRIC_THRESHOLDS in golden_dataset.py
THRESHOLDS: dict[str, float] = {
    "faithfulness_score": 0.75,
    "relevancy_score":    0.72,
    "context_precision":  0.68,
    "context_recall":     0.70,
    "answer_quality":     0.60,
    "hallucination_rate": 0.25,
    "retrieval_ratio":    0.10,
    "context_awareness":  0.70,
}


def main() -> int:
    path = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("eval_summary.json")

    if not path.exists():
        print("## RAGAS Evaluation\n\nNo `eval_summary.json` found — evaluation did not run.")
        return 0

    try:
        data = json.loads(path.read_text())
    except json.JSONDecodeError as exc:
        print(f"## RAGAS Evaluation\n\nFailed to parse `eval_summary.json`: {exc}")
        return 1

    sample_count = int(data.get("sample_count", 0))
    print("## RAGAS Evaluation Results\n")
    print(f"**Samples evaluated:** {sample_count}\n")
    print("| Metric | Score | Threshold | Status |")
    print("|--------|------:|----------:|--------|")

    all_pass = True
    for key, label in METRIC_LABELS.items():
        value = data.get(key)
        if value is None:
            continue
        try:
            value = float(value)
        except (TypeError, ValueError):
            continue
        if value != value:  # NaN
            continue

        threshold = THRESHOLDS.get(key)
        if threshold is not None:
            if key in UPPER_BOUND:
                passed = value <= threshold
                direction = "≤"
            else:
                passed = value >= threshold
                direction = "≥"
            status = "✅ PASS" if passed else "❌ FAIL"
            threshold_str = f"{direction} {threshold:.2f}"
            if not passed:
                all_pass = False
        else:
            status = "—"
            threshold_str = "—"

        print(f"| {label} | {value:.3f} | {threshold_str} | {status} |")

    print()
    if all_pass:
        print("> **All metrics passed their thresholds.**")
    else:
        print("> **⚠️ One or more metrics failed thresholds. See test output for details.**")

    return 0 if all_pass else 1


if __name__ == "__main__":
    sys.exit(main())
