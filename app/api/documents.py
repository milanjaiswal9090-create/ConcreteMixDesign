"""Document management API — upload, list, and reprocess documents."""

import os
import shutil
from typing import Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile
from sqlalchemy.orm import Session

from app.config import settings
from app.database import SessionLocal, get_db
from app.models import Document, DocumentChunk
from app.rag.ingestion import DocumentIngester

router = APIRouter(prefix="/api/documents", tags=["documents"])


def _ingester() -> DocumentIngester:
    return DocumentIngester(SessionLocal, upload_dir=settings.UPLOAD_DIR)


@router.post("/upload")
async def upload_document(
    file: UploadFile = File(...),
    standard_name: Optional[str] = Form(None),
    edition: Optional[str] = Form(None),
    admin_key: str = Form(...),
):
    """Upload a document for ingestion (requires admin key)."""
    if admin_key != settings.ADMIN_KEY:
        raise HTTPException(status_code=403, detail="Invalid admin key")

    if not file.filename:
        raise HTTPException(status_code=400, detail="No file provided")

    ext = os.path.splitext(file.filename)[1].lower()
    if ext not in DocumentIngester.SUPPORTED_TYPES:
        raise HTTPException(status_code=400, detail=f"Unsupported file type: {ext}")

    # Check size
    content = await file.read()
    if len(content) > settings.MAX_UPLOAD_SIZE:
        raise HTTPException(
            status_code=413,
            detail=f"File too large. Maximum {settings.MAX_UPLOAD_SIZE // (1024*1024)} MB.",
        )

    # Save to upload directory
    upload_path = settings.upload_path / file.filename
    with open(upload_path, "wb") as f:
        f.write(content)

    # Ingest
    ingester = _ingester()
    result = ingester.ingest_file(
        str(upload_path), file.filename,
        standard_name=standard_name or "",
        edition=edition or "",
    )
    return result


@router.get("")
def list_documents(db: Session = Depends(get_db)):
    """List all uploaded documents."""
    docs = db.query(Document).order_by(Document.created_at.desc()).all()
    results = []
    for doc in docs:
        chunk_count = db.query(DocumentChunk).filter(DocumentChunk.document_id == doc.id).count()
        results.append({
            "id": doc.id,
            "filename": doc.filename,
            "original_name": doc.original_name,
            "doc_type": doc.doc_type,
            "standard_name": doc.standard_name,
            "edition": doc.edition,
            "status": doc.status,
            "page_count": doc.page_count,
            "chunk_count": chunk_count,
            "error_message": doc.error_message,
            "created_at": doc.created_at.isoformat() if doc.created_at else None,
        })
    return {"total": len(results), "documents": results}


@router.get("/{doc_id}")
def get_document(doc_id: int, db: Session = Depends(get_db)):
    """Get document detail with chunks."""
    doc = db.query(Document).filter(Document.id == doc_id).first()
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")

    chunks = db.query(DocumentChunk).filter(
        DocumentChunk.document_id == doc.id
    ).order_by(DocumentChunk.chunk_index).all()

    return {
        "id": doc.id,
        "filename": doc.filename,
        "original_name": doc.original_name,
        "doc_type": doc.doc_type,
        "standard_name": doc.standard_name,
        "edition": doc.edition,
        "status": doc.status,
        "page_count": doc.page_count,
        "error_message": doc.error_message,
        "chunks": [
            {
                "id": c.id,
                "chunk_index": c.chunk_index,
                "text": c.chunk_text,
                "page_number": c.page_number,
                "section_heading": c.section_heading,
            }
            for c in chunks
        ],
    }
