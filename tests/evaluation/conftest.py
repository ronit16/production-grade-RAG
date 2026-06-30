"""Fixtures for evaluation tests: auth helpers + document ingestion for live slow tests."""
import os
import time
import uuid
from pathlib import Path

import pytest
import pytest_asyncio

FIXTURE_DOCS_DIR = Path(__file__).parent / "fixtures" / "docs"

# How long to wait for synchronous ingestion before giving up (seconds)
_INGEST_TIMEOUT = 300


@pytest_asyncio.fixture(scope="session")
async def registered_user(client):
    """Register a unique test user once per session. Returns auth payload dict."""
    suffix = uuid.uuid4().hex[:8]
    payload = {
        "username": f"testeval_{suffix}",
        "email":    f"testeval_{suffix}@example.com",
        "password": "Evaluation1234!",
    }
    resp = await client.post("/v1/auth/register", json=payload)
    assert resp.status_code == 201, resp.text
    data = resp.json()
    return {**data, "password": payload["password"], "email": payload["email"]}


@pytest.fixture(scope="session")
def auth_headers(registered_user):
    return {"Authorization": f"Bearer {registered_user['access_token']}"}


@pytest_asyncio.fixture(scope="session")
async def ingest_eval_fixtures(client, auth_headers, registered_user):
    """
    Upload and synchronously ingest all fixture documents before evaluation.

    Skips gracefully when OPENAI_API_KEY is a test placeholder — in that case
    retrieval will return empty results and RAGAS tests will also skip.

    Returns dict[filename -> document_id] for the ingested documents.

    Ingestion runs synchronously by calling process_document.apply() directly,
    bypassing the Celery broker (no worker process needed in CI).
    """
    api_key = os.environ.get("OPENAI_API_KEY", "")
    if not api_key or api_key.startswith("sk-test"):
        yield {}
        return

    if not FIXTURE_DOCS_DIR.exists() or not list(FIXTURE_DOCS_DIR.iterdir()):
        import warnings
        warnings.warn(
            f"No fixture documents found in {FIXTURE_DOCS_DIR}. "
            "Run: python tests/evaluation/download_fixtures.py"
        )
        yield {}
        return

    from app.core.config import get_settings
    from app.workers.ingestion import process_document

    settings = get_settings()
    tenant_id = registered_user["tenant_id"]
    doc_ids: dict[str, str] = {}  # filename → document_id

    for doc_path in sorted(FIXTURE_DOCS_DIR.iterdir()):
        if not doc_path.is_file():
            continue

        content = doc_path.read_bytes()
        # Infer content type from extension
        suffix = doc_path.suffix.lower()
        content_type_map = {
            ".txt":  "text/plain",
            ".md":   "text/markdown",
            ".pdf":  "application/pdf",
            ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            ".html": "text/html",
        }
        content_type = content_type_map.get(suffix, "application/octet-stream")

        # Upload via HTTP to create the S3 object + DB record
        resp = await client.post(
            "/v1/documents",
            files={"file": (doc_path.name, content, content_type)},
            headers=auth_headers,
        )
        if resp.status_code != 202:
            continue  # skip this file and continue — don't abort all ingestion

        doc_id = resp.json()["document_id"]
        s3_key = f"{settings.S3_PREFIX}/{tenant_id}/{doc_id}/{doc_path.name}"

        # Run ingestion synchronously — bypasses Celery broker.
        # .apply() provides a fake task context for bind=True tasks.
        process_document.apply(kwargs={
            "document_id":     doc_id,
            "tenant_id":       tenant_id,
            "s3_key":          s3_key,
            "content_type":    content_type,
            "embedding_model": settings.EMBEDDING_MODEL.value,
            "user_id":         None,
        })

        doc_ids[doc_path.name] = doc_id

    yield doc_ids
