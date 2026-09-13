"""Document embedding workflow: src/medibot/rag/ingestion/document_embeddings.py."""

from medibot.rag.shared.embeddings import VECTOR_SIZE, get_embedder


def get_document_embedder(offline: bool = False):
    """Create the embedder used to encode document chunks."""
    return get_embedder(offline=offline)


def embed_documents(embedder, texts: list[str]) -> list[list[float]]:
    """Encode document texts for storage in the vector index."""
    return embedder.embed(texts)
