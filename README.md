# Production RAG System

A production-grade Retrieval-Augmented Generation (RAG) system with multi-tenant isolation, hybrid vector search, streaming responses, and a fully modular API structure.

---

## Architecture

```
Client
  │
  ▼
FastAPI  ──── CORSMiddleware
  │
  ├── Auth Middleware  (RS256 JWT  |  API key → TenantContext)
  ├── Rate Limiter     (token-bucket per tenant via Redis)
  │
  ├── POST /v1/documents   → S3 upload + Celery task dispatch
  ├── GET  /v1/documents/:id
  ├── POST /v1/sessions
  ├── GET  /v1/sessions
  ├── DEL  /v1/sessions/:id
  └── POST /v1/query  ──── SSE stream
              │
              ├── 1. Query rewrite       (gpt-4o-mini)
              ├── 2. Hybrid search       (Qdrant: dense + sparse → RRF)
              ├── 3. Cross-encoder rerank (MiniLM cross-encoder)
              └── 4. LLM generation      (LiteLLM: GPT-4o / Claude fallback)

Background
  └── Celery worker
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
| **Reranker** | `cross-encoder/ms-marco-MiniLM-L-6-v2` | ~40 % precision lift over ANN-only; runs on CPU |
| **Session store** | Redis (hot) + PostgreSQL (cold) | Sub-ms reads for active sessions; durable audit trail |
| **Task queue** | Celery + RabbitMQ | Reliable async ingestion; horizontal worker scaling |
| **Auth** | RS256 JWT + API keys | Stateless; no DB hit on every request |
| **LLM routing** | LiteLLM | Provider-agnostic; automatic fallback (GPT-4o → Claude) |
| **Streaming** | Server-Sent Events (SSE) | Works with any HTTP client |

---

## Project structure

```
production_grade_RAG/
├── app/
│   ├── main.py                        # App factory: middleware, lifespan, router mount
│   │
│   ├── api/
│   │   ├── deps.py                    # Shared dependency type aliases (DBSession, RedisClient)
│   │   └── v1/
│   │       ├── router.py              # Mounts all v1 endpoint routers
│   │       └── endpoints/
│   │           ├── health.py          # GET /health, GET /ready
│   │           ├── documents.py       # POST /v1/documents, GET /v1/documents/:id
│   │           ├── sessions.py        # POST/GET/DELETE /v1/sessions
│   │           └── query.py           # POST /v1/query  (SSE stream)
│   │
│   ├── core/
│   │   ├── config.py                  # Pydantic settings (all env vars)
│   │   ├── database.py                # Async SQLAlchemy engine + Redis pool
│   │   └── exceptions.py             # Typed HTTP exceptions
│   │
│   ├── middleware/
│   │   └── auth.py                    # JWT/API-key auth, TenantContext, rate limiting
│   │
│   ├── models/
│   │   └── db.py                      # SQLAlchemy ORM models (13 tables)
│   │
│   ├── schemas/
│   │   ├── document.py                # Upload / status response models
│   │   ├── session.py                 # Session create / list / close models
│   │   └── query.py                   # QueryRequest model
│   │
│   ├── services/
│   │   ├── retriever.py               # Hybrid retrieval: dense + sparse → RRF → rerank
│   │   ├── generator.py               # LLM streaming (LiteLLM, citations, fallback)
│   │   └── session.py                 # SessionManager: Redis ↔ PostgreSQL lifecycle
│   │
│   └── workers/
│       ├── celery_app.py              # Celery factory (broker, backend, task config)
│       └── ingestion.py               # Celery task: parse → embed → Qdrant → DB
│
├── tests/
│   ├── conftest.py                    # Shared fixtures (client, tenant context, …)
│   ├── unit/
│   │   ├── test_chunking.py           # Token estimation, chunk deduplication
│   │   ├── test_rrf.py                # Qdrant hybrid search call structure
│   │   └── test_session.py            # SessionState rolling window, token budget
│   ├── integration/
│   │   ├── test_tenant_isolation.py   # Cross-tenant data leakage checks
│   │   └── test_session_management.py # Session create / close / unknown-id
│   └── evaluation/
│       └── test_ragas.py              # RAGAS golden-set + performance benchmarks
│
├── main.py                            # Entry point (uvicorn)
├── requirements.txt
├── .env.example
└── docker-compose.yml                 # Local dev: Postgres + Redis + Qdrant + RabbitMQ
```

---

## Quick start (local)

### Prerequisites

- Python 3.11+
- Docker & Docker Compose

### 1 — Clone and install

```bash
git clone <repo>
cd production_grade_RAG
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
```

### 2 — Configure environment

```bash
cp .env.example .env
# Required: SECRET_KEY, DATABASE_URL, OPENAI_API_KEY, ANTHROPIC_API_KEY, S3_BUCKET
```

### 3 — Start infrastructure

```bash
docker compose up -d          # PostgreSQL, Redis, Qdrant, RabbitMQ
```

### 4 — Run DB migrations

```bash
alembic upgrade head
```

Qdrant collection is created automatically on first API startup (idempotent `ensure_collection()` call in the lifespan).

### 5 — Start the API

```bash
uvicorn app.main:app --reload --port 8000
# Swagger UI: http://localhost:8000/docs  (development mode only)
```

### 6 — Start the ingestion worker

```bash
celery -A app.workers.celery_app.celery_app worker \
       --loglevel=info -Q ingest -c 4
```

---

## Environment variables

| Variable | Required | Default | Description |
|---|:---:|---|---|
| `SECRET_KEY` | ✓ | — | 32+ char secret |
| `DATABASE_URL` | ✓ | — | `postgresql+asyncpg://user:pass@host/db` |
| `REDIS_URL` | | `redis://localhost:6379/0` | Session + rate-limit store |
| `OPENAI_API_KEY` | ✓ | — | Embeddings (`text-embedding-3-large`) + GPT-4o |
| `ANTHROPIC_API_KEY` | ✓ | — | Claude fallback via LiteLLM |
| `S3_BUCKET` | ✓ | — | Document storage bucket |
| `QDRANT_URL` | | `http://localhost:6333` | Qdrant server URL |
| `QDRANT_API_KEY` | | — | Required for Qdrant Cloud; blank for self-hosted |
| `QDRANT_COLLECTION` | | `rag_chunks` | Collection name (created automatically) |
| `QDRANT_DENSE_DIM` | | `1536` | Must match embedding model output dims |
| `QDRANT_SPARSE_MODEL` | | `Qdrant/bm25` | fastembed sparse model name |
| `CELERY_BROKER_URL` | | `amqp://guest:guest@localhost:5672//` | RabbitMQ |
| `JWT_PUBLIC_KEY_PATH` | ✓ | `/secrets/jwt_public.pem` | RS256 public key |
| `JWT_PRIVATE_KEY_PATH` | ✓ | `/secrets/jwt_private.pem` | RS256 private key |
| `APP_ENV` | | `production` | `development` / `staging` / `production` |

See [.env.example](.env.example) for the full list.

---

## API reference

### Upload a document
```bash
curl -X POST http://localhost:8000/v1/documents \
  -H "Authorization: Bearer <token>" \
  -F "file=@report.pdf"
# → {"document_id": "...", "status": "processing", "filename": "report.pdf"}
```

### Poll document status
```bash
curl http://localhost:8000/v1/documents/<document_id> \
  -H "Authorization: Bearer <token>"
# → {"status": "ready", "chunk_count": 42, "processing_ms": 3200, ...}
```

### Create a session
```bash
curl -X POST http://localhost:8000/v1/sessions \
  -H "Authorization: Bearer <token>"
# → {"session_id": "...", "created_at": 1715000000.0}
```

### Stream a query (SSE)
```bash
curl -N -X POST http://localhost:8000/v1/query \
  -H "Authorization: Bearer <token>" \
  -H "Content-Type: application/json" \
  -d '{"session_id": "...", "question": "What is our refund policy?"}'
```

SSE event sequence:

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
   ▼                              ▼
Qdrant Prefetch              Qdrant Prefetch
using="dense"                using="sparse"
top_k candidates             top_k candidates
   │                              │
   └──────────┬───────────────────┘
              ▼
       Fusion.RRF  (Qdrant native — single round-trip)
              │
              ▼
   Cross-encoder rerank  (MiniLM, top rerank_top_k)
              │
              ▼
     Final chunks → LLM context
```

**Tenant isolation:** every Qdrant query carries a `Filter(must=[tenant_id == ctx.tenant_id])` on both Prefetch branches, so tenants never see each other's data.

---

## Data models (PostgreSQL)

| Table | Purpose |
|---|---|
| `tenants` | Plan, vector namespace, per-tenant LLM/RAG config |
| `users` | Owner / Admin / Member roles, SSO-compatible |
| `api_keys` | Scoped, expiring keys (SHA-256 hashed) |
| `documents` | Upload metadata, processing status, soft delete |
| `chunks` | Chunk metadata + vector ID for Qdrant point lookup |
| `sessions` | Conversation sessions (live state in Redis) |
| `queries` | Full audit log with sources, latencies, RAGAS scores |
| `usage_logs` | Daily token rollup per tenant (billing) |

---

## Running tests

```bash
# Unit + integration (no external services required)
pytest tests/unit tests/integration -v

# Full suite including RAGAS evaluation (requires live API keys)
pytest tests/ -m slow -v --tb=short

# With coverage report
pytest tests/ --cov=app --cov-report=html
```

### RAGAS quality thresholds

| Metric | Minimum |
|---|---|
| `faithfulness` | 0.80 |
| `answer_relevancy` | 0.75 |
| `context_precision` | 0.70 |
| `context_recall` | 0.75 |

---

## Production checklist

- [ ] RS256 keypair generated: `openssl genrsa -out jwt_private.pem 4096 && openssl rsa -in jwt_private.pem -pubout -out jwt_public.pem`
- [ ] Qdrant collection created (happens automatically on startup via `ensure_collection()`)
- [ ] Alembic migrations applied on production DB: `alembic upgrade head`
- [ ] S3 bucket created with versioning + lifecycle policies
- [ ] Redis `maxmemory-policy allkeys-lru` set
- [ ] `APP_ENV=production` (disables `/docs` Swagger UI)
- [ ] `SENTRY_DSN` configured for error tracking
- [ ] Grafana dashboards imported
- [ ] AlertManager rules: P99 latency, error rate, Celery queue depth
- [ ] WAF rules: prompt injection patterns, oversized payload limits
- [ ] PII scrubbing enabled in logging pipeline
- [ ] Cross-tenant isolation smoke test run in staging
- [ ] Load test at 2× expected peak RPS

---

## Monitoring SLOs

| SLO | Target |
|---|---|
| Query P50 latency | < 2 s |
| Query P99 latency | < 10 s |
| Ingestion time (10 MB doc) | < 60 s |
| API error rate | < 0.5 % |
| Uptime | 99.9 % |

---

## Scaling notes

| Component | Strategy |
|---|---|
| **API** | Stateless → horizontal HPA on CPU/memory |
| **Workers** | Scale on RabbitMQ queue depth via KEDA |
| **Qdrant** | Distributed mode with sharding for > 10 M vectors; Qdrant Cloud for managed option |
| **PostgreSQL** | Read replicas for analytics; PgBouncer for connection pooling |
| **Redis** | Cluster mode for > 10 k concurrent sessions |
