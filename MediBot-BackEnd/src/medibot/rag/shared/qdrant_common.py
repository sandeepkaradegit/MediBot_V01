"""Shared Qdrant helpers: src/medibot/rag/shared/qdrant_common.py."""

from pathlib import Path

from qdrant_client import QdrantClient
from qdrant_client.models import (
    Distance,
    FieldCondition,
    Filter,
    MatchAny,
    PayloadSchemaType,
    SparseVectorParams,
    VectorParams,
)

from medibot.core.config import QDRANT_DB_PATH

COLLECTION_NAME = "medibot_hybrid"


def get_client(db_path: str | Path = QDRANT_DB_PATH) -> QdrantClient:
    return QdrantClient(path=str(db_path))


def ensure_collection(client: QdrantClient, dense_size: int) -> None:
    existing = [collection.name for collection in client.get_collections().collections]
    if COLLECTION_NAME not in existing:
        client.create_collection(
            collection_name=COLLECTION_NAME,
            vectors_config={
                "dense": VectorParams(size=dense_size, distance=Distance.COSINE)
            },
            sparse_vectors_config={"sparse": SparseVectorParams()},
        )
        client.create_payload_index(
            collection_name=COLLECTION_NAME,
            field_name="access_roles",
            field_schema=PayloadSchemaType.KEYWORD,
        )


def rbac_filter(role: str) -> Filter:
    return Filter(must=[FieldCondition(key="access_roles", match=MatchAny(any=[role]))])
