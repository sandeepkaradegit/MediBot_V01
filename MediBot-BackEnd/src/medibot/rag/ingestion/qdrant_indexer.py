"""Qdrant document indexing: src/medibot/rag/ingestion/qdrant_indexer.py."""

import uuid

from qdrant_client import QdrantClient
from qdrant_client.models import PointStruct, SparseVector

from medibot.rag.ingestion.document_bm25 import (
    build_corpus_stats,
    document_sparse_vector,
)
from medibot.rag.ingestion.document_embeddings import embed_documents
from medibot.rag.shared.bm25_common import BM25Stats
from medibot.rag.shared.qdrant_common import COLLECTION_NAME


def _stable_point_id(chunk_id: str) -> str:
    return str(uuid.uuid5(uuid.NAMESPACE_URL, chunk_id))


def upsert_chunks_hybrid(
    client: QdrantClient, chunks: list[dict], embedder
) -> BM25Stats:
    """Build document vectors and upsert dense+sparse points into Qdrant."""
    texts = [chunk["text"] for chunk in chunks]
    stats = build_corpus_stats(texts)
    dense_vectors = embed_documents(embedder, texts)

    points = []
    for chunk, dense_vector, text in zip(chunks, dense_vectors, texts):
        sparse = document_sparse_vector(text, stats)
        payload = dict(chunk["metadata"])
        payload["chunk_id"] = chunk["chunk_id"]
        payload["text"] = text
        points.append(
            PointStruct(
                id=_stable_point_id(chunk["chunk_id"]),
                vector={
                    "dense": dense_vector,
                    "sparse": SparseVector(
                        indices=sparse["indices"], values=sparse["values"]
                    ),
                },
                payload=payload,
            )
        )

    client.upsert(collection_name=COLLECTION_NAME, points=points)
    return stats
