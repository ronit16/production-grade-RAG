# syntax=docker/dockerfile:1

# ── Stage 1: builder ─────────────────────────────────────────────────────────
FROM python:3.11-slim AS builder

WORKDIR /build

RUN apt-get update && apt-get install -y --no-install-recommends \
        build-essential \
        libpoppler-cpp-dev \
        poppler-utils \
        libmagic1 \
        tesseract-ocr \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN --mount=type=cache,target=/root/.cache/pip \
    pip install --timeout 300 --retries 5 -r requirements.txt

# ── Stage 2: runner ──────────────────────────────────────────────────────────
FROM python:3.11-slim AS runner

# Runtime system deps only — no build-essential (saves ~250 MB)
RUN apt-get update && apt-get install -y --no-install-recommends \
        libpoppler-cpp-dev \
        poppler-utils \
        libmagic1 \
        tesseract-ocr \
    && rm -rf /var/lib/apt/lists/* \
    && useradd -m -u 1001 appuser

WORKDIR /app

# Copy installed packages from builder
COPY --from=builder /usr/local/lib/python3.11/site-packages /usr/local/lib/python3.11/site-packages
COPY --from=builder /usr/local/bin /usr/local/bin

# Copy application code (tests/ and scripts/ are excluded by .dockerignore)
COPY --chown=appuser:appuser . .

USER appuser

EXPOSE 8000

# Default: API server. Override CMD in docker-compose for the Celery worker.
CMD ["gunicorn", "app.main:app", \
     "-k", "uvicorn.workers.UvicornWorker", \
     "-w", "4", \
     "--bind", "0.0.0.0:8000", \
     "--timeout", "120", \
     "--graceful-timeout", "30", \
     "--keep-alive", "5"]
