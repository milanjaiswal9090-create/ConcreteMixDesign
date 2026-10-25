"""Search API — hybrid BM25 + TF-IDF retrieval across examples and documents."""

from fastapi import APIRouter, Query

from app.database import SessionLocal
from app.rag.embeddings import TFIDFEmbedder
from app.rag.examples import ExampleManager
from app.rag.search import HybridSearcher

router = APIRouter(prefix="/api/search", tags=["search"])


@router.get("")
def search(
    q: str = Query(..., min_length=2, description="Search query"),
    top_k: int = Query(10, ge=1, le=50),
    grade: str = Query(None),
    exposure: str = Query(None),
    zone: str = Query(None),
):
    """Hybrid search across examples and document chunks.

    Combines BM25 keyword matching with TF-IDF cosine similarity.
    Supports metadata filtering by grade, exposure, and zone.
    """
    embedder = TFIDFEmbedder()
    searcher = HybridSearcher(embedder)

    # Load or build index
    if not embedder.load_index():
        mgr = ExampleManager(SessionLocal)
        docs = mgr.get_for_search_index()
        if not docs:
            return {"query": q, "total": 0, "results": [], "method": "no index available"}
        searcher.index_documents(docs)
        embedder.save_index()
    else:
        # Reconstruct searcher state from loaded embedder
        from rank_bm25 import BM25Okapi
        searcher.documents = [
            {"id": eid, "text": txt, "metadata": meta}
            for eid, txt, meta in zip(embedder.doc_ids, embedder.doc_texts, embedder.doc_metadata)
        ]
        tokenized = [searcher._tokenize(t) for t in embedder.doc_texts]
        if tokenized:
            searcher.bm25 = BM25Okapi(tokenized)
        searcher.tokenized_corpus = tokenized

    # Build metadata filter
    meta_filter = {}
    if grade:
        meta_filter["grade"] = grade
    if exposure:
        meta_filter["exposure"] = exposure
    if zone:
        meta_filter["zone"] = zone

    results = searcher.search(q, top_k=top_k, metadata_filter=meta_filter or None)

    return {
        "query": q,
        "total": len(results),
        "filters_applied": meta_filter,
        "method": "hybrid BM25 + TF-IDF (deterministic, no external API)",
        "results": results,
    }
