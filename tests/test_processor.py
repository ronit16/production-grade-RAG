import pytest
from unittest.mock import patch, MagicMock

# Mock out Chroma before importing the service to prevent errors if no valid API key/db is up
with patch("langchain_chroma.Chroma"):
    with patch("langchain_google_genai.GoogleGenerativeAIEmbeddings"):
        from services.document_processor import process_url

@pytest.mark.asyncio
@patch("services.document_processor.WebBaseLoader")
@patch("services.document_processor.vector_store")
async def test_process_url(mock_vector_store, mock_loader):
    # Setup mock documents
    mock_doc = MagicMock()
    mock_doc.page_content = "This is a test document content."
    mock_doc.metadata = {}
    
    mock_loader_instance = mock_loader.return_value
    mock_loader_instance.load.return_value = [mock_doc]

    import uuid
    doc_id = uuid.uuid4()
    
    await process_url("https://example.com", doc_id)
    
    # Check if vector_store.add_documents was called
    mock_vector_store.add_documents.assert_called()
    chunks = mock_vector_store.add_documents.call_args[0][0]
    
    assert len(chunks) > 0
    assert chunks[0].metadata["document_id"] == str(doc_id)
    assert chunks[0].metadata["source"] == "https://example.com"
