# Production Grade RAG System

A complete FastAPI, Langchain, and Gemini-powered RAG backend.

## Requirements
- Python 3.10+
- Docker & Docker Compose (for DBs)

## Setup

1. **Start Databases**
   ```bash
   docker-compose up -d
   ```

2. **Install Dependencies**
   ```bash
   python -m venv venv
   source venv/bin/activate
   pip install -r requirements.txt
   ```

3. **Configure Environment**
   Update `.env` with your actual `GEMINI_API_KEY`. The database URLs are pre-configured for the `docker-compose` setup.

4. **Run Application**
   ```bash
   uvicorn main:app --reload
   ```

5. **Run Tests**
   ```bash
   pytest
   ```

## Endpoints

- **POST /documents/upload**: Upload a file (PDF/MD/DOCX) or form `url` to process and store in ChromaDB.
- **GET /documents/**: List all uploaded documents.
- **DELETE /documents/{id}**: Delete a document from SQL and ChromaDB.
- **POST /chat/query**: Ask a question with `query` and optional `session_id`. Returns Gemini response with citations.
