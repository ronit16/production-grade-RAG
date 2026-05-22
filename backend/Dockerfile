FROM python:3.11-slim

WORKDIR /app

# System deps for unstructured (PDF/DOCX parsing) + sentence-transformers
RUN apt-get update && apt-get install -y --no-install-recommends \
        build-essential \
        libpoppler-cpp-dev \
        poppler-utils \
        libmagic1 \
        tesseract-ocr \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Default: API server. Override CMD in docker-compose for the worker.
CMD ["gunicorn", "app.main:app", \
     "-k", "uvicorn.workers.UvicornWorker", \
     "-w", "4", \
     "--bind", "0.0.0.0:8000", \
     "--timeout", "120", \
     "--graceful-timeout", "30", \
     "--keep-alive", "5"]
