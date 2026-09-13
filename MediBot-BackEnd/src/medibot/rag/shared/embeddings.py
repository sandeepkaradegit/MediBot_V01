"""
Shared embedding implementation: src/medibot/rag/shared/embeddings.py.

Real mode uses sentence-transformers (downloads the model from HuggingFace
on first run — same one-time-download pattern as Docling in Topic 2).

Offline mode uses a deterministic hash-based fake embedding so you can test
the Qdrant plumbing (storage, filtering, RBAC) without needing network
access or a real model. Offline embeddings carry NO real semantic meaning —
never use them for anything except pipeline testing.
"""

import hashlib
import struct

import os

EMBEDDING_MODEL_NAME = "sentence-transformers/all-MiniLM-L6-v2"
# If your network can't reach huggingface.co, download the model once on a
# machine that can (see README), copy the folder over, then set this env var
# to that folder's path -- SentenceTransformer loads a local folder exactly
# the same way it loads a hub name; nothing else in this file changes.
EMBEDDING_MODEL_PATH = os.environ.get("EMBEDDING_MODEL_PATH", EMBEDDING_MODEL_NAME)
VECTOR_SIZE = 384  # matches all-MiniLM-L6-v2's output dimension


class RealEmbedder:
    def __init__(self):
        from sentence_transformers import SentenceTransformer
        self.model = SentenceTransformer(EMBEDDING_MODEL_PATH)

    def embed(self, texts: list[str]) -> list[list[float]]:
        return self.model.encode(texts, normalize_embeddings=True).tolist()


class OfflineFakeEmbedder:
    """Deterministic, hash-based pseudo-embedding. Same text -> same vector,
    similar text -> NOT reliably similar vectors (unlike a real embedder).
    Only good for testing that storage/filtering code runs correctly."""

    def embed(self, texts: list[str]) -> list[list[float]]:
        return [self._embed_one(t) for t in texts]

    def _embed_one(self, text: str) -> list[float]:
        vector = []
        seed = text.encode("utf-8")
        i = 0
        while len(vector) < VECTOR_SIZE:
            digest = hashlib.sha256(seed + str(i).encode()).digest()
            # unpack 8 floats (4 bytes each doesn't fit; use 4-byte chunks as uint32 -> normalize)
            for j in range(0, len(digest) - 3, 4):
                val = struct.unpack("I", digest[j:j + 4])[0]
                vector.append((val % 2000 - 1000) / 1000.0)  # roughly [-1, 1]
                if len(vector) >= VECTOR_SIZE:
                    break
            i += 1
        return vector


def get_embedder(offline: bool = False):
    return OfflineFakeEmbedder() if offline else RealEmbedder()