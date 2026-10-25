"""Hybrid search combining BM25 keyword retrieval with TF-IDF semantic search.

Supports metadata filtering for precise retrieval across the concrete mix
design example corpus and ingested documents.
"""

import logging
import re
from typing import Any, Dict, List, Optional

import numpy as np
from rank_bm25 import BM25Okapi

from app.rag.embeddings import TFIDFEmbedder

logger = logging.getLogger(__name__)


class HybridSearcher:
    """Combines BM25 keyword search with TF-IDF semantic search.

    Metadata filtering lets users narrow results by grade, exposure,
    zone, aggregate size, etc.
    """

    def __init__(self, tfidf_embedder: Optional[TFIDFEmbedder] = None) -> None:
        self.embedder = tfidf_embedder or TFIDFEmbedder()
        self.bm25: Optional[BM25Okapi] = None
        self.documents: List[Dict[str, Any]] = []
        self.tokenized_corpus: List[List[str]] = []

    # ------------------------------------------------------------------
    # Indexing
    # ------------------------------------------------------------------

    def index_documents(self, documents: List[Dict[str, Any]]) -> None:
        """Index documents for both BM25 and TF-IDF search.

        Args:
            documents: list of ``{id, text, metadata}`` dicts.
        """
        if not documents:
            logger.warning("index_documents called with empty list")
            return

        self.documents = documents

        # Tokenise for BM25
        self.tokenized_corpus = [self._tokenize(doc["text"]) for doc in documents]
        if self.tokenized_corpus:
            self.bm25 = BM25Okapi(self.tokenized_corpus)
        else:
            self.bm25 = None

        # Build TF-IDF index
        self.embedder.build_index(documents)

        logger.info("HybridSearcher indexed %d documents", len(documents))

    # ------------------------------------------------------------------
    # Search
    # ------------------------------------------------------------------

    def search(
        self,
        query: str,
        top_k: int = 5,
        metadata_filter: Optional[Dict[str, Any]] = None,
        bm25_weight: float = 0.4,
        tfidf_weight: float = 0.6,
    ) -> List[Dict[str, Any]]:
        """Hybrid search with optional metadata filtering.

        Returns list of ``{id, text, score, metadata, retrieval_method,
        relevance_indicators}`` dicts, sorted by descending combined score.
        """
        if not self.documents:
            return []

        n = len(self.documents)

        # ── BM25 scores ─────────────────────────────────────────────────
        bm25_scores = np.zeros(n)
        if self.bm25 is not None:
            tokenized_query = self._tokenize(query)
            raw = self.bm25.get_scores(tokenized_query)
            bm25_scores = self._normalize_scores(raw)

        # ── TF-IDF cosine scores ─────────────────────────────────────────
        tfidf_scores = np.zeros(n)
        if self.embedder.is_ready:
            raw = self.embedder.get_all_scores(query)
            if raw.size == n:
                tfidf_scores = self._normalize_scores(raw)

        # ── Combine ──────────────────────────────────────────────────────
        combined = bm25_weight * bm25_scores + tfidf_weight * tfidf_scores

        # Build result list
        results: List[Dict[str, Any]] = []
        for idx in range(n):
            doc = self.documents[idx]
            meta = doc.get("metadata", {})

            # Metadata filter
            if metadata_filter and not self._matches_filter(meta, metadata_filter):
                continue

            # Determine dominant retrieval method
            if bm25_scores[idx] > tfidf_scores[idx]:
                method = "keyword (BM25)"
            elif tfidf_scores[idx] > bm25_scores[idx]:
                method = "semantic (TF-IDF)"
            else:
                method = "hybrid"

            results.append(
                {
                    "id": doc["id"],
                    "text": doc["text"][:500],
                    "score": float(combined[idx]),
                    "bm25_score": float(bm25_scores[idx]),
                    "tfidf_score": float(tfidf_scores[idx]),
                    "metadata": meta,
                    "retrieval_method": method,
                }
            )

        results.sort(key=lambda r: r["score"], reverse=True)
        return results[:top_k]

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _matches_filter(metadata: Dict, filter_dict: Dict) -> bool:
        """Check if metadata matches all filter conditions."""
        for key, expected in filter_dict.items():
            if expected is None or expected == "":
                continue
            actual = metadata.get(key)
            if actual is None:
                return False
            if str(actual).lower() != str(expected).lower():
                return False
        return True

    @staticmethod
    def _tokenize(text: str) -> List[str]:
        """Simple whitespace + punctuation tokeniser for BM25."""
        text = text.lower()
        tokens = re.findall(r"[a-z0-9]+(?:\.[0-9]+)?", text)
        # Remove very common stop words
        stop = {
            "the", "a", "an", "is", "are", "was", "were", "be", "been",
            "of", "in", "to", "for", "and", "or", "with", "on", "at",
            "by", "from", "as", "it", "this", "that", "which",
        }
        return [t for t in tokens if t not in stop and len(t) > 1]

    @staticmethod
    def _normalize_scores(scores: np.ndarray) -> np.ndarray:
        """Min–max normalise scores to [0, 1]."""
        if scores.size == 0:
            return scores
        lo, hi = scores.min(), scores.max()
        if hi - lo < 1e-12:
            return np.zeros_like(scores)
        return (scores - lo) / (hi - lo)
