"""Query embedding workflow: src/medibot/rag/retrieval/query_embeddings.py."""


def embed_query(embedder, query: str) -> list[float]:
    """Encode one user query using the shared embedding model."""
    return embedder.embed([query])[0]
