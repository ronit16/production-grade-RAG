from fastapi import APIRouter, UploadFile, File, Depends, HTTPException, BackgroundTasks, Form
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from typing import List, Optional
from uuid import UUID
import uuid

from core.database import get_db
from models.db import DocumentMetadata, DocumentStatus
from models.schemas import DocumentResponse, DeleteResponse
from services.document_processor import process_upload_file, process_url, delete_document_from_vector_store

router = APIRouter()

async def background_process_file(file: UploadFile, doc_id: UUID, db: AsyncSession):
    try:
        await process_upload_file(file, doc_id)
        # Update status
        stmt = select(DocumentMetadata).where(DocumentMetadata.id == doc_id)
        result = await db.execute(stmt)
        doc = result.scalars().first()
        if doc:
            doc.status = DocumentStatus.COMPLETED
            await db.commit()
    except Exception as e:
        stmt = select(DocumentMetadata).where(DocumentMetadata.id == doc_id)
        result = await db.execute(stmt)
        doc = result.scalars().first()
        if doc:
            doc.status = DocumentStatus.FAILED
            doc.error_message = str(e)
            await db.commit()

async def background_process_url(url: str, doc_id: UUID, db: AsyncSession):
    try:
        await process_url(url, doc_id)
        stmt = select(DocumentMetadata).where(DocumentMetadata.id == doc_id)
        result = await db.execute(stmt)
        doc = result.scalars().first()
        if doc:
            doc.status = DocumentStatus.COMPLETED
            await db.commit()
    except Exception as e:
        stmt = select(DocumentMetadata).where(DocumentMetadata.id == doc_id)
        result = await db.execute(stmt)
        doc = result.scalars().first()
        if doc:
            doc.status = DocumentStatus.FAILED
            doc.error_message = str(e)
            await db.commit()

@router.post("/upload", response_model=DocumentResponse)
async def upload_document(
    background_tasks: BackgroundTasks,
    file: Optional[UploadFile] = File(None),
    url: Optional[str] = Form(None),
    tenant_id: str = Form(...),
    db: AsyncSession = Depends(get_db)
):
    if not file and not url:
        raise HTTPException(status_code=400, detail="Must provide either file or url")

    doc_id = uuid.uuid4()
    filename = file.filename if file else url
    ext = filename.split(".")[-1].lower() if file else "url"
    if url:
        source_type = "url"
    elif ext in ["pdf", "md", "docx", "doc", "txt", "html"]:
        source_type = ext
    else:
        source_type = "other"

    new_doc = DocumentMetadata(
        id=doc_id,
        tenant_id=tenant_id,
        filename=filename,
        source_type=source_type,
        status=DocumentStatus.PROCESSING
    )
    db.add(new_doc)
    await db.commit()
    await db.refresh(new_doc)

    if file:
        background_tasks.add_task(background_process_file, file, doc_id, db)
    else:
        background_tasks.add_task(background_process_url, url, doc_id, db)

    return new_doc

@router.get("/", response_model=List[DocumentResponse])
async def list_documents(db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(DocumentMetadata))
    documents = result.scalars().all()
    return documents

@router.delete("/{document_id}", response_model=DeleteResponse)
async def delete_document(document_id: UUID, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(DocumentMetadata).where(DocumentMetadata.id == document_id))
    doc = result.scalars().first()
    
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")
        
    # Remove from ChromaDB
    await delete_document_from_vector_store(document_id)
    
    # Remove from Postgres
    await db.delete(doc)
    await db.commit()
    
    return DeleteResponse(message="Document deleted successfully", document_id=document_id)
