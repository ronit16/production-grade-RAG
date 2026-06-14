# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

---

## Commands

### Docker (primary workflow)

```bash
# Build and start everything
docker compose up -d --build

# Rebuild only the API after code changes
docker compose up -d --build api

# Check all container statuses
docker compose ps

# Tail API logs
docker logs production_grade_rag-api-1 -f
```

### Tests (run from `backend/`)

```bash
cd backend

# Default run — all non-slow, non-integration tests; real containers via Testcontainers (auto-started)
pytest

# Single test file
pytest tests/regression/test_auth.py -v

# Single test by name
pytest tests/regression/test_auth.py::test_register_success -v

# Unit tests only (no Docker containers needed)
pytest tests/unit/ -v --no-containers

# Full regression suite (includes auth, documents, sessions, health)
pytest tests/regression/ -v

# Multi-tenant / multi-user HTTP isolation tests (marked 'integration')
pytest -m integration -v
pytest tests/regression/test_multitenancy.py -v   # 7 cross-tenant isolation tests
pytest tests/regression/test_multiuser.py -v      # 9 multi-user (same tenant) tests
pytest tests/regression/test_multisession.py -v   # 10 multi-session per user tests

# Include slow tests (requires running stack + real LLM API keys)
pytest tests/ -v -m ""

# Regression suite with coverage
pytest tests/regression/ --cov=app --cov-report=html
```

`pytest.ini` defaults: `asyncio_mode = auto`, 60 s timeout per test, `-m "not slow"` filter applied automatically.

Two markers are registered:
- `slow` — requires a real Celery worker or LLM API calls (excluded by default)
- `integration` — HTTP-layer tests spanning multiple tenants or users (excluded by default)

### Evaluation tests

```bash
cd backend

# Fast — unit/mock tests, no containers or API key required
pytest tests/evaluation/ --no-containers -v

# Live — real retrieve + generate + RAGAS scoring (requires real GEMINI_API_KEY)
export GEMINI_API_KEY=AI-...your-real-key...
pytest tests/evaluation/ -m slow -v

# Multi-tenant corpus divergence evaluation (Acme vs RFC 7231 corpora)
GEMINI_API_KEY=<key> pytest tests/evaluation/test_multitenant_eval.py -m slow -v
```

The live tests auto-skip if `GEMINI_API_KEY` is absent or equals `test-fake-gemini-key`.
RAGAS scoring uses `gemini/gemini-2.0-flash` — not OpenAI.

Two golden datasets exist:
- `GOLDEN_SAMPLES` — 5 Acme Corp policy Q&A samples (single-tenant baseline)
- `GOLDEN_SAMPLES_RFC` — 3 RFC 7231 HTTP semantics samples, including a multi-turn follow-up

### Load tests (requires running stack)

```bash
# Interactive UI at http://localhost:8089
locust -f backend/tests/load/locustfile.py --host http://localhost:8000

# Headless — ramp to 50 users, 5 min run
locust -f backend/tests/load/locustfile.py \
  --headless --host http://localhost:8000 \
  --users 50 --spawn-rate 5 --run-time 5m \
  --html backend/tests/load/report.html
```

---

## Architecture

### Request lifecycle

```
HTTP → CORSMiddleware
     → auth.py: HTTPBearer extracts JWT → decode_jwt() (RS256, /secrets/jwt_public.pem)
                                        → get_tenant_ctx() builds TenantContext (cached in Redis 60 s)
                                        → check_rate_limit() (token-bucket per tenant in Redis)
     → endpoint handler receives: ctx: TenantContext, db: AsyncSession, redis: Redis
     → services/retriever.py   (hybrid search + rerank)
     → services/generator.py   (LiteLLM streaming)
     → SSE response
```

The `TenantContext` object (`middleware/auth.py`) carries `tenant_id`, `user_id`, `role`, per-plan limits (`max_docs`, `tokens_day`, `rps`), and `rag_config` overrides. It is the single gating object — always pass it into service calls, never bypass it.

### Ingestion pipeline (Celery worker)

```
POST /v1/documents
  → upload file to MinIO (s3://{S3_PREFIX}/{tenant_id}/{doc_id}/{filename})
  → create Document row (status=PENDING)
  → dispatch Celery task to "ingest" queue

Celery worker (workers/ingestion.py):
  1. Download from MinIO → parse with Unstructured → split into chunks
  2. Embed dense:  OpenAI text-embedding-3-large (batch=256)
  3. Embed sparse: fastembed BM25 (onnxruntime, no PyTorch)
  4. Upsert to Qdrant (batch=100 points), payload includes tenant_id + user_id
  5. Insert Chunk rows into PostgreSQL
  6. Update Document.status = READY (or FAILED on error, up to 3 retries)
```

All module-level clients in `ingestion.py` (`oai`, `qdrant`, `sparse_model`, `s3`, `engine`) are initialized once per Celery worker process — not per task.

### Retrieval pipeline (services/retriever.py)

```
retrieve(question, ctx)
  1. rewrite_query()     — gpt-4o-mini makes follow-ups self-contained
  2. hybrid_search()     — parallel dense + sparse embed, then Qdrant Prefetch + Fusion.RRF
  3. rerank()            — fastembed TextCrossEncoder (ONNX ms-marco-MiniLM-L-6-v2)
  → RetrievalResult(chunks, rewritten_query, retrieval_ms, candidate_count)
```

All four singletons (`_oai_client`, `_qdrant_client`, `_sparse_model`, `_cross_encoder`) are lazy-loaded and module-global — they survive across requests within a Gunicorn worker process.

### Evaluation pipeline (services/evaluator.py)

```
EvaluationPipeline(ctx).run_dataset(samples)
  Phase 1: for each EvalSample → retrieve() + generate_sync() → answer, RetrievalResult, usage
  Phase 2: single RAGAS evaluate() call for full batch (faithfulness, relevancy, precision,
           recall, correctness) — run in executor so it doesn't block the event loop
           Uses gemini/gemini-2.0-flash as the RAGAS LLM judge (GEMINI_API_KEY required)
  Phase 3: derive hallucination_rate (1−faithfulness), retrieval_ratio (reranked/candidates),
           context_awareness (gpt-4o-mini LLM judge for multi-turn; 1.0 for single-turn)
  → list[EvalResult]  +  EvaluationPipeline.aggregate(results) → dict[metric, float]
```

`EvalResult` carries all 8 metric fields plus `retrieval_ms`, `generation_ms`, `total_ms`, and token counts. RAGAS imports are guarded with `try/except ImportError` so the service loads cleanly in environments where `ragas` is not installed.

`tests/evaluation/test_multitenant_eval.py` verifies that two `EvaluationPipeline` instances with different `TenantContext` objects are fully independent, and (via slow tests) that answers from different corpora diverge — Tenant A (Acme policy) gets refund answers, Tenant B (RFC 7231) gets HTTP semantics answers.

### Tenant isolation — where it is enforced

| Layer | File | Mechanism |
|---|---|---|
| Auth | `middleware/auth.py` | JWT claim `tenant_id` decoded into TenantContext |
| Vector search | `services/retriever.py` `_tenant_filter()` | Every Qdrant Prefetch carries `FieldCondition(tenant_id==...)` |
| DB queries | All endpoint handlers | `WHERE tenant_id = :tid` on every query |
| Object storage | `workers/ingestion.py` | S3 key prefix `{S3_PREFIX}/{tenant_id}/...` |
| Redis sessions | `services/session.py` | Key `session:{tenant_id}:{session_id}` |
| Rate limiting | `middleware/auth.py` | Per-tenant token bucket in Redis |

### Database / Redis setup (core/database.py)

- **PostgreSQL**: `create_async_engine` with `asyncpg`, `pool_size=5`, `max_overflow=10` per Gunicorn worker (4 workers × 15 = 60 max connections; PostgreSQL configured with `max_connections=200`).
- **Redis**: `redis.asyncio` pool, `max_connections=50`. Used for: session cache (DB 0), Celery results (DB 1), rate-limit counters, tenant context cache (TTL 60 s).
- `init_db()` (called in lifespan): runs SQLAlchemy `create_all` + applies any pending SQL migrations from `backend/migrations/`.
- `ensure_collection()` (called in lifespan): idempotently creates the Qdrant collection with named dense + sparse vector configs and payload indexes.

### Process model

The API runs as **Gunicorn + 4 Uvicorn workers** (`gunicorn -k uvicorn.workers.UvicornWorker -w 4`). Each worker has its own asyncio event loop, its own DB connection pool, and its own in-process model singletons. `uvicorn --workers` (fork-based) is intentionally avoided because `onnxruntime` (used by `fastembed`) is not fork-safe.

The Celery worker runs with **8 concurrent processes** (`-c 8`) on the `ingest` queue. `worker_prefetch_multiplier=1` ensures one task per process at a time.

### Adding a new endpoint

1. Create handler in `backend/app/api/v1/endpoints/`.
2. Declare dependencies: `ctx: TenantContext = Depends(get_tenant_ctx)`, `db: AsyncSession = Depends(get_db)`, `redis: Redis = Depends(get_redis)`.
3. Register in `backend/app/api/v1/router.py`.
4. Add regression test in `backend/tests/regression/`.

### Key configuration knobs (core/config.py)

| Setting | Default | Effect |
|---|---|---|
| `DATABASE_POOL_SIZE` | 5 | Per-worker DB pool (× 4 workers = 20 idle) |
| `DATABASE_MAX_OVERFLOW` | 10 | Per-worker burst (× 4 workers = 40 extra) |
| `RETRIEVAL_TOP_K` | 20 | Qdrant candidates before rerank |
| `RERANK_TOP_K` | 5 | Chunks sent to LLM after rerank |
| `INGEST_CONCURRENCY` | 8 | Must match Celery `-c` flag in docker-compose |
| `APP_ENV` | `production` | Set to `development` to enable `/docs` Swagger UI |

### JWT key setup (required before first run)

```bash
mkdir -p backend/secrets
openssl genrsa -out backend/secrets/jwt_private.pem 4096
openssl rsa -in backend/secrets/jwt_private.pem -pubout -out backend/secrets/jwt_public.pem
```

Keys are mounted read-only into the container at `/secrets/`. The API reads them at every `decode_jwt()` call (no caching needed — small files).
