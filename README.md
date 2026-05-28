# Production RAG System

A production-grade Retrieval-Augmented Generation (RAG) system with multi-tenant isolation, hybrid vector search, streaming responses, and a ChatGPT-style Next.js frontend.

---

## Architecture

```
Browser / API Client
       │
       ▼
  Next.js Frontend  (port 3001)
       │
       ▼
FastAPI  ──── CORSMiddleware
  │
  ├── Auth Middleware  (RS256 JWT  |  API key → TenantContext)
  ├── Rate Limiter     (token-bucket per tenant via Redis)
  │
  ├── POST /v1/auth/register
  ├── POST /v1/auth/login
  │
  ├── POST /v1/documents       → MinIO upload + Celery task dispatch
  ├── GET  /v1/documents/:id
  │
  ├── POST /v1/sessions
  ├── GET  /v1/sessions
  ├── DEL  /v1/sessions/:id
  │
  ├── POST /v1/query  ──── SSE stream
  │           │
  │           ├── 1. Query rewrite        (gpt-4o-mini)
  │           ├── 2. Hybrid search        (Qdrant: dense + sparse → native RRF)
  │           ├── 3. Cross-encoder rerank (fastembed ONNX — no PyTorch/CUDA)
  │           └── 4. LLM generation       (LiteLLM: GPT-4o → Gemini fallback)
  │
  ├── GET /v1/health
  ├── GET /v1/ready
  └── GET /v1/health/detailed   → probes all 5 backing services

Background
  └── Celery worker  (RabbitMQ broker, 8 concurrent processes)
        └── parse (Unstructured) → chunk → embed dense (OpenAI)
                                          + embed sparse (fastembed BM25)
                                          → upsert to Qdrant
                                          → persist metadata to PostgreSQL
```

---

## Key design decisions

| Concern | Choice | Rationale |
|---|---|---|
| **Vector DB** | Qdrant (single collection, payload-filtered per tenant) | Supports dense + sparse vectors natively; built-in RRF fusion; self-hostable or cloud |
| **Dense search** | OpenAI `text-embedding-3-large` (1536-dim) | State-of-the-art retrieval accuracy |
| **Sparse search** | BM25 via `fastembed` (`Qdrant/bm25`) | Exact-match, acronyms, rare terms — no separate search cluster needed |
| **Hybrid fusion** | Qdrant native `Prefetch + Fusion.RRF` | Zero extra infrastructure; equal-weight RRF in a single query call |
| **Reranker** | `cross-encoder/ms-marco-MiniLM-L-6-v2` via `fastembed.TextCrossEncoder` (ONNX) | Same MiniLM model, ~40% precision lift; no PyTorch/CUDA — saves ~1.3 GB from image |
| **Session store** | Redis (hot) + PostgreSQL (cold) | Sub-ms reads for active sessions; durable audit trail |
| **Task queue** | Celery + RabbitMQ | Reliable async ingestion; horizontal worker scaling |
| **Auth** | RS256 JWT + API keys | Stateless; no DB hit on every request |
| **LLM routing** | LiteLLM | Provider-agnostic; automatic fallback (GPT-4o → Gemini) |
| **Streaming** | Server-Sent Events (SSE) | Works with any HTTP client |
| **Testing** | Testcontainers | Regression tests spin up real containers — no mocks, no manual setup |

---

## Project structure

```
production_grade_RAG/
├── backend/
│   ├── app/
│   │   ├── main.py                        # App factory: middleware, lifespan, routers
│   │   ├── api/
│   │   │   ├── deps.py                    # Shared dependency aliases (DBSession, RedisClient)
│   │   │   └── v1/
│   │   │       ├── router.py
│   │   │       └── endpoints/
│   │   │           ├── health.py          # GET /health, /ready, /health/detailed
│   │   │           ├── auth.py            # POST /auth/register, /auth/login
│   │   │           ├── documents.py       # POST/GET /v1/documents
│   │   │           ├── sessions.py        # POST/GET/DELETE /v1/sessions
│   │   │           └── query.py           # POST /v1/query  (SSE stream)
│   │   ├── core/
│   │   │   ├── config.py                  # Pydantic settings (all env vars)
│   │   │   ├── database.py                # Async SQLAlchemy engine + Redis pool + init_db
│   │   │   └── exceptions.py
│   │   ├── middleware/
│   │   │   └── auth.py                    # JWT/API-key auth, TenantContext, rate limiting
│   │   ├── models/
│   │   │   └── db.py                      # SQLAlchemy ORM models (8 tables)
│   │   ├── schemas/
│   │   │   ├── document.py
│   │   │   ├── session.py
│   │   │   └── query.py
│   │   ├── services/
│   │   │   ├── retriever.py               # Hybrid retrieval: dense+sparse → RRF → rerank
│   │   │   ├── generator.py               # LLM streaming (LiteLLM, citations, fallback)
│   │   │   ├── session.py                 # SessionManager: Redis ↔ PostgreSQL lifecycle
│   │   │   └── evaluator.py               # RAGAS evaluation pipeline (8 metrics)
│   │   └── workers/
│   │       ├── celery_app.py
│   │       └── ingestion.py               # Celery task: parse → embed → Qdrant → DB
│   ├── migrations/
│   │   └── 001_add_user_id_to_queries.sql # Applied automatically on startup
│   ├── tests/
│   │   ├── conftest.py                    # Testcontainers startup (pytest_configure hook)
│   │   ├── regression/                    # Live-service regression tests
│   │   │   ├── conftest.py                # Auth helpers, session fixtures
│   │   │   ├── fixtures/sample.txt        # Synthetic document for upload tests
│   │   │   ├── test_health.py
│   │   │   ├── test_auth.py
│   │   │   ├── test_sessions.py
│   │   │   ├── test_documents.py
│   │   │   └── test_query.py              # SSE streaming tests with respx mocks
│   │   ├── unit/
│   │   │   ├── test_chunking.py
│   │   │   ├── test_rrf.py
│   │   │   └── test_session.py
│   │   ├── integration/
│   │   │   ├── test_tenant_isolation.py
│   │   │   └── test_session_management.py
│   │   ├── load/
│   │   │   └── locustfile.py              # 50-user step ramp-up load test
│   │   └── evaluation/
│   │       ├── conftest.py                # Auth fixtures for evaluation tests
│   │       ├── golden_dataset.py          # 5-sample golden Q&A set + metric thresholds
│   │       └── test_ragas.py              # RAGAS golden-set evaluation (7 test classes)
│   ├── pytest.ini
│   └── requirements.txt
├── frontend/                              # Next.js 14 ChatGPT-style UI
├── docker-compose.yml                     # Application stack
└── .env.example
```

---

## Quick start

### Prerequisites

- Docker & Docker Compose v2
- An OpenAI API key (`OPENAI_API_KEY`)
- A Gemini API key (`GEMINI_API_KEY`) for LLM fallback

### 1 — Clone and configure

```bash
git clone <repo>
cd production_grade_RAG
cp .env.example .env
# Edit .env — set SECRET_KEY, OPENAI_API_KEY, GEMINI_API_KEY at minimum
```

### 2 — Generate JWT keys

```bash
mkdir -p backend/secrets
openssl genrsa -out backend/secrets/jwt_private.pem 4096
openssl rsa -in backend/secrets/jwt_private.pem -pubout -out backend/secrets/jwt_public.pem
```

### 3 — Start the full stack

```bash
docker compose up --build -d
```

All services start with health checks. The API is ready at **http://localhost:8000** once `docker compose ps` shows all services as `healthy`.

The API runs under **Gunicorn + 4 Uvicorn workers** (`gunicorn -k uvicorn.workers.UvicornWorker -w 4`). All async FastAPI features (SSE streaming, WebSockets, async DB/Redis) work identically — Gunicorn is purely the process manager.

> **Swagger UI** (development mode only): http://localhost:8000/docs

### 4 — Verify

```bash
curl http://localhost:8000/v1/health
# → {"status": "ok", "version": "1.0.0"}

curl http://localhost:8000/v1/health/detailed
# → {"status": "healthy", "checks": {"postgres": {...}, "redis": {...}, ...}}
```

### Port reference

| Service | URL |
|---|---|
| FastAPI | http://localhost:8000 |
| Frontend (Next.js) | http://localhost:3001 |
| PostgreSQL | localhost:5433 |
| Redis | localhost:6381 |
| RabbitMQ management | http://localhost:15672 (guest/guest) |
| Qdrant | http://localhost:6333 |
| MinIO console | http://localhost:9003 (minioadmin/minioadmin) |

---

## Running tests

### Regression tests (Testcontainers)

Containers start automatically — no running stack required.

```bash
cd backend

# Full regression suite
pytest tests/regression/ -v

# Skip slow tests (those requiring a real Celery worker + LLM keys)
pytest tests/regression/ -v -m "not slow"

# Unit tests only (no containers)
pytest tests/unit/ -v --no-containers

# All tests with coverage
pytest tests/ --cov=app --cov-report=html -m "not slow"
```

**How Testcontainers works here:** `pytest_configure` in `tests/conftest.py` starts real Docker containers for Postgres, Redis, Qdrant, MinIO, and RabbitMQ before any test module is imported, then injects their URLs into `os.environ`. OpenAI and Gemini HTTP calls are intercepted by `respx` so no API keys are needed for regression tests.

### Load tests (Locust)

Requires the application stack to be running (`docker compose up -d`).

```bash
# Interactive web UI → http://localhost:8089
locust -f backend/tests/load/locustfile.py --host http://localhost:8000

# Headless — ramp to 50 users over 4 minutes, generate HTML report
locust -f backend/tests/load/locustfile.py \
  --headless --host http://localhost:8000 \
  --users 50 --spawn-rate 5 --run-time 5m \
  --html backend/tests/load/report.html \
  --csv backend/tests/load/results
```

Load shape: warm-up (10 users) → ramp (25) → peak (50) → hold.

**Target SLOs under 50 concurrent users:**

| Endpoint | P95 target |
|---|---|
| GET /v1/health | < 50 ms |
| POST /v1/sessions | < 500 ms |
| POST /v1/query | < 30 s (LLM-bound) |
| Overall error rate | < 1% |

### RAGAS evaluation

```bash
# Fast unit tests — no containers, no API key required
pytest tests/evaluation/ --no-containers -v

# Full live evaluation — requires a real OPENAI_API_KEY and running stack
export OPENAI_API_KEY=sk-...
pytest tests/evaluation/ -m slow -v
```

The evaluation pipeline (`app/services/evaluator.py`) runs the full retrieve + generate cycle against a 5-sample golden dataset and scores 8 metric categories:

| Metric | Threshold | Method |
|---|---|---|
| `faithfulness_score` | ≥ 0.80 | RAGAS `faithfulness` |
| `context_precision` | ≥ 0.70 | RAGAS `context_precision` |
| `context_recall` | ≥ 0.75 | RAGAS `context_recall` |
| `relevancy_score` | ≥ 0.75 | RAGAS `answer_relevancy` |
| `answer_quality` | ≥ 0.65 | RAGAS `answer_correctness` |
| `hallucination_rate` | ≤ 0.20 | `1 − faithfulness_score` |
| `retrieval_ratio` | ≥ 0.10 | `reranked_count / candidate_count` |
| `context_awareness` | ≥ 0.70 | `gpt-4o-mini` LLM judge (multi-turn only) |

---

## API reference

### Authentication

```bash
# Register
curl -X POST http://localhost:8000/v1/auth/register \
  -H "Content-Type: application/json" \
  -d '{"username": "alice", "email": "alice@example.com", "password": "Secret1234!"}'
# → {"access_token": "...", "token_type": "bearer", "user_id": "...", "tenant_id": "..."}

# Login
curl -X POST http://localhost:8000/v1/auth/login \
  -H "Content-Type: application/json" \
  -d '{"email": "alice@example.com", "password": "Secret1234!"}'
```

### Upload a document

```bash
curl -X POST http://localhost:8000/v1/documents \
  -H "Authorization: Bearer <token>" \
  -F "file=@report.pdf"
# → {"document_id": "...", "status": "processing", "filename": "report.pdf"}
```

Supported types: `application/pdf`, `text/plain`, `text/markdown`, `text/html`, `.docx`

### Poll document status

```bash
curl http://localhost:8000/v1/documents/<document_id> \
  -H "Authorization: Bearer <token>"
# → {"status": "ready", "chunk_count": 42, "processing_ms": 3200, ...}
```

### Create a session and query

```bash
# Create session
curl -X POST http://localhost:8000/v1/sessions \
  -H "Authorization: Bearer <token>"
# → {"session_id": "...", "created_at": 1715000000.0}

# Stream a RAG query (SSE)
curl -N -X POST http://localhost:8000/v1/query \
  -H "Authorization: Bearer <token>" \
  -H "Content-Type: application/json" \
  -d '{"session_id": "...", "question": "What is our refund policy?"}'
```

**SSE event sequence:**

| Event | Payload |
|---|---|
| `status` | `{"status": "retrieving"}` |
| `retrieval` | `{"chunk_count": 5, "rewritten_query": "..."}` |
| `status` | `{"status": "generating"}` |
| `delta` | `{"text": "token..."}` (repeated) |
| `done` | `{"sources": [...], "query_id": "..."}` |
| `error` | `{"error": "..."}` (on failure) |

---

## Hybrid retrieval pipeline

```
Question
   │
   ▼
Query rewrite  (gpt-4o-mini — makes follow-ups self-contained)
   │
   ├──────────────────────────────┐
   ▼                              ▼
Dense embedding              Sparse embedding
(OpenAI text-embedding-3-large) (fastembed BM25)
   │                              │
   └──────────┬───────────────────┘
              ▼
       Fusion.RRF  (Qdrant native — single round-trip)
              │
              ▼
   Cross-encoder rerank  (fastembed ONNX MiniLM, top rerank_top_k results)
              │
              ▼
     Final chunks → LLM context → streaming SSE response
```

**Tenant isolation:** every Qdrant query carries a payload filter `tenant_id == ctx.tenant_id` on both Prefetch branches — tenants never see each other's data.

---

## Environment variables

| Variable | Required | Default | Description |
|---|:---:|---|---|
| `SECRET_KEY` | ✓ | — | 32+ char secret for miscellaneous signing |
| `DATABASE_URL` | ✓ | — | `postgresql+asyncpg://user:pass@host/db` |
| `REDIS_URL` | | `redis://localhost:6379/0` | Session + rate-limit store |
| `OPENAI_API_KEY` | ✓ | — | Embeddings (`text-embedding-3-large`) + GPT-4o |
| `GEMINI_API_KEY` | ✓ | — | Gemini fallback LLM via LiteLLM |
| `MINIO_ENDPOINT` | | `http://localhost:9000` | MinIO (S3-compatible) endpoint |
| `MINIO_ACCESS_KEY` | ✓ | — | MinIO access key |
| `MINIO_SECRET_KEY` | ✓ | — | MinIO secret key |
| `S3_BUCKET` | | `rag-documents` | Document storage bucket name |
| `QDRANT_URL` | | `http://localhost:6333` | Qdrant server URL |
| `QDRANT_API_KEY` | | — | Required for Qdrant Cloud; blank for self-hosted |
| `QDRANT_COLLECTION` | | `rag_chunks` | Collection name (created automatically) |
| `CELERY_BROKER_URL` | | `amqp://guest:guest@localhost:5672//` | RabbitMQ broker |
| `CELERY_RESULT_BACKEND` | | `redis://localhost:6379/1` | Celery result backend |
| `JWT_PUBLIC_KEY_PATH` | ✓ | `/secrets/jwt_public.pem` | RS256 public key |
| `JWT_PRIVATE_KEY_PATH` | ✓ | `/secrets/jwt_private.pem` | RS256 private key |
| `APP_ENV` | | `production` | `development` / `staging` / `production` |

See [.env.example](.env.example) for the full list.

---

## Data models (PostgreSQL)

| Table | Purpose |
|---|---|
| `tenants` | Plan tier, vector namespace, per-tenant LLM/RAG config |
| `users` | Email/password auth, owner/admin/member roles |
| `api_keys` | Scoped, expiring service keys (SHA-256 hashed) |
| `documents` | Upload metadata, processing status, soft delete |
| `chunks` | Chunk text + vector ID for Qdrant point lookup |
| `sessions` | Conversation sessions (live state in Redis) |
| `queries` | Full audit log with sources, latencies, token usage |
| `usage_logs` | Daily token rollup per tenant (billing) |

---

## Production checklist

- [ ] RS256 keypair generated and mounted at `/secrets/`
- [ ] All required env vars set (no `...` placeholders in `.env`)
- [ ] `APP_ENV=production` set (disables `/docs` Swagger UI)
- [ ] Qdrant collection created automatically on first startup
- [ ] MinIO bucket `rag-documents` created (handled by `minio-init` service)
- [x] Redis `maxmemory 512mb` + `allkeys-lru` configured (set in `docker-compose.yml`)
- [x] Container resource limits set for all services (CPU + memory in `docker-compose.yml`)
- [ ] Regression tests green: `pytest tests/regression/ -v -m "not slow"`
- [ ] Load test passed at 2× expected peak RPS
- [ ] Cross-tenant isolation smoke test run in staging
- [ ] WAF rules: prompt injection patterns, oversized payload limits
- [ ] PII scrubbing enabled in logging pipeline

---

## Performance targets

| Metric | Target |
|---|---|
| Query P50 latency | < 2 s |
| Query P95 latency | < 3 s |
| Query P99 latency | < 10 s |
| Ingestion time (10 MB doc) | < 60 s |
| API error rate | < 0.5% |
| Uptime | 99.9% |

---

## Per-container capacity

Each service runs as a single Docker container. These are the practical concurrency ceilings and the threshold at which a second container should be considered.

| Service | Single-container ceiling | Primary bottleneck | Scale-out trigger |
|---|---|---|---|
| **API** | ~200 concurrent requests | DB pool: 4 workers × 15 = 60 connections | CPU > 70% or DB pool > 75% utilized |
| **Worker** | 8 parallel ingest jobs | Celery concurrency (`-c 8`) | RabbitMQ `ingest` queue depth > 5 |
| **PostgreSQL** | 200 connections (`max_connections=200`) | Disk I/O on large datasets | > 160 active connections (80%) |
| **Redis** | ~512 MB cached data | Memory limit (`--maxmemory 512mb`) with LRU eviction | Memory usage > 80% |
| **Qdrant** | CPU/RAM bound (~50–100 concurrent searches) | Index size × CPU cores | CPU > 80% sustained |
| **MinIO** | Disk I/O bound; 50+ concurrent uploads fine | Disk throughput | Disk throughput saturation |

> **Note:** PostgreSQL, Redis, Qdrant, and MinIO are stateful singletons. Scaling them requires their own HA strategies (PgBouncer + Patroni, Redis Sentinel, Qdrant distributed mode, MinIO distributed mode) — not `docker compose --scale`.

### Docker Compose resource limits

All containers have explicit CPU and memory limits defined in `docker-compose.yml`:

| Service | CPU limit | Memory limit | CPU reserved | Memory reserved |
|---|---|---|---|---|
| `api` | 2.0 | 2 GB | 0.5 | 512 MB |
| `worker` | 4.0 | 8 GB | 1.0 | 2 GB |
| `db` | 1.0 | 1 GB | 0.25 | 256 MB |
| `redis` | 0.5 | 768 MB | 0.1 | 128 MB |
| `qdrant` | 2.0 | 4 GB | 0.5 | 1 GB |
| `minio` | 1.0 | 1 GB | 0.25 | 256 MB |
| `rabbitmq` | 1.0 | 1 GB | 0.25 | 256 MB |

---

## Scaling notes

| Component | Strategy |
|---|---|
| **API** | Stateless; 4 Gunicorn workers per container → horizontal scale with a load balancer (e.g. Traefik) when CPU > 70% |
| **Workers** | Scale on RabbitMQ queue depth; use KEDA in Kubernetes or `docker compose up --scale worker=N` |
| **Qdrant** | Distributed mode with sharding for > 10M vectors; Qdrant Cloud for managed |
| **PostgreSQL** | Add PgBouncer at > 3 API replicas (pool × workers × replicas would exceed `max_connections=200`); read replicas for analytics |
| **Redis** | Cluster mode for > 10k concurrent sessions |
