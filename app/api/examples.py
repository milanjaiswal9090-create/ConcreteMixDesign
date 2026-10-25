"""Examples API — CRUD and search for solved mix design examples."""

import json
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.database import get_db, SessionLocal
from app.models import Example
from app.rag.examples import ExampleManager

router = APIRouter(prefix="/api/examples", tags=["examples"])


def _mgr() -> ExampleManager:
    return ExampleManager(SessionLocal)


@router.get("")
def list_examples(
    grade: Optional[str] = Query(None),
    exposure: Optional[str] = Query(None),
    zone: Optional[str] = Query(None),
    group: Optional[str] = Query(None),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
):
    """List examples with optional filters."""
    examples, total = _mgr().list_examples(grade, exposure, zone, group, limit, offset)
    return {"total": total, "limit": limit, "offset": offset, "results": examples}


@router.get("/stats")
def example_statistics():
    """Get statistics about the example collection."""
    return _mgr().get_statistics()


@router.get("/search")
def search_examples(
    q: str = Query(..., min_length=2),
    top_k: int = Query(10, ge=1, le=50),
):
    """Search examples by query text."""
    from app.rag.search import HybridSearcher
    from app.rag.embeddings import TFIDFEmbedder

    embedder = TFIDFEmbedder()
    if not embedder.load_index():
        # Build index on the fly
        docs = _mgr().get_for_search_index()
        if not docs:
            return {"query": q, "total": 0, "results": []}
        searcher = HybridSearcher(embedder)
        searcher.index_documents(docs)
    else:
        searcher = HybridSearcher(embedder)
        searcher.documents = [
            {"id": eid, "text": txt, "metadata": meta}
            for eid, txt, meta in zip(embedder.doc_ids, embedder.doc_texts, embedder.doc_metadata)
        ]
        from rank_bm25 import BM25Okapi
        import re
        tokenized = [re.findall(r"[a-z0-9]+", t.lower()) for t in embedder.doc_texts]
        if tokenized:
            searcher.bm25 = BM25Okapi(tokenized)
        searcher.tokenized_corpus = tokenized

    results = searcher.search(q, top_k=top_k)
    return {"query": q, "total": len(results), "results": results}


@router.get("/{example_id}")
def get_example(example_id: str):
    """Get a single example by external ID (e.g. P001)."""
    ex = _mgr().get_example(example_id)
    if not ex:
        raise HTTPException(status_code=404, detail=f"Example '{example_id}' not found")
    return ex
