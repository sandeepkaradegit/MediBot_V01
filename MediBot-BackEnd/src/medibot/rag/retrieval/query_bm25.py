"""Query BM25 workflow: src/medibot/rag/retrieval/query_bm25.py."""

import math

from medibot.rag.shared.bm25_common import BM25Stats, term_index, tokenize


def query_sparse_vector(query: str, stats: BM25Stats) -> dict:
    """Build the query-side BM25 vector sent to Qdrant."""
    tokens = set(tokenize(query))
    indices, values = [], []
    for term in tokens:
        document_frequency = stats.doc_freq.get(term, 0)
        inverse_document_frequency = math.log(
            1 + (stats.num_docs - document_frequency + 0.5)
            / (document_frequency + 0.5)
        )
        if inverse_document_frequency <= 0:
            continue
        indices.append(term_index(term))
        values.append(inverse_document_frequency)
    return {"indices": indices, "values": values}