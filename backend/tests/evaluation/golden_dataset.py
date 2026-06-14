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

# ── RFC 7231 domain — used by TestMultiTenantRAGASScores ─────────────────────
# These samples target the tech_specs.txt fixture corpus (HTTP semantics content).

GOLDEN_SAMPLES_RFC: list[EvalSample] = [
    EvalSample(
        question="What HTTP request methods are described and what do they do?",
        ground_truth=(
            "GET requests a representation of the target resource. "
            "POST submits data for processing or creates a new resource. "
            "PUT replaces the resource's state with the supplied representation. "
            "DELETE removes the resource. HEAD is identical to GET but without "
            "a response body. PATCH applies partial modifications."
        ),
        reference_contexts=[
            "The GET method requests transfer of a current selected representation "
            "for the target resource.",
            "The POST method requests that the target resource process the representation "
            "enclosed in the request according to the resource's own specific semantics.",
            "The PUT method requests that the state of the target resource be created or "
            "replaced with the state defined by the representation in the request.",
            "The DELETE method requests that the origin server remove the association "
            "between the target resource and its current functionality.",
            "The PATCH method requests that a set of changes be applied to the resource.",
        ],
    ),
    EvalSample(
        question="What do 4xx HTTP status codes indicate and what are some examples?",
        ground_truth=(
            "4xx status codes indicate that the client seems to have erred. "
            "400 means the request is malformed. 401 means authentication is required. "
            "403 means the server refuses to authorize the request. "
            "404 means the resource was not found. 429 means too many requests."
        ),
        reference_contexts=[
            "The 4xx (Client Error) class of status code indicates that the client "
            "seems to have erred.",
            "400 Bad Request: The server cannot process the request due to a client error "
            "such as malformed request syntax.",
            "401 Unauthorized: The request lacks valid authentication credentials.",
            "403 Forbidden: The server understood the request but refuses to authorize it.",
            "404 Not Found: The origin server did not find a current representation for "
            "the target resource.",
            "429 Too Many Requests: The user has sent too many requests in a given time.",
        ],
    ),
    # Multi-turn: exercises _compute_context_awareness for the RFC domain
    EvalSample(
        question="What about 5xx codes — when does the server return those?",
        ground_truth=(
            "5xx status codes indicate that the server is aware it has erred. "
            "500 Internal Server Error means an unexpected condition prevented the response. "
            "502 Bad Gateway means the gateway received an invalid response from upstream. "
            "503 Service Unavailable means the server is temporarily overloaded or down."
        ),
        reference_contexts=[
            "The 5xx (Server Error) class of status codes indicates that the server is "
            "aware that it has erred or is incapable of performing the requested method.",
            "500 Internal Server Error: The server encountered an unexpected condition.",
            "502 Bad Gateway: The server received an invalid response from an inbound server.",
            "503 Service Unavailable: The server is temporarily unable to handle the request.",
        ],
        history=[
            {
                "role":    "user",
                "content": "What do 4xx HTTP status codes indicate?",
            },
            {
                "role":    "assistant",
                "content": (
                    "4xx codes indicate client errors. For example, 400 is a bad request, "
                    "401 requires authentication, 403 is forbidden, and 404 means not found."
                ),
            },
        ],
    ),
]
