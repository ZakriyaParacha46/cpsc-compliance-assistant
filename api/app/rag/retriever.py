"""Hybrid retrieval: BM25 keyword search + pgvector similarity, merged with reciprocal rank fusion.

Why not LangChain's EnsembleRetriever: it drops scores, and we need the vector distance for
the relevance threshold ("not covered" without calling the LLM). This class is still a
LangChain BaseRetriever, so it plugs into LCEL chains the same way.
"""

import re
from dataclasses import dataclass, field
from typing import Any, Literal

from langchain_core.callbacks import CallbackManagerForRetrieverRun
from langchain_core.documents import Document
from langchain_core.retrievers import BaseRetriever
from rank_bm25 import BM25Okapi

Mode = Literal["vector", "bm25", "hybrid"]

# Keeps section numbers and dotted terms whole: "1263.3", "u.s.c", "f963".
_TOKEN = re.compile(r"[a-z0-9]+(?:\.[a-z0-9]+)*")
_STOPWORDS = frozenset(
    "a an and are as at be by can do does for from has have how i if in is it its my of on or "
    "our should that the their them there these this to was what when where which who will with "
    "you your".split()
)


def tokenize(text: str) -> list[str]:
    return [t for t in _TOKEN.findall(text.lower()) if t not in _STOPWORDS]


def chunk_key(meta: dict[str, Any]) -> str:
    return f"{meta['doc_id']}|{meta['section']}|{meta.get('chunk_index', 0)}"


def section_key(meta: dict[str, Any]) -> str:
    return f"{meta['doc_id']}|{meta['section']}"


class KeywordIndex:
    """In-memory BM25 over every chunk. A few thousand chunks fit easily; rebuilt at startup."""

    def __init__(self, docs: list[Document]):
        self.docs = docs
        self._bm25 = BM25Okapi([tokenize(d.page_content) for d in docs]) if docs else None

    def search(self, query: str, k: int) -> list[Document]:
        if self._bm25 is None:
            return []
        scores = self._bm25.get_scores(tokenize(query))
        ranked = sorted(range(len(self.docs)), key=lambda i: scores[i], reverse=True)
        return [self.docs[i] for i in ranked[:k] if scores[i] > 0]


@dataclass
class SearchResult:
    docs: list[Document]
    # Cosine distance of the closest chunk by meaning (0 = identical). Drives the threshold.
    best_distance: float | None
    distances: dict[str, float] = field(default_factory=dict)  # chunk_key -> distance


class HybridRetriever(BaseRetriever):
    vector_store: Any  # langchain_postgres.PGVector (Any keeps tests free of a database)
    keyword_index: KeywordIndex
    mode: Mode = "hybrid"
    k: int = 6
    fetch_k: int = 30  # candidates taken from each method before fusing
    rrf_k: int = 60  # standard RRF constant: dampens the gap between rank 1 and rank 2
    one_per_section: bool = True

    model_config = {"arbitrary_types_allowed": True}

    def search(self, query: str) -> SearchResult:
        scored = self.vector_store.similarity_search_with_score(query, k=self.fetch_k)
        distances = {chunk_key(d.metadata): float(s) for d, s in scored}
        best = min(distances.values()) if distances else None
        vector_docs = [d for d, _ in scored]

        if self.mode == "vector":
            ranked = vector_docs
        elif self.mode == "bm25":
            ranked = self.keyword_index.search(query, self.fetch_k)
        else:
            ranked = self._fuse([vector_docs, self.keyword_index.search(query, self.fetch_k)])

        picked, seen = [], set()
        for d in ranked:
            key = section_key(d.metadata) if self.one_per_section else chunk_key(d.metadata)
            if key in seen:
                continue
            seen.add(key)
            picked.append(d)
            if len(picked) == self.k:
                break
        return SearchResult(docs=picked, best_distance=best, distances=distances)

    def _fuse(self, rankings: list[list[Document]]) -> list[Document]:
        """Reciprocal rank fusion: score = sum of 1 / (rrf_k + rank) across rankings."""
        scores: dict[str, float] = {}
        by_key: dict[str, Document] = {}
        for ranking in rankings:
            for rank, d in enumerate(ranking, start=1):
                key = chunk_key(d.metadata)
                scores[key] = scores.get(key, 0.0) + 1.0 / (self.rrf_k + rank)
                by_key.setdefault(key, d)
        return [by_key[k] for k in sorted(scores, key=scores.get, reverse=True)]

    def _get_relevant_documents(
        self, query: str, *, run_manager: CallbackManagerForRetrieverRun
    ) -> list[Document]:
        return self.search(query).docs
