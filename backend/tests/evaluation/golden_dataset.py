"""
Golden evaluation dataset for offline RAGAS evaluation.

5 samples covering: policy, technical specs, multi-turn follow-up,
document processing timing, and file format support.
Sample 3 (index 2) has a history field — it exercises the
context_awareness LLM judge path in EvaluationPipeline.
"""
from app.services.evaluator import EvalSample

GOLDEN_SAMPLES: list[EvalSample] = [
    EvalSample(
        question="What is the company's refund policy?",
        ground_truth=(
            "Customers can request a full refund within 30 days of purchase. "
            "After 30 days, store credit may be issued at the company's discretion."
        ),
        reference_contexts=[
            "Our refund policy allows customers to request a full refund within 30 days of purchase.",
            "After 30 days, store credit may be issued at our discretion.",
            "Refund requests must be submitted through the customer portal with proof of purchase.",
        ],
    ),
    EvalSample(
        question="What are the minimum system requirements?",
        ground_truth=(
            "The minimum system requirements are 8 GB RAM, a 4-core CPU, "
            "and 10 GB of free disk space."
        ),
        reference_contexts=[
            "Minimum system requirements: 8 GB RAM, 4-core processor, 10 GB free disk space.",
            "Recommended configuration: 16 GB RAM, 8-core processor, SSD storage.",
            "Supported operating systems: Windows 10/11, macOS 12+, Ubuntu 22.04 or later.",
        ],
    ),
    # Multi-turn: exercises _compute_context_awareness LLM judge
    EvalSample(
        question="Does it also support batch uploads?",
        ground_truth=(
            "Yes, the system supports batch uploads of up to 50 files at once "
            "via the POST /v1/documents/batch endpoint."
        ),
        reference_contexts=[
            "Single file uploads are accepted via POST /v1/documents.",
            "Batch uploads of up to 50 files are supported via the /v1/documents/batch endpoint.",
            "Supported formats for batch upload include PDF, DOCX, HTML, and plain text.",
        ],
        history=[
            {"role": "user",      "content": "How do I upload documents to the knowledge base?"},
            {"role": "assistant", "content": "Use POST /v1/documents to upload a single file."},
        ],
    ),
    EvalSample(
        question="How long does it take for an uploaded document to become searchable?",
        ground_truth=(
            "Standard documents are searchable within 2–5 minutes. "
            "Large documents over 100 pages may take up to 10 minutes."
        ),
        reference_contexts=[
            "After upload, documents enter a Celery processing queue managed by the worker.",
            "Standard documents (under 100 pages) are indexed and searchable within 2–5 minutes.",
            "Documents exceeding 100 pages may require up to 10 minutes for full processing.",
            "Processing status can be polled via GET /v1/documents/{id}/status.",
        ],
    ),
    EvalSample(
        question="Which file formats are supported for document ingestion?",
        ground_truth=(
            "PDF, DOCX, HTML, Markdown (.md), and plain text (.txt) files are supported."
        ),
        reference_contexts=[
            "Supported input formats: PDF (.pdf), Word documents (.docx), HTML (.html), "
            "Markdown (.md), and plain text (.txt).",
            "Files are parsed using the Unstructured library for layout-aware text extraction.",
            "Maximum file size per upload is 50 MB; larger files are rejected with a 413 error.",
        ],
    ),
]

# Thresholds used by TestRAGASMetrics.
# hallucination_rate is an upper bound (assert <=); all others are lower bounds (assert >=).
METRIC_THRESHOLDS: dict[str, float] = {
    "faithfulness_score": 0.80,
    "relevancy_score":    0.75,
    "context_precision":  0.70,
    "context_recall":     0.75,
    "answer_quality":     0.65,
    "hallucination_rate": 0.20,
    "retrieval_ratio":    0.10,
    "context_awareness":  0.70,
}
