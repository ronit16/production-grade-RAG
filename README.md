# Production RAG System

![Python](https://img.shields.io/badge/Python-3.11-blue?logo=python)
![FastAPI](https://img.shields.io/badge/FastAPI-0.110-green?logo=fastapi)
![Docker](https://img.shields.io/badge/Docker-Compose-2496ED?logo=docker)
![License](https://img.shields.io/badge/License-MIT-yellow)

A production-grade Retrieval-Augmented Generation (RAG) API built to handle real-world multi-tenant SaaS requirements. It combines hybrid vector search (dense + sparse with native RRF fusion), streaming LLM responses via Server-Sent Events — all containerized with Docker Compose and tested end-to-end with Testcontainers.

The system solves the core challenge of deploying RAG in a shared-infrastructure environment: strict per-tenant data isolation at every layer (auth, vector search, object storage, Redis, and database) with zero cross-tenant leakage, validated by a comprehensive test suite including multi-tenant regression tests, RAGAS quality evaluation, and load testing.

---

## Table of Contents

- [Features](#features)
- [Prerequisites \& Installation](#prerequisites--installation)
- [Usage](#usage)
  - [Authentication](#authentication)
  - [Upload a Document](#upload-a-document)
  - [Create a Session and Query](#create-a-session-and-query)
- [Architecture](#architecture)
  - [Request Lifecycle](#request-lifecycle)
  - [Ingestion Pipeline](#ingestion-pipeline)
  - [Hybrid Retrieval Pipeline](#hybrid-retrieval-pipeline)
  - [Evaluation Pipeline](#evaluation-pipeline)
  - [Key Design Decisions](#key-design-decisions)
- [Project Structure](#project-structure)
- [Running Tests](#running-tests)
  - [Regression Tests](#regression-tests-testcontainers)
  - [Integration Tests](#integration-tests-multi-tenant--multi-user)
  - [Unit Tests](#unit-tests)
  - [Evaluation Tests](#evaluation-tests-ragas)
  - [Load Tests](#load-tests-locust)
- [Environment Variables](#environment-variables)
- [Data Models](#data-models-postgresql)
- [API Reference](#api-reference)
- [Performance Targets](#performance-targets)
- [Scaling Notes](#scaling-notes)
- [Contributing](#contributing)
- [License](#license)

---

## Features

- **Hybrid vector search** — dense (OpenAI `text-embedding-3-large`) + sparse (fastembed BM25) with Qdrant native Reciprocal Rank Fusion in a single round-trip
- **Cross-encoder reranking** — `ms-marco-MiniLM-L-6-v2` via fastembed ONNX (~40% precision lift, no PyTorch or CUDA required)
- **Streaming SSE responses** — token-by-token generation via LiteLLM (GPT-4o primary, Gemini fallback), works with any HTTP client
- **Multi-tenant isolation** — JWT-authenticated tenants are isolated at auth, Qdrant, PostgreSQL, MinIO (S3), and Redis layers simultaneously
- **Multi-user sessions** — per-user session history with rolling 20-message context window, Redis hot-path, PostgreSQL audit trail
- **Async ingestion pipeline** — Celery + RabbitMQ worker parses PDFs/DOCX/Markdown with Unstructured, embeds in batches, upserts to Qdrant
- **RAGAS quality evaluation** — 8-metric automated quality gate (faithfulness, relevancy, context precision/recall, answer quality, hallucination rate, retrieval ratio, context-awareness) against golden Q&A datasets
- **Production-grade testing** — Testcontainers regression suite, HTTP-layer multi-tenant isolation tests, unit tests, RAGAS evaluation, and Locust load tests (50-user ramp)
- **Plan-tier rate limiting** — per-tenant token-bucket rate limiter in Redis (FREE/STARTER/PROFESSIONAL/ENTERPRISE tiers)

---

## Prerequisites & Installation

### Prerequisites

- Docker Engine 24+ and Docker Compose v2
- `openssl` (available on macOS, Linux, and WSL2)
- An **OpenAI API key** — for embeddings (`text-embedding-3-large`) and GPT-4o generation
- A **Gemini API key** — for LLM fallback and RAGAS evaluation (`gemini-2.0-flash`)

### 1 — Clone and configure

```bash
git clone <repo-url>
cd production-grade-RAG
cp .env.example .env
# Open .env and set at minimum:
#   SECRET_KEY=<32+ random chars>
#   OPENAI_API_KEY=sk-...
#   GEMINI_API_KEY=AI-...
#   MINIO_ACCESS_KEY=minioadmin
#   MINIO_SECRET_KEY=minioadmin
```

### 2 — Generate RS256 JWT keys

```bash
mkdir -p secrets
openssl genrsa -out secrets/jwt_private.pem 4096
openssl rsa -in secrets/jwt_private.pem -pubout -out secrets/jwt_public.pem
```

These keys are mounted read-only into the container at `/secrets/` and never leave your machine.

### 3 — Start the stack

```bash
docker compose up --build -d
```

> **Development mode:** set `APP_ENV=development` in your `.env` to enable Swagger UI at `/docs`.  
> A `docker-compose.dev.yml` with hot-reload and lighter resource limits is not tracked in the repo — create your own local override if needed.

All 8 services start with health checks. Watch progress with:

```bash
docker compose ps
# Wait until all services show (healthy)
```

The API is ready at **http://localhost:8000**.

> **Swagger UI** (development mode only): http://localhost:8000/docs  
> Set `APP_ENV=development` in `.env` to enable it.

### 4 — Verify the stack

```bash
curl http://localhost:8000/v1/health
# → {"status": "ok", "version": "1.0.0"}

curl http://localhost:8000/v1/health/detailed
# → {"status": "healthy", "checks": {"postgres": {...}, "redis": {...}, ...}}
```

### Port Reference

| Service | URL | Notes |
|---|---|---|
| FastAPI | http://localhost:8000 | Main API |
| Swagger UI | http://localhost:8000/docs | Dev mode only (`docker-compose.dev.yml`) |
| PostgreSQL | localhost:5433 | Host port (container: 5432) |
| Redis | localhost:6381 | Host port (container: 6379) |
| RabbitMQ management | http://localhost:15672 | guest / guest |
| Qdrant | http://localhost:6333 | REST; 6334 = gRPC |
| MinIO console | http://localhost:9003 | minioadmin / minioadmin |

---

## Usage

### Authentication

Every API call (except `/v1/auth/*` and `/v1/health*`) requires a `Bearer` token in the `Authorization` header. Each registration creates a new isolated tenant.

```bash
# Register a new account (creates a tenant automatically)
curl -X POST http://localhost:8000/v1/auth/register \
  -H "Content-Type: application/json" \
  -d '{"username": "alice", "email": "alice@example.com", "password": "Secret1234!"}'
# → {"access_token": "eyJ...", "token_type": "bearer", "user_id": "...", "tenant_id": "..."}

# Log in and get a fresh token
curl -X POST http://localhost:8000/v1/auth/login \
  -H "Content-Type: application/json" \
  -d '{"email": "alice@example.com", "password": "Secret1234!"}'
```

Tokens expire after 15 minutes (`ACCESS_TOKEN_EXPIRE_MINUTES`). Store the `access_token` and pass it as `Authorization: Bearer <token>` on subsequent requests.

### Upload a Document

```bash
curl -X POST http://localhost:8000/v1/documents \
  -H "Authorization: Bearer <token>" \
  -F "file=@report.pdf"
# → {"document_id": "3f2a...", "status": "processing", "filename": "report.pdf"}
```

**Supported formats:** `application/pdf`, `text/plain`, `text/markdown`, `text/html`, `.docx`  
**Max file size:** 100 MB

Poll for completion (processing typically takes 2–5 minutes):

```bash
curl http://localhost:8000/v1/documents/<document_id> \
  -H "Authorization: Bearer <token>"
# → {"status": "ready", "chunk_count": 42, "processing_ms": 3200, ...}
```

### Create a Session and Query

```bash
# Create a conversation session
curl -X POST http://localhost:8000/v1/sessions \
  -H "Authorization: Bearer <token>"
# → {"session_id": "7c1d...", "created_at": 1715000000.0}

# Stream a RAG query (Server-Sent Events)
curl -N -X POST http://localhost:8000/v1/query \
  -H "Authorization: Bearer <token>" \
  -H "Content-Type: application/json" \
  -d '{"session_id": "7c1d...", "question": "What is our refund policy?"}'
```

**SSE event sequence:**

| Event | Payload | Description |
|---|---|---|
| `status` | `{"status": "retrieving"}` | Retrieval phase started |
| `retrieval` | `{"chunk_count": 5, "rewritten_query": "..."}` | Retrieval complete |
| `status` | `{"status": "generating"}` | LLM generation started |
| `delta` | `{"text": "token..."}` | Streamed token (repeats) |
| `done` | `{"sources": [...], "query_id": "..."}` | Generation complete |
| `error` | `{"error": "..."}` | On failure |

The query endpoint maintains **conversation history** across multiple turns in the same session (rolling 20-message window, 2,000-token budget).

---

## Architecture

### Request Lifecycle

```
HTTP Client / Browser
       │
       ▼
FastAPI  ──── CORSMiddleware
  │
  ├── Auth Middleware  (RS256 JWT | API key → TenantContext)
  ├── Rate Limiter     (token-bucket per tenant in Redis)
  │
  ├── POST /v1/auth/register    — creates User + Tenant
  ├── POST /v1/auth/login       — issues 15-min JWT
  │
  ├── POST /v1/documents        → MinIO upload + Celery task dispatch
  ├── GET  /v1/documents/:id    → processing status poll
  │
  ├── POST /v1/sessions         → create conversation session
  ├── GET  /v1/sessions         → list user's sessions (paginated)
  ├── DEL  /v1/sessions/:id     → close + archive session
  │
  ├── POST /v1/query  ──── SSE stream
  │           │
  │           ├── 1. Query rewrite  (gpt-4o-mini — makes follow-ups self-contained)
  │           ├── 2. Hybrid search  (Qdrant: dense + sparse → native RRF)
  │           ├── 3. Rerank         (fastembed ONNX MiniLM cross-encoder)
  │           └── 4. LLM generation (LiteLLM: GPT-4o → Gemini fallback)
  │
  ├── GET /v1/health
  ├── GET /v1/ready
  └── GET /v1/health/detailed   → probes all 5 backing services

Background
  └── Celery worker  (RabbitMQ broker, 8 concurrent processes)
        └── parse (Unstructured) → chunk → embed dense (OpenAI)
                                          + embed sparse (fastembed BM25)
                                          → upsert to Qdrant (batch=100)
                                          → persist metadata to PostgreSQL
```

The `TenantContext` object (built in `middleware/auth.py`) carries `tenant_id`, `user_id`, `role`, per-plan limits (`max_docs`, `tokens_day`, `rps`), and `rag_config` overrides. It is the single gating object — every service call receives it and enforces isolation through it.

### Ingestion Pipeline

```
POST /v1/documents
  → validate file type + size → upload to MinIO (s3://{S3_PREFIX}/{tenant_id}/{doc_id}/{filename})
  → create Document row (status=PENDING)
  → dispatch Celery task to "ingest" queue

Celery worker (workers/ingestion.py):
  1. Download from MinIO → parse with Unstructured → split into chunks
  2. Embed dense:  OpenAI text-embedding-3-large (batch=256)
  3. Embed sparse: fastembed BM25 (onnxruntime — no PyTorch)
  4. Upsert to Qdrant (batch=100 points), payload includes tenant_id + doc_id
  5. Insert Chunk rows into PostgreSQL
  6. Update Document.status = READY (or FAILED on error, up to 3 retries)
```

### Hybrid Retrieval Pipeline

```
Question
   │
   ▼
Query rewrite  (gpt-4o-mini — makes follow-ups self-contained)
   │
   ├────────────────────────────┐
   ▼                            ▼
Dense embedding            Sparse embedding
(OpenAI text-embedding-3-large)  (fastembed BM25)
   │                            │
   └──────────┬─────────────────┘
              ▼
       Fusion.RRF  (Qdrant native — single round-trip, no extra infrastructure)
              │
              ▼
   Cross-encoder rerank  (fastembed ONNX MiniLM, top rerank_top_k results)
              │
              ▼
     Final chunks → LLM context → streaming SSE response
```

**Tenant isolation:** every Qdrant query carries a payload filter `tenant_id == ctx.tenant_id` on both Prefetch branches. Tenants never see each other's vectors.

### Evaluation Pipeline

```
EvaluationPipeline(ctx).run_dataset(samples)
  Phase 1: for each EvalSample → retrieve() + generate_sync() → answer, RetrievalResult, usage
  Phase 2: single RAGAS evaluate() call for full batch
           (faithfulness, answer_relevancy, context_precision, context_recall, answer_correctness)
           — run in thread executor so it doesn't block the event loop
  Phase 3: derive
           hallucination_rate  = 1 − faithfulness_score
           retrieval_ratio     = reranked_count / candidate_count
           context_awareness   = gpt-4o-mini LLM judge (multi-turn) | 1.0 (single-turn)
  → list[EvalResult]  +  EvaluationPipeline.aggregate(results) → dict[metric, float]
```

Two golden datasets are supported:
- **`GOLDEN_SAMPLES`** — 5 Acme Corp policy Q&A samples (single-tenant baseline)
- **`GOLDEN_SAMPLES_RFC`** — 3 RFC 7231 HTTP semantics samples, including a multi-turn follow-up (multi-tenant corpus divergence testing)

### Key Design Decisions

| Concern | Choice | Rationale |
|---|---|---|
| **Vector DB** | Qdrant (single collection, payload-filtered per tenant) | Supports dense + sparse natively; built-in RRF fusion; self-hostable or cloud |
| **Dense search** | OpenAI `text-embedding-3-large` (1536-dim) | State-of-the-art retrieval accuracy |
| **Sparse search** | BM25 via `fastembed` (`Qdrant/bm25`) | Exact-match, acronyms, rare terms — no separate search cluster needed |
| **Hybrid fusion** | Qdrant native `Prefetch + Fusion.RRF` | Zero extra infrastructure; equal-weight RRF in a single query call |
| **Reranker** | `cross-encoder/ms-marco-MiniLM-L-6-v2` via fastembed ONNX | ~40% precision lift; no PyTorch/CUDA — saves ~1.3 GB from image size |
| **Session store** | Redis (hot) + PostgreSQL (cold) | Sub-ms reads for active sessions; durable audit trail |
| **Task queue** | Celery + RabbitMQ | Reliable async ingestion; horizontal worker scaling |
| **Auth** | RS256 JWT + API keys | Stateless; no DB hit on every request; short expiry (15 min) |
| **LLM routing** | LiteLLM | Provider-agnostic; automatic fallback (GPT-4o → Gemini) |
| **Streaming** | Server-Sent Events (SSE) | Works with any HTTP client; no WebSocket upgrade handshake |
| **Testing** | Testcontainers | Regression tests spin up real containers — no mocks, no manual setup |
| **Evaluation** | RAGAS + LLM judge | Automated quality gate with 8 metrics; runs in CI against golden datasets |
| **Process model** | Gunicorn + Uvicorn workers (not fork) | `onnxruntime` (fastembed) is not fork-safe; Gunicorn exec-based workers avoid the issue |

---

## Project Structure

```
production-grade-RAG/
├── app/
│   ├── main.py                          # App factory: middleware, lifespan, routers
│   ├── api/
│   │   ├── deps.py                      # Shared dependency aliases (DBSession, RedisClient)
│   │   └── v1/
│   │       ├── router.py
│   │       └── endpoints/
│   │           ├── health.py            # GET /health, /ready, /health/detailed
│   │           ├── auth.py              # POST /auth/register, /auth/login
│   │           ├── documents.py         # POST/GET /v1/documents
│   │           ├── sessions.py          # POST/GET/DELETE /v1/sessions
│   │           └── query.py             # POST /v1/query (SSE stream)
│   ├── core/
│   │   ├── config.py                    # Pydantic settings (all env vars)
│   │   ├── database.py                  # Async SQLAlchemy engine + Redis pool + init_db
│   │   └── exceptions.py
│   ├── middleware/
│   │   └── auth.py                      # JWT/API-key auth, TenantContext, rate limiting
│   ├── models/
│   │   └── db.py                        # SQLAlchemy ORM models (8 tables)
│   ├── schemas/
│   │   ├── document.py
│   │   ├── session.py
│   │   └── query.py
│   ├── services/
│   │   ├── retriever.py                 # Hybrid retrieval: dense+sparse → RRF → rerank
│   │   ├── generator.py                 # LLM streaming (LiteLLM, citations, fallback)
│   │   ├── session.py                   # SessionManager: Redis ↔ PostgreSQL lifecycle
│   │   └── evaluator.py                 # RAGAS evaluation pipeline (8 metrics)
│   └── workers/
│       ├── celery_app.py
│       └── ingestion.py                 # Celery task: parse → embed → Qdrant → DB
├── tests/
│   ├── conftest.py                      # Testcontainers startup (pytest_configure hook)
│   ├── regression/                      # HTTP-layer tests against real containers
│   │   ├── conftest.py                  # Auth fixtures: registered_user, tenant_b_user,
│   │   │                                #   second_user_same_tenant, member fixtures
│   │   ├── fixtures/
│   │   │   ├── sample.txt               # Synthetic Acme Corp policy document
│   │   │   └── tech_specs.txt           # RFC 7231 HTTP semantics document
│   │   ├── test_health.py               # Health & readiness probe tests
│   │   ├── test_auth.py                 # Register / login flows
│   │   ├── test_documents.py            # Upload + status polling
│   │   ├── test_sessions.py             # Session CRUD
│   │   ├── test_query.py                # SSE streaming with respx mocks
│   │   ├── test_multitenancy.py         # Cross-tenant isolation (7 tests)
│   │   ├── test_multiuser.py            # Multi-user within same tenant (9 tests)
│   │   └── test_multisession.py         # Multi-session per user (10 tests)
│   ├── unit/                            # No containers required
│   │   ├── test_chunking.py
│   │   ├── test_rrf.py
│   │   └── test_session.py
│   ├── integration/                     # Service-layer integration tests (mocked clients)
│   │   ├── test_tenant_isolation.py     # Qdrant filter + Redis key scoping
│   │   └── test_session_management.py   # Session lifecycle with mocked Redis/DB
│   ├── evaluation/
│   │   ├── conftest.py                  # Auth fixtures for evaluation tests
│   │   ├── golden_dataset.py            # GOLDEN_SAMPLES (5 Acme) + GOLDEN_SAMPLES_RFC (3 RFC)
│   │   ├── test_ragas.py                # 7 RAGAS test classes (unit + live)
│   │   └── test_multitenant_eval.py     # Multi-tenant evaluation (6 tests)
│   └── load/
│       └── locustfile.py                # 50-user step ramp-up load test
├── scripts/
│   └── generate_dev_token.py            # Mint a dev JWT for manual API testing
├── deploy/k8s/
│   └── deployment.yaml                  # Kubernetes manifests (API, worker, HPA, Ingress)
├── secrets/                             # RS256 JWT keypair — git-ignored, never committed
├── Dockerfile                           # Python 3.11 slim + Gunicorn/Uvicorn
├── docker-compose.yml                   # Production: 8-service stack with resource limits
├── docker-compose.dev.yml               # Dev: hot-reload, Swagger UI — git-ignored
├── requirements.txt
├── pytest.ini
├── main.py                              # Gunicorn entry point
└── .env.example                         # Environment variable template
```

### Tenant isolation — where it is enforced

| Layer | File | Mechanism |
|---|---|---|
| Auth | `middleware/auth.py` | JWT claim `tenant_id` decoded into TenantContext |
| Vector search | `services/retriever.py` | Every Qdrant Prefetch carries `FieldCondition(tenant_id==...)` |
| DB queries | All endpoint handlers | `WHERE tenant_id = :tid` on every query |
| Object storage | `workers/ingestion.py` | S3 key prefix `{S3_PREFIX}/{tenant_id}/...` |
| Redis sessions | `services/session.py` | Key `rag:session:{tenant_id}:{session_id}` |
| Rate limiting | `middleware/auth.py` | Per-tenant token bucket in Redis |

---

## Running Tests

All tests live under `tests/`. Run from the repo root.

### Regression Tests (Testcontainers)

Containers start automatically — no running stack required. The `pytest_configure` hook in `tests/conftest.py` spins up real PostgreSQL, Redis, Qdrant, MinIO, and RabbitMQ containers before any test module is imported.

```bash
# Full regression suite (default: excludes slow and integration markers)
pytest tests/regression/ -v

# All non-slow tests across all suites
pytest -v

# Single file
pytest tests/regression/test_auth.py -v

# Single test
pytest tests/regression/test_auth.py::TestRegister::test_register_returns_201 -v

# With coverage report
pytest tests/regression/ --cov=app --cov-report=html -v
```

### Integration Tests (Multi-Tenant & Multi-User)

HTTP-layer tests that verify cross-tenant data isolation and multi-user session boundaries. Use real PostgreSQL + Redis containers (started by Testcontainers). No LLM API keys required.

```bash
# Run all integration-marked tests
pytest -m integration -v

# Cross-tenant isolation only
pytest tests/regression/test_multitenancy.py -v

# Multi-user (same tenant) tests
pytest tests/regression/test_multiuser.py -v

# Multi-session per user
pytest tests/regression/test_multisession.py -v
```

**What `@pytest.mark.integration` tests cover:**

| Test file | Tests | What is verified |
|---|---|---|
| `test_multitenancy.py` | 7 | Tenant A/B cannot see each other's docs, sessions, or query results |
| `test_multiuser.py` | 9 | Session lists are user-scoped; docs are tenant-scoped; role claims correct |
| `test_multisession.py` | 10 | Unique IDs, pagination, concurrent creates, history isolation, rolling window |

### Unit Tests

No Docker containers needed. Uses `--no-containers` flag (defined in `pytest.ini` if containers are not available).

```bash
pytest tests/unit/ -v --no-containers
```

### Evaluation Tests (RAGAS)

```bash
# Fast — mock tests, no containers or API keys required
pytest tests/evaluation/ --no-containers -v

# Full live evaluation — requires a real GEMINI_API_KEY and running stack
export GEMINI_API_KEY=AI-...your-real-key...
pytest tests/evaluation/ -m slow -v

# Multi-tenant corpus divergence (Acme vs RFC corpora)
GEMINI_API_KEY=<key> pytest tests/evaluation/test_multitenant_eval.py -m slow -v
```

The live test auto-skips if `GEMINI_API_KEY` is absent or equals `test-fake-gemini-key`.

**RAGAS quality thresholds:**

| Metric | Threshold | Method |
|---|---|---|
| `faithfulness_score` | ≥ 0.80 | RAGAS `faithfulness` |
| `context_precision` | ≥ 0.70 | RAGAS `context_precision` |
| `context_recall` | ≥ 0.75 | RAGAS `context_recall` |
| `relevancy_score` | ≥ 0.75 | RAGAS `answer_relevancy` |
| `answer_quality` | ≥ 0.65 | RAGAS `answer_correctness` |
| `hallucination_rate` | ≤ 0.20 | `1 − faithfulness_score` |
| `retrieval_ratio` | ≥ 0.10 | `reranked_count / candidate_count` |
| `context_awareness` | ≥ 0.70 | gpt-4o-mini LLM judge (multi-turn only) |

### Load Tests (Locust)

Requires the application stack to be running (`docker compose up -d`).

```bash
# Interactive web UI → http://localhost:8089
locust -f tests/load/locustfile.py --host http://localhost:8000

# Headless — ramp to 50 users, 5-minute run, HTML report
locust -f tests/load/locustfile.py \
  --headless --host http://localhost:8000 \
  --users 50 --spawn-rate 5 --run-time 5m \
  --html tests/load/report.html
```

Load shape: warm-up (10 users) → ramp (25) → peak (50) → hold.

**Target SLOs under 50 concurrent users:**

| Endpoint | P95 target |
|---|---|
| GET /v1/health | < 50 ms |
| POST /v1/sessions | < 500 ms |
| POST /v1/query | < 30 s (LLM-bound) |
| Overall error rate | < 1% |

---

## Environment Variables

| Variable | Required | Default | Description |
|---|:---:|---|---|
| `SECRET_KEY` | ✓ | — | 32+ char secret for miscellaneous signing |
| `APP_ENV` | | `production` | `development` enables `/docs` Swagger UI |
| `DATABASE_URL` | ✓ | — | `postgresql+asyncpg://user:pass@host/db` |
| `REDIS_URL` | | `redis://localhost:6379/0` | Session + rate-limit store |
| `OPENAI_API_KEY` | ✓ | — | Embeddings (`text-embedding-3-large`) + GPT-4o |
| `GEMINI_API_KEY` | ✓ | — | Gemini fallback LLM + RAGAS evaluation (`gemini-2.0-flash`) |
| `MINIO_ENDPOINT` | | `http://localhost:9000` | MinIO (S3-compatible) endpoint |
| `MINIO_ACCESS_KEY` | ✓ | — | MinIO access key |
| `MINIO_SECRET_KEY` | ✓ | — | MinIO secret key |
| `S3_BUCKET` | | `rag-documents` | Document storage bucket name |
| `QDRANT_URL` | | `http://localhost:6333` | Qdrant server URL |
| `QDRANT_API_KEY` | | — | Required for Qdrant Cloud; blank for self-hosted |
| `QDRANT_COLLECTION` | | `rag_chunks` | Collection name (created automatically on startup) |
| `CELERY_BROKER_URL` | | `amqp://guest:guest@localhost:5672//` | RabbitMQ broker |
| `CELERY_RESULT_BACKEND` | | `redis://localhost:6379/1` | Celery result backend |
| `JWT_PUBLIC_KEY_PATH` | ✓ | `/secrets/jwt_public.pem` | RS256 public key path |
| `JWT_PRIVATE_KEY_PATH` | ✓ | `/secrets/jwt_private.pem` | RS256 private key path |
| `RETRIEVAL_TOP_K` | | `20` | Qdrant candidates before rerank |
| `RERANK_TOP_K` | | `5` | Chunks passed to LLM after reranking |
| `CHUNK_SIZE` | | `512` | Token chunk size for ingestion |
| `CHUNK_OVERLAP` | | `50` | Token overlap between adjacent chunks |
| `INGEST_CONCURRENCY` | | `8` | Must match Celery `-c` flag |

See `.env.example` for the complete list with descriptions.

---

## Data Models (PostgreSQL)

| Table | Purpose |
|---|---|
| `tenants` | Plan tier, vector namespace, per-tenant LLM/RAG config overrides |
| `users` | Email/password auth, owner/admin/member roles; nullable `hashed_password` (SSO path) |
| `api_keys` | Scoped, expiring service keys (SHA-256 hashed, `sk_` prefix) |
| `documents` | Upload metadata, processing status, soft delete |
| `chunks` | Chunk text + Qdrant point ID for lookup |
| `sessions` | Conversation sessions (live state in Redis; closed state in DB) |
| `queries` | Full audit log: question, answer, sources, latencies, token usage, RAGAS scores |
| `usage_logs` | Daily token rollup per tenant (billing data) |

**Plan tiers and limits:**

| Tier | Max docs | Tokens/day | RPS | Max sessions |
|---|---|---|---|---|
| FREE | 100 | 50,000 | 2 | 10 |
| STARTER | 2,000 | 500,000 | 10 | 100 |
| PROFESSIONAL | 20,000 | 5,000,000 | 50 | 500 |
| ENTERPRISE | Unlimited | Unlimited | 200 | Unlimited |

---

## API Reference

Full OpenAPI documentation is available at `http://localhost:8000/docs` when `APP_ENV=development`.

### Authentication endpoints

```
POST /v1/auth/register   — create user + tenant, returns JWT
POST /v1/auth/login      — authenticate, returns JWT
```

### Document endpoints

```
POST /v1/documents        — upload file for async processing (returns 202)
GET  /v1/documents/:id    — poll processing status
```

### Session endpoints

```
POST   /v1/sessions            — create session (returns 201)
GET    /v1/sessions            — list user's sessions (limit, offset)
DELETE /v1/sessions/:id        — close and archive session
```

### Query endpoint

```
POST /v1/query    — stream RAG response via SSE
```

### Health endpoints

```
GET /v1/health           — {"status": "ok", "version": "..."}
GET /v1/ready            — checks DB + Redis connectivity
GET /v1/health/detailed  — per-service status + latency for all 5 backing services
```

---

## Performance Targets

| Metric | Target |
|---|---|
| Query P50 latency | < 2 s |
| Query P95 latency | < 3 s |
| Query P99 latency | < 10 s |
| Ingestion (10 MB doc) | < 60 s |
| API error rate | < 0.5% |
| Uptime | 99.9% |

---

## Scaling Notes

| Component | Strategy |
|---|---|
| **API** | Stateless — 4 Gunicorn workers per container → horizontal scale with a load balancer (e.g. Traefik) when CPU > 70% |
| **Workers** | Scale on RabbitMQ queue depth; `docker compose up --scale worker=N` or KEDA in Kubernetes |
| **Qdrant** | Distributed mode with sharding for > 10 M vectors; Qdrant Cloud for managed |
| **PostgreSQL** | Add PgBouncer at > 3 API replicas; read replicas for analytics queries |
| **Redis** | Cluster mode for > 10 k concurrent sessions |

**Per-container capacity:**

| Service | Single-container ceiling | Primary bottleneck | Scale-out trigger |
|---|---|---|---|
| API | ~200 concurrent requests | DB pool (4 workers × 15 connections) | CPU > 70% or DB pool > 75% |
| Worker | 8 parallel ingest jobs | Celery concurrency (`-c 8`) | Queue depth > 5 |
| PostgreSQL | 200 connections | Disk I/O | > 160 active connections |
| Redis | ~512 MB cached data | Memory limit (LRU eviction) | Memory > 80% |
| Qdrant | ~50–100 concurrent searches | Index size × CPU cores | CPU > 80% sustained |

**Docker Compose resource limits:**

| Service | CPU limit | Memory limit |
|---|---|---|
| `api` | 2.0 | 2 GB |
| `worker` | 4.0 | 8 GB |
| `db` | 1.0 | 1 GB |
| `redis` | 0.5 | 768 MB |
| `qdrant` | 2.0 | 4 GB |
| `minio` | 1.0 | 1 GB |
| `rabbitmq` | 1.0 | 1 GB |

> PostgreSQL, Redis, Qdrant, and MinIO are stateful singletons. Scaling them requires their own HA strategies (PgBouncer + Patroni, Redis Sentinel, Qdrant distributed mode, MinIO distributed mode) — not `docker compose --scale`.

---

## Production Checklist

- [ ] RS256 keypair generated and mounted at `/secrets/`
- [ ] All required env vars set (no placeholder values in `.env`)
- [ ] `APP_ENV=production` (disables `/docs` Swagger UI)
- [ ] Qdrant collection created automatically on first startup
- [ ] MinIO bucket `rag-documents` created (handled by `minio-init` service)
- [x] Redis `maxmemory 512mb` + `allkeys-lru` configured (set in `docker-compose.yml`)
- [x] Container resource limits set for all services
- [ ] Regression tests green: `pytest tests/regression/ -v`
- [ ] Integration isolation tests green: `pytest -m integration -v`
- [ ] Load test passed at 2× expected peak RPS
- [ ] RAGAS evaluation meets all 8 metric thresholds
- [ ] WAF rules: prompt injection patterns, oversized payload limits
- [ ] PII scrubbing enabled in logging pipeline

---

## Contributing

Contributions are welcome. Please follow these guidelines:

1. **Fork and branch** — create a feature branch from `main` (`git checkout -b feature/your-feature`).

2. **Run the test suite before submitting:**
   ```bash
   pytest tests/regression/ tests/unit/ tests/integration/ -v
   pytest -m integration -v
   ```
   All tests must pass. Do not add `--no-verify` or skip the test run.

3. **Adding a new endpoint:**
   - Create the handler in `app/api/v1/endpoints/`
   - Declare dependencies: `ctx: TenantContext = Depends(get_tenant_ctx)`, `db: AsyncSession = Depends(get_db)`, `redis: Redis = Depends(get_redis)`
   - Register in `app/api/v1/router.py`
   - Add a regression test in `tests/regression/`
   - Every query against PostgreSQL must include `WHERE tenant_id = :tid`

4. **Adding new tests:**
   - Regression tests use the shared `client` + `registered_user` fixtures from `tests/regression/conftest.py`
   - Use `@pytest.mark.slow` for tests that require real LLM API keys or a running Celery worker
   - Use `@pytest.mark.integration` for tests that span multiple tenants or users
   - Do not add `autouse=True` fixtures to `tests/conftest.py` (session-level) without discussion

5. **Code style:** no inline comments unless the *why* is non-obvious; no docstrings on internal functions; snake_case throughout.

6. **Pull request:** include a brief description of what changed and paste the test output showing all new tests passing.

---

## License

This project is licensed under the [MIT License](LICENSE).

```
MIT License

Copyright (c) 2024 Ronit Shah

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
```
