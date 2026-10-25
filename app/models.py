"""
SQLAlchemy ORM models for ConcreteMix AI.

Tables:
- examples: Solved mix design examples for reference and RAG retrieval
- documents: Uploaded standards/reference documents
- document_chunks: Chunked text from processed documents
- design_sessions: User mix design calculation sessions
"""

import uuid
from datetime import datetime, timezone

from sqlalchemy import (
    Column,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
)
from sqlalchemy.orm import relationship

from app.database import Base


def _utcnow() -> datetime:
    """Return current UTC time."""
    return datetime.now(timezone.utc)


def _uuid() -> str:
    """Generate a new UUID string."""
    return str(uuid.uuid4())


class Example(Base):
    """
    Solved concrete mix design example.

    Stores problem statement, parsed inputs, full solution,
    and a retrieval_text field for search indexing.
    """

    __tablename__ = "examples"

    id: int = Column(Integer, primary_key=True, autoincrement=True)
    external_id: str = Column(String(20), unique=True, nullable=False, index=True)
    group: str = Column(String(50), nullable=True, index=True)
    grade: str = Column(String(10), nullable=True, index=True)
    exposure: str = Column(String(20), nullable=True, index=True)
    member: str = Column(String(10), nullable=True, default="RCC")
    max_size: int = Column(Integer, nullable=True)
    slump: int = Column(Integer, nullable=True)
    zone: str = Column(String(5), nullable=True)
    cement_grade: int = Column(Integer, nullable=True)
    problem_statement: str = Column(Text, nullable=True)
    inputs_json: str = Column(Text, nullable=True)
    solution_json: str = Column(Text, nullable=True)
    mix_json: str = Column(Text, nullable=True)
    checks_json: str = Column(Text, nullable=True)
    retrieval_text: str = Column(Text, nullable=True)
    verification_status: str = Column(
        String(20), nullable=False, default="unverified"
    )
    source: str = Column(String(100), nullable=True)
    created_at: datetime = Column(DateTime, default=_utcnow, nullable=False)
    updated_at: datetime = Column(
        DateTime, default=_utcnow, onupdate=_utcnow, nullable=False
    )

    def __repr__(self) -> str:
        return f"<Example {self.external_id} grade={self.grade}>"


class Document(Base):
    """
    Uploaded reference document (PDF, DOCX, TXT).

    Tracks processing status and metadata.
    """

    __tablename__ = "documents"

    id: int = Column(Integer, primary_key=True, autoincrement=True)
    filename: str = Column(String(255), nullable=False, unique=True)
    original_name: str = Column(String(255), nullable=False)
    doc_type: str = Column(String(10), nullable=False)  # pdf, docx, txt
    standard_name: str = Column(String(255), nullable=True)
    edition: str = Column(String(50), nullable=True)
    status: str = Column(
        String(20), nullable=False, default="pending"
    )  # pending, processed, failed
    page_count: int = Column(Integer, nullable=True)
    error_message: str = Column(Text, nullable=True)
    created_at: datetime = Column(DateTime, default=_utcnow, nullable=False)

    # Relationship to chunks
    chunks = relationship(
        "DocumentChunk", back_populates="document", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:
        return f"<Document {self.filename} status={self.status}>"


class DocumentChunk(Base):
    """
    Text chunk extracted from a processed document.

    Used for search and retrieval.
    """

    __tablename__ = "document_chunks"

    id: int = Column(Integer, primary_key=True, autoincrement=True)
    document_id: int = Column(
        Integer, ForeignKey("documents.id", ondelete="CASCADE"), nullable=False
    )
    chunk_text: str = Column(Text, nullable=False)
    chunk_index: int = Column(Integer, nullable=False)
    page_number: int = Column(Integer, nullable=True)
    section_heading: str = Column(String(255), nullable=True)
    metadata_json: str = Column(Text, nullable=True)
    created_at: datetime = Column(DateTime, default=_utcnow, nullable=False)

    # Relationship back to document
    document = relationship("Document", back_populates="chunks")

    def __repr__(self) -> str:
        return f"<DocumentChunk doc={self.document_id} idx={self.chunk_index}>"


class DesignSession(Base):
    """
    A saved mix design calculation session.

    Stores the user's input, parsed parameters, and computed result.
    """

    __tablename__ = "design_sessions"

    id: int = Column(Integer, primary_key=True, autoincrement=True)
    session_id: str = Column(
        String(36), unique=True, nullable=False, default=_uuid, index=True
    )
    problem_text: str = Column(Text, nullable=True)
    parsed_inputs_json: str = Column(Text, nullable=True)
    result_json: str = Column(Text, nullable=True)
    retrieved_examples_json: str = Column(Text, nullable=True)
    created_at: datetime = Column(DateTime, default=_utcnow, nullable=False)

    def __repr__(self) -> str:
        return f"<DesignSession {self.session_id}>"
