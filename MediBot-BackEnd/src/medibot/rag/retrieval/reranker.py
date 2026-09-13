"""
Cross-encoder reranking workflow: src/medibot/rag/retrieval/reranker.py.

Uses LangChain's HuggingFaceCrossEncoder wrapper around
cross-encoder/ms-marco-MiniLM-L-6-v2 (~67MB) instead of bge-reranker-base
(~280MB) -- much faster first-run download. Internally this still wraps
sentence-transformers.CrossEncoder and needs the same one-time HuggingFace
download as the shared embedding model, just a much smaller file.
"""

import logging
from dataclasses import dataclass
from typing import Any

logger = logging.getLogger("medibot.reranker")

_MODEL_NAME = "cross-encoder/ms-marco-MiniLM-L-6-v2"
_cross_encoder = None


def get_reranker():
    """Lazy-load the cross-encoder once and reuse it across requests."""
    global _cross_encoder
    if _cross_encoder is None:
        logger.info(f"Loading cross-encoder model: {_MODEL_NAME}")
        from langchain_community.cross_encoders import HuggingFaceCrossEncoder
        _cross_encoder = HuggingFaceCrossEncoder(model_name=_MODEL_NAME)
    return _cross_encoder


@dataclass
class RankedChunk:
    chunk_id: str
    text: str
    metadata: dict[str, Any]
    initial_rank: int
    initial_score: float
    rerank_score: float
    final_rank: int


def qdrant_hits_to_candidates(hits) -> list[dict]:
    """Adapts Qdrant ScoredPoint results (from qdrant_search) into
    the plain-dict shape rerank_chunks() expects. Payload fields are flat."""
    candidates = []
    for hit in hits:
        p = hit.payload
        candidates.append({
            "chunk_id": p["chunk_id"],
            "text": p["text"],
            "metadata": {
                "source_document": p["source_document"],
                "collection": p["collection"],
                "access_roles": p["access_roles"],
                "section_title": p["section_title"],
                "chunk_type": p["chunk_type"],
            },
            "score": hit.score,
        })
    return candidates


def rerank_chunks(query: str, candidates: list[dict[str, Any]], top_k: int = 3) -> list[RankedChunk]:
    if not candidates:
        return []

    model = get_reranker()
    pairs = [(query, c["text"]) for c in candidates]
    scores = model.score(pairs)  # HuggingFaceCrossEncoder API is .score(), not .predict()

    ranked = [
        RankedChunk(
            chunk_id=c["chunk_id"],
            text=c["text"],
            metadata=c["metadata"],
            initial_rank=i,
            initial_score=c.get("score", 0.0),
            rerank_score=float(scores[i]),
            final_rank=-1,
        )
        for i, c in enumerate(candidates)
    ]
    ranked.sort(key=lambda r: r.rerank_score, reverse=True)
    for final_rank, r in enumerate(ranked):
        r.final_rank = final_rank

    _log_rerank_shift(query, ranked)
    return ranked[:top_k]


def _log_rerank_shift(query: str, ranked: list[RankedChunk]) -> None:
    logger.info(f"Rerank scores for query: {query!r}")
    for r in ranked:
        shift = r.initial_rank - r.final_rank
        arrow = "↑" if shift > 0 else ("↓" if shift < 0 else "=")
        logger.info(
            f"  [{r.chunk_id}] initial_rank={r.initial_rank} -> final_rank={r.final_rank} "
            f"({arrow}{abs(shift)})  hybrid_score={r.initial_score:.4f}  rerank_score={r.rerank_score:.4f}  "
            f"section={r.metadata.get('section_title')}"
        )
