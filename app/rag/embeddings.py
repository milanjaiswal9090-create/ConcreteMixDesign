"""TF-IDF based document embeddings for semantic search.

No external API key required. Works entirely offline.
Uses scikit-learn TF-IDF vectorizer with cosine similarity for
fast, lightweight semantic search over concrete mix design documents.
"""

import json
import logging
import os
from typing import Dict, List, Optional, Tuple

import numpy as np
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

logger = logging.getLogger(__name__)


class TFIDFEmbedder:
    """Manages TF-IDF vectorization and similarity search.

    Builds an in-memory TF-IDF index over a corpus of documents,
    supports cosine-similarity search, and can persist/load the index
    to/from disk as JSON + numpy arrays.
    """

    def __init__(self, index_path: str = "data/tfidf_index") -> None:
        self.index_path = index_path
        self.vectorizer = TfidfVectorizer(
            max_features=10000,
            ngram_range=(1, 2),  # unigrams and bigrams
            stop_words="english",
            sublinear_tf=True,
            min_df=1,
            max_df=0.95,
        )
        self.doc_matrix: Optional[np.ndarray] = None
        self.doc_ids: List[str] = []
        self.doc_metadata: List[Dict] = []
        self.doc_texts: List[str] = []
        self._is_fitted: bool = False
        os.makedirs(index_path, exist_ok=True)

    # ------------------------------------------------------------------
    # Indexing
    # ------------------------------------------------------------------

    def build_index(self, documents: List[Dict]) -> None:
        """Build TF-IDF index from documents.

        Args:
            documents: List of dicts, each with keys:
                - id (str): unique document identifier
                - text (str): full text content to index
                - metadata (dict): arbitrary metadata for filtering
        """
        if not documents:
            logger.warning("build_index called with empty document list")
            return

        self.doc_ids = [str(doc["id"]) for doc in documents]
        self.doc_texts = [doc.get("text", "") for doc in documents]
        self.doc_metadata = [doc.get("metadata", {}) for doc in documents]

        # Fit and transform the corpus
        self.doc_matrix = self.vectorizer.fit_transform(self.doc_texts)
        self._is_fitted = True

        logger.info(
            "TF-IDF index built: %d documents, vocabulary size %d",
            len(documents),
            len(self.vectorizer.vocabulary_),
        )

    # ------------------------------------------------------------------
    # Search
    # ------------------------------------------------------------------

    def search(
        self,
        query: str,
        top_k: int = 5,
        metadata_filter: Optional[Dict] = None,
    ) -> List[Tuple[str, float, Dict]]:
        """Search the index returning (doc_id, similarity_score, metadata).

        Args:
            query: Search query string.
            top_k: Number of top results to return.
            metadata_filter: Optional dict of {field: value} to filter by.

        Returns:
            List of (doc_id, cosine_similarity_score, metadata) tuples,
            sorted by descending similarity.
        """
        if not self._is_fitted or self.doc_matrix is None:
            logger.warning("search called on un-fitted index; returning empty")
            return []

        # Transform query using the fitted vectorizer
        query_vec = self.vectorizer.transform([query])

        # Compute cosine similarity between query and all documents
        similarities = cosine_similarity(query_vec, self.doc_matrix).flatten()

        # Pair with doc IDs and metadata
        scored: List[Tuple[str, float, Dict]] = []
        for idx, score in enumerate(similarities):
            meta = self.doc_metadata[idx] if idx < len(self.doc_metadata) else {}

            # Apply metadata filter if provided
            if metadata_filter:
                if not self._matches_filter(meta, metadata_filter):
                    continue

            scored.append((self.doc_ids[idx], float(score), meta))

        # Sort descending by similarity score
        scored.sort(key=lambda x: x[1], reverse=True)

        return scored[:top_k]

    def get_all_scores(self, query: str) -> np.ndarray:
        """Return raw cosine similarity scores for all documents.

        Used by HybridSearcher to combine with BM25 scores.

        Args:
            query: Search query string.

        Returns:
            1-D numpy array of similarity scores (one per document).
        """
        if not self._is_fitted or self.doc_matrix is None:
            return np.array([])

        query_vec = self.vectorizer.transform([query])
        return cosine_similarity(query_vec, self.doc_matrix).flatten()

    # ------------------------------------------------------------------
    # Persistence
    # ------------------------------------------------------------------

    def save_index(self) -> None:
        """Persist the TF-IDF index to disk.

        Saves:
        - vocabulary and IDF weights as JSON
        - document matrix as a numpy .npy file
        - document IDs and metadata as JSON
        """
        if not self._is_fitted:
            logger.warning("save_index called on un-fitted index; skipping")
            return

        # 1. Vocabulary + IDF weights
        vocab_data = {
            "vocabulary": {k: int(v) for k, v in self.vectorizer.vocabulary_.items()},
            "idf": [float(x) for x in self.vectorizer.idf_.tolist()],
        }
        vocab_path = os.path.join(self.index_path, "vocab.json")
        with open(vocab_path, "w", encoding="utf-8") as f:
            json.dump(vocab_data, f, ensure_ascii=False)

        # 2. Document matrix (sparse → dense for simplicity)
        matrix_path = os.path.join(self.index_path, "doc_matrix.npy")
        np.save(matrix_path, self.doc_matrix.toarray())  # type: ignore[union-attr]

        # 3. Document IDs and metadata
        docs_data = {
            "doc_ids": self.doc_ids,
            "doc_metadata": self.doc_metadata,
            "doc_texts": self.doc_texts,
        }
        docs_path = os.path.join(self.index_path, "documents.json")
        with open(docs_path, "w", encoding="utf-8") as f:
            json.dump(docs_data, f, ensure_ascii=False)

        logger.info("TF-IDF index saved to %s", self.index_path)

    def load_index(self) -> bool:
        """Load a previously-saved index from disk.

        Returns:
            True if the index was loaded successfully, False otherwise.
        """
        vocab_path = os.path.join(self.index_path, "vocab.json")
        matrix_path = os.path.join(self.index_path, "doc_matrix.npy")
        docs_path = os.path.join(self.index_path, "documents.json")

        # Check all required files exist
        if not all(os.path.exists(p) for p in [vocab_path, matrix_path, docs_path]):
            logger.info("Index files not found at %s; load_index returning False", self.index_path)
            return False

        try:
            # 1. Load vocabulary + IDF
            with open(vocab_path, "r", encoding="utf-8") as f:
                vocab_data = json.load(f)

            # Reconstruct vectorizer state
            # We need to do a dummy fit first so internal state is consistent,
            # then overwrite vocabulary_ and idf_.
            self.vectorizer = TfidfVectorizer(
                max_features=10000,
                ngram_range=(1, 2),
                stop_words="english",
                sublinear_tf=True,
                min_df=1,
                max_df=0.95,
            )

            # 3. Load documents data
            with open(docs_path, "r", encoding="utf-8") as f:
                docs_data = json.load(f)

            self.doc_ids = docs_data["doc_ids"]
            self.doc_metadata = docs_data["doc_metadata"]
            self.doc_texts = docs_data.get("doc_texts", [])

            # Fit the vectorizer on the original texts so it's in a valid state,
            # then overwrite with saved vocabulary and IDF for exact reproducibility.
            if self.doc_texts:
                self.vectorizer.fit(self.doc_texts)
                self.vectorizer.vocabulary_ = {
                    k: int(v) for k, v in vocab_data["vocabulary"].items()
                }
                self.vectorizer.idf_ = np.array(vocab_data["idf"])

            # 2. Load document matrix
            dense_matrix = np.load(matrix_path)
            from scipy.sparse import csr_matrix
            self.doc_matrix = csr_matrix(dense_matrix)

            self._is_fitted = True
            logger.info(
                "TF-IDF index loaded: %d documents from %s",
                len(self.doc_ids),
                self.index_path,
            )
            return True

        except Exception:
            logger.exception("Failed to load TF-IDF index from %s", self.index_path)
            self._is_fitted = False
            return False

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _matches_filter(metadata: Dict, filter_dict: Dict) -> bool:
        """Check if metadata matches all filter conditions.

        Args:
            metadata: Document metadata dictionary.
            filter_dict: Filter conditions as {field: expected_value}.

        Returns:
            True if all filter conditions match.
        """
        for key, expected in filter_dict.items():
            actual = metadata.get(key)
            if actual is None:
                return False
            # Normalise both sides to string for comparison (handles int/str mismatches)
            if str(actual).lower() != str(expected).lower():
                return False
        return True

    @property
    def document_count(self) -> int:
        """Number of documents currently in the index."""
        return len(self.doc_ids)

    @property
    def is_ready(self) -> bool:
        """Whether the index is fitted and ready for search."""
        return self._is_fitted and self.doc_matrix is not None
