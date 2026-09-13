"""
Shared BM25 primitives: src/medibot/rag/shared/bm25_common.py.

No network or model download
needed (unlike fastembed's 'Qdrant/bm25', which needs a HuggingFace
download for its vocabulary/stopword files -- the same network wall you
hit with sentence-transformers). This implements the standard Okapi BM25
formula directly.

The key trick: BM25's formula splits cleanly into a term-frequency part
and an inverse-document-frequency part. We bake the tf/length-normalization
part into each DOCUMENT's sparse vector at ingestion time, and the idf part
into the QUERY's sparse vector at search time. Their dot product then
equals the full BM25 score -- computed natively by Qdrant when both are
stored/queried as sparse vectors, with zero application-code merging.

Terms are mapped to fixed integer indices via a stable hash (not Python's
built-in hash(), which is randomized per-process) so the same word always
lands on the same index across ingestion and query time, without needing
to persist an explicit vocabulary file.
"""

import hashlib
import json
import re
from dataclasses import dataclass, asdict

K1 = 1.5   # term frequency saturation -- higher = tf matters more before saturating
B = 0.75   # length normalization strength -- 0 = no normalization, 1 = full
INDEX_SPACE = 2 ** 20  # hashing bucket count; large enough to keep collisions rare


def tokenize(text: str) -> list[str]:
    return re.findall(r"[a-z0-9]+", text.lower())


def term_index(term: str) -> int:
    """Stable hash -> fixed index, so 'amoxicillin' maps to the same
    dimension every time, across processes and across doc/query vectors."""
    digest = hashlib.md5(term.encode("utf-8")).digest()
    return int.from_bytes(digest[:4], "big") % INDEX_SPACE


@dataclass
class BM25Stats:
    doc_freq: dict          # term -> number of docs containing it
    num_docs: int
    avg_doc_len: float

    def to_json(self) -> str:
        return json.dumps(asdict(self))

    @staticmethod
    def from_json(s: str) -> "BM25Stats":
        d = json.loads(s)
        return BM25Stats(doc_freq=d["doc_freq"], num_docs=d["num_docs"], avg_doc_len=d["avg_doc_len"])

