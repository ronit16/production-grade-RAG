from fastapi import FastAPI
from contextlib import asynccontextmanager
from core.database import engine, Base, redis_client
from core.config import settings

from api.routes import documents, chat

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup: create tables if they don't exist
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield
    # Shutdown: close redis connection
    await redis_client.aclose()

app = FastAPI(
    title=settings.PROJECT_NAME,
    version=settings.VERSION,
    lifespan=lifespan
)

app.include_router(documents.router, prefix="/documents", tags=["documents"])
app.include_router(chat.router, prefix="/chat", tags=["chat"])

@app.get("/")
async def root():
    return {"message": "Welcome to the Production Grade RAG System API"}
