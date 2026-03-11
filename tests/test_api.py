import pytest
from httpx import AsyncClient, ASGITransport
import uuid
from unittest.mock import patch

from main import app
from models.schemas import DocumentResponse

@pytest.fixture
async def async_client():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client

@pytest.mark.asyncio
async def test_root(async_client):
    response = await async_client.get("/")
    assert response.status_code == 200
    assert response.json() == {"message": "Welcome to the Production Grade RAG System API"}

@pytest.mark.asyncio
@patch("api.routes.documents.get_db")
async def test_upload_url(mock_get_db, async_client):
    # Mocking DB and background tasks to avoid real execution during unit tests
    with patch("api.routes.documents.background_process_url") as mock_bg:
        response = await async_client.post(
            "/documents/upload",
            data={"url": "https://example.com"}
        )
        assert response.status_code == 200
        data = response.json()
        assert "id" in data
        assert data["filename"] == "https://example.com"
        assert data["source_type"] == "url"
        assert data["status"] == "uploaded" or data["status"] == "processing"

@pytest.mark.asyncio
async def test_upload_missing_file_and_url(async_client):
    response = await async_client.post("/documents/upload")
    # Pydantic/FastAPI will return 422 if form data is completely missing or 400 based on our custom logic
    assert response.status_code in [400, 422]
