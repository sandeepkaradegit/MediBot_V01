"""Qdrant retrieval workflow: src/medibot/rag/retrieval/qdrant_search.py."""

from qdrant_client import QdrantClient
from qdrant_client.models import Fusion, FusionQuery, Prefetch, SparseVector

from medibot.rag.retrieval.query_bm25 import query_sparse_vector
from medibot.rag.retrieval.query_embeddings import embed_query
from medibot.rag.shared.bm25_common import BM25Stats
from medibot.rag.shared.qdrant_common import COLLECTION_NAME, rbac_filter


def hybrid_search(
    client: QdrantClient,
    query: str,
    role: str,
    embedder,
    stats: BM25Stats,
    top_k: int = 5,
    prefetch_k: int = 10,
) -> list[dict]:
    """Retrieve dense+sparse results fused by Qdrant reciprocal rank fusion."""
    dense_vector = embed_query(embedder, query)
    sparse = query_sparse_vector(query, stats)
    role_filter = rbac_filter(role)

    results = client.query_points(
        collection_name=COLLECTION_NAME,
        prefetch=[
            Prefetch(
                query=dense_vector,
                using="dense",
                filter=role_filter,
                limit=prefetch_k,
            ),
            Prefetch(
                query=SparseVector(
                    indices=sparse["indices"], values=sparse["values"]
                ),
                using="sparse",
                filter=role_filter,
                limit=prefetch_k,
            ),
        ],
        query=FusionQuery(fusion=Fusion.RRF),
        limit=top_k,
    ).points

    return [
        {
            "score": result.score,
            "source_document": result.payload["source_document"],
            "collection": result.payload["collection"],
            "section_title": result.payload["section_title"],
            "text_preview": result.payload["text"][:100],
        }
        for result in results
    ]


def hybrid_search_full(
    client: QdrantClient,
    query: str,
    role: str,
    embedder,
    stats: BM25Stats,
    top_k: int = 10,
):
    """Retrieve full dense+sparse payloads for reranking and prompting."""
    dense_vector = embed_query(embedder, query)
    sparse = query_sparse_vector(query, stats)
    role_filter = rbac_filter(role)

    return client.query_points(
        collection_name=COLLECTION_NAME,
        prefetch=[
            Prefetch(
                query=dense_vector,
                using="dense",
                filter=role_filter,
                limit=top_k,
            ),
            Prefetch(
                query=SparseVector(
                    indices=sparse["indices"], values=sparse["values"]
                ),
                using="sparse",
                filter=role_filter,
                limit=top_k,
            ),
        ],
        query=FusionQuery(fusion=Fusion.RRF),
        limit=top_k,
    ).points


def scored_points_to_dicts(points: list) -> list[dict]:
    """Convert Qdrant scored points to the reranker candidate shape."""
    return [
        {
            "chunk_id": point.payload.get("chunk_id"),
            "score": point.score,
            "source_document": point.payload.get("source_document"),
            "collection": point.payload.get("collection"),
            "section_title": point.payload.get("section_title"),
            "text": point.payload.get("text"),
            "metadata": point.payload,
        }
        for point in points
    ]


def dense_only_search(
    client: QdrantClient,
    query: str,
    role: str,
    embedder,
    top_k: int = 5,
) -> list[dict]:
    """Retrieve dense-only results for comparison and validation."""
    dense_vector = embed_query(embedder, query)
    results = client.query_points(
        collection_name=COLLECTION_NAME,
        query=dense_vector,
        using="dense",
        query_filter=rbac_filter(role),
        limit=top_k,
    ).points
    return [
        {
            "score": result.score,
            "source_document": result.payload["source_document"],
            "collection": result.payload["collection"],
            "section_title": result.payload["section_title"],
            "text_preview": result.payload["text"][:100],
        }
        for result in results
    ]
