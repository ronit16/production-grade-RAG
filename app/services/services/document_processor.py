import os
import aiofiles
from fastapi import UploadFile
from typing import List, Optional
from uuid import UUID

from langchain_community.document_loaders import (
    PyPDFLoader,
    UnstructuredMarkdownLoader,
    Docx2txtLoader,
    WebBaseLoader,
    UnstructuredHTMLLoader,
    TextLoader
)
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_google_genai import GoogleGenerativeAIEmbeddings
from langchain_chroma import Chroma

from app.core.config import settings
from app.core.database import chroma_client

# Define the embedding model using Gemini
embeddings = GoogleGenerativeAIEmbeddings(
    model="models/embedding-001",
    google_api_key=settings.GEMINI_API_KEY
)

# Initialize the vector store using the persistent client
vector_store = Chroma(
    client=chroma_client,
    collection_name="rag_documents",
    embedding_function=embeddings,
)

async def process_upload_file(file: UploadFile, document_id: UUID) -> List:
    # Save uploaded file temporarily to process it
    temp_dir = "./temp_uploads"
    os.makedirs(temp_dir, exist_ok=True)
    file_path = f"{temp_dir}/{document_id}_{file.filename}"
    
    async with aiofiles.open(file_path, 'wb') as out_file:
        content = await file.read()
        await out_file.write(content)

    return await process_document(file_path, file.filename, str(document_id), file.content_type)

async def process_document(file_path: str, filename: str, document_id: str, content_type: Optional[str] = None) -> None:

    loader = None
    ext = filename.lower().split(".")[-1]
    if ext == "pdf" or content_type == "application/pdf":
        loader = PyPDFLoader(file_path)
    elif ext == "md":
        loader = UnstructuredMarkdownLoader(file_path)
    elif ext in ("docx", "doc"):
        loader = Docx2txtLoader(file_path)
    elif ext == "html" or content_type == "text/html":
        loader = UnstructuredHTMLLoader(file_path)
    elif ext == "txt" or content_type == "text/plain":
        loader = TextLoader(file_path)
    else:
        raise ValueError(f"Unsupported file type for {filename}")

    # Load documents
    docs = loader.load()

    # Define the text splitter with chunk_size 800 and overlap 120
    text_splitter = RecursiveCharacterTextSplitter(
        chunk_size=settings.CHUNK_SIZE,
        chunk_overlap=settings.CHUNK_OVERLAP,
        add_start_index=True,
    )

    # Split documents into chunks
    chunks = text_splitter.split_documents(docs)

    # Add metadata to chunks to link back to the document
    for chunk in chunks:
        chunk.metadata["document_id"] = document_id
        chunk.metadata["source"] = filename

    # Add to ChromaDB
    vector_store.add_documents(chunks)

async def process_url(url: str, document_id: UUID) -> None:
    loader = WebBaseLoader(url)
    docs = loader.load()

    text_splitter = RecursiveCharacterTextSplitter(
        chunk_size=settings.CHUNK_SIZE,
        chunk_overlap=settings.CHUNK_OVERLAP,
        add_start_index=True,
    )

    chunks = text_splitter.split_documents(docs)

    for chunk in chunks:
        chunk.metadata["document_id"] = str(document_id)
        chunk.metadata["source"] = url

    vector_store.add_documents(chunks)

async def delete_document_from_vector_store(document_id: UUID) -> None:
    # Delete chunks associated with specific document_id from ChromaDB
    # Chromadb delete uses where filter
    vector_store.delete(where={"document_id": str(document_id)})
