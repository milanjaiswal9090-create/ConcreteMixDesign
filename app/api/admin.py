"""Admin API — import examples, rebuild indexes, system status."""

import os

from fastapi import APIRouter, Depends, Header, HTTPException, UploadFile, File
from sqlalchemy.orm import Session

from app.config import settings
from app.database import SessionLocal, get_db
from app.models import Document, DocumentChunk, DesignSession, Example
from app.rag.embeddings import TFIDFEmbedder
from app.rag.examples import ExampleManager
from app.rag.search import HybridSearcher

router = APIRouter(prefix="/api/admin", tags=["admin"])


def _require_admin(x_admin_key: str = Header(...)):
    """Dependency that checks the admin key header."""
    if x_admin_key != settings.ADMIN_KEY:
        raise HTTPException(status_code=403, detail="Invalid admin key")
    return True


@router.post("/import-examples")
def import_examples(
    file: UploadFile = File(...),
    _auth: bool = Depends(_require_admin),
):
    """Import solved examples from a JSONL file."""
    if not file.filename or not file.filename.endswith(".jsonl"):
        raise HTTPException(status_code=400, detail="Please upload a .jsonl file")

    # Save temporarily
    tmp_path = os.path.join(settings.DATA_DIR, "tmp_import.jsonl")
    os.makedirs(settings.DATA_DIR, exist_ok=True)
    with open(tmp_path, "wb") as f:
        content = file.file.read()
        f.write(content)

    mgr = ExampleManager(SessionLocal)
    result = mgr.import_from_jsonl(tmp_path)

    # Clean up
    try:
        os.remove(tmp_path)
    except OSError:
        pass

    return result


@router.post("/rebuild-index")
def rebuild_index(_auth: bool = Depends(_require_admin)):
    """Rebuild the TF-IDF search index from all examples."""
    mgr = ExampleManager(SessionLocal)
    docs = mgr.get_for_search_index()

    if not docs:
        return {"status": "no documents to index", "document_count": 0}

    embedder = TFIDFEmbedder()
    searcher = HybridSearcher(embedder)
    searcher.index_documents(docs)
    embedder.save_index()

    return {"status": "index rebuilt", "document_count": len(docs)}


@router.get("/status")
def system_status(
    _auth: bool = Depends(_require_admin),
    db: Session = Depends(get_db),
):
    """Get system health and statistics."""
    total_examples = db.query(Example).count()
    total_documents = db.query(Document).count()
    total_chunks = db.query(DocumentChunk).count()
    total_sessions = db.query(DesignSession).count()

    db_path = settings.DATABASE_URL.replace("sqlite:///", "")
    db_size = os.path.getsize(db_path) / (1024 * 1024) if os.path.exists(db_path) else 0

    # Check index status
    embedder = TFIDFEmbedder()
    index_ready = embedder.load_index()

    return {
        "app_name": settings.APP_NAME,
        "version": settings.APP_VERSION,
        "total_examples": total_examples,
        "total_documents": total_documents,
        "total_chunks": total_chunks,
        "total_sessions": total_sessions,
        "database_size_mb": round(db_size, 2),
        "search_index_ready": index_ready,
        "index_document_count": embedder.document_count if index_ready else 0,
    }


@router.post("/import-bundled-examples")
def import_bundled_examples(_auth: bool = Depends(_require_admin)):
    """Import the bundled 100 mix design examples from data/examples/."""
    jsonl_path = os.path.join(settings.DATA_DIR, "examples", "mix_problems.jsonl")
    if not os.path.exists(jsonl_path):
        raise HTTPException(
            status_code=404,
            detail=f"Bundled examples not found at {jsonl_path}",
        )
    mgr = ExampleManager(SessionLocal)
    result = mgr.import_from_jsonl(jsonl_path)
    return result
