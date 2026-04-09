import pytest
from unittest.mock import patch, MagicMock

# Mock out Chroma before importing the service to prevent errors if no valid API key/db is up
with patch("langchain_chroma.Chroma"):
    with patch("langchain_google_genai.GoogleGenerativeAIEmbeddings"):
        from app.services.document_processor import process_url


# Parametrize for all supported file types
import tempfile
import os

@pytest.mark.asyncio
@pytest.mark.parametrize("ext,loader_patch", [
    ("pdf", "PyPDFLoader"),
    ("md", "UnstructuredMarkdownLoader"),
    ("docx", "Docx2txtLoader"),
    ("txt", "TextLoader"),
    ("html", "UnstructuredHTMLLoader"),
])
@patch("services.document_processor.vector_store")
def test_process_document_supported_types(mock_vector_store, ext, loader_patch):
    # Patch the correct loader
    with patch(f"services.document_processor.{loader_patch}") as mock_loader:
        mock_doc = MagicMock()
        mock_doc.page_content = f"This is a test {ext} document."
        mock_doc.metadata = {}
        mock_loader_instance = mock_loader.return_value
        mock_loader_instance.load.return_value = [mock_doc]

        # Create a temp file
        with tempfile.NamedTemporaryFile(suffix=f".{ext}", delete=False) as tmp:
            tmp.write(b"test content")
            tmp_path = tmp.name

        from app.services.document_processor import process_document
        import uuid
        doc_id = str(uuid.uuid4())

        # Should not raise
        import asyncio
        asyncio.run(process_document(tmp_path, os.path.basename(tmp_path), doc_id))

        mock_vector_store.add_documents.assert_called()
        chunks = mock_vector_store.add_documents.call_args[0][0]
        assert len(chunks) > 0
        assert chunks[0].metadata["document_id"] == doc_id
        assert chunks[0].metadata["source"] == os.path.basename(tmp_path)

        os.remove(tmp_path)
