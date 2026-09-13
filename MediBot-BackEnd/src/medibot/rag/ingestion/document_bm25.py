"""Document BM25 workflow: src/medibot/rag/ingestion/document_bm25.py."""

from collections import Counter

from medibot.rag.shared.bm25_common import B, K1, BM25Stats, tokenize, term_index


def build_corpus_stats(texts: list[str]) -> BM25Stats:
    """Build BM25 statistics for the complete document corpus."""
    doc_freq = Counter()
    total_len = 0
    for text in texts:
        tokens = set(tokenize(text))
        for term in tokens:
            doc_freq[term] += 1
        total_len += len(tokenize(text))

    return BM25Stats(
        doc_freq=dict(doc_freq),
        num_docs=len(texts),
        avg_doc_len=(total_len / len(texts)) if texts else 0.0,
    )


def document_sparse_vector(text: str, stats: BM25Stats) -> dict:
    """Build the document-side BM25 vector stored in Qdrant."""
    tokens = tokenize(text)
    doc_len = len(tokens)
    term_frequencies = Counter(tokens)

    indices, values = [], []
    for term, frequency in term_frequencies.items():
        norm = 1 - B + B * (doc_len / stats.avg_doc_len if stats.avg_doc_len else 1)
        weight = (frequency * (K1 + 1)) / (frequency + K1 * norm)
        indices.append(term_index(term))
        values.append(weight)
    return {"indices": indices, "values": values}