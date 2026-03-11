import uuid
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from typing import List

from core.database import get_db
from models.db import ChatSession, ChatMessage
from models.schemas import ChatRequest, ChatResponse, Citation
from services.rag_service import generate_rag_response
from services.session_manager import get_session_history_from_redis, append_to_redis_session

router = APIRouter()

@router.post("/query", response_model=ChatResponse)
async def chat_query(request: ChatRequest, db: AsyncSession = Depends(get_db)):
    session_id = request.session_id
    
    if not session_id:
        # Create a new session in Postgres
        session_id = uuid.uuid4()
        new_session = ChatSession(id=session_id, title=request.query[:50])
        db.add(new_session)
        await db.commit()
    else:
        # Verify session exists
        result = await db.execute(select(ChatSession).where(ChatSession.id == session_id))
        session = result.scalars().first()
        if not session:
            raise HTTPException(status_code=404, detail="Session not found")

    # Save User message to Postgres
    user_msg = ChatMessage(session_id=session_id, role="user", content=request.query)
    db.add(user_msg)
    
    # Fetch History from Redis
    history = await get_session_history_from_redis(session_id)
    
    # Optional logic: we could inject history into the prompt depending on requirements,
    # but for true LangChain memory we might want a slightly different rag_chain.
    # We will inject it inside the query text for basic context if history exists.
    contextualized_query = request.query
    if history:
         contextualized_query = f"Previous conversation history:\n{history}\n\nUser Question: {request.query}"

    # Generate Response
    try:
        answer, citations_raw = await generate_rag_response(contextualized_query)
        
        # Save Assistant message to Postgres
        assistant_msg = ChatMessage(session_id=session_id, role="assistant", content=answer)
        db.add(assistant_msg)
        await db.commit()

        # Update Redis Cache
        await append_to_redis_session(session_id, "user", request.query)
        await append_to_redis_session(session_id, "assistant", answer)

        citations = [Citation(**c) for c in citations_raw]

        return ChatResponse(
            session_id=session_id,
            answer=answer,
            citations=citations
        )
    except Exception as e:
        await db.rollback()
        raise HTTPException(status_code=500, detail=f"Failed to generate response: {str(e)}")
