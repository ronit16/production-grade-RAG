import uuid
from datetime import datetime, timezone
from sqlalchemy import Column, String, DateTime, Text, ForeignKey, Enum
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
import enum

from core.database import Base

class DocumentStatus(str, enum.Enum):
    UPLOADED = "uploaded"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"

class DocumentMetadata(Base):
    __tablename__ = "document_metadata"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    filename = Column(String(255), nullable=False)
    source_type = Column(String(50), nullable=False) # e.g., pdf, md, url
    upload_time = Column(DateTime(timezone=True), default=datetime.now(timezone.utc))
    status = Column(Enum(DocumentStatus), default=DocumentStatus.UPLOADED)
    error_message = Column(Text, nullable=True)

class ChatSession(Base):
    __tablename__ = "chat_sessions"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    title = Column(String(255), nullable=True)
    created_at = Column(DateTime(timezone=True), default=datetime.now(timezone.utc))
    updated_at = Column(DateTime(timezone=True), default=datetime.now(timezone.utc), onupdate=datetime.now(timezone.utc))
    
    messages = relationship("ChatMessage", back_populates="session", cascade="all, delete-orphan")

class ChatMessage(Base):
    __tablename__ = "chat_messages"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    session_id = Column(UUID(as_uuid=True), ForeignKey("chat_sessions.id", ondelete="CASCADE"), nullable=False)
    role = Column(String(50), nullable=False) # 'user' or 'assistant'
    content = Column(Text, nullable=False)
    timestamp = Column(DateTime(timezone=True), default=datetime.now(timezone.utc))

    session = relationship("ChatSession", back_populates="messages")
