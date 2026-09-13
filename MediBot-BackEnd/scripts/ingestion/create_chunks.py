"""
Document chunking entry point: scripts/ingestion/create_chunks.py.

This is the command-line entry point for the Docling + hierarchical chunking
ingestion workflow.

Given a folder of source documents organized by collection, this:
  1. Parses each file with Docling (structure-aware: headings, tables, code preserved)
  2. Chunks it hierarchically (HybridChunker: structure-first, then token-aware)
  3. Attaches the full required metadata schema to every chunk
  4. Returns/saves chunk dicts ready to be embedded and upserted into Qdrant

FIRST RUN NOTE: Docling will download layout + table-structure models from
HuggingFace the first time you run this. This is expected and matches the
assignment's own tip: "Run your ingestion pipeline once in a standalone
script before your demo." Subsequent runs use the cached models and are fast.

Usage:
    python -m scripts.ingestion.create_chunks                  # ingests everything under raw_data/mediassist_data/
    python -m scripts.ingestion.create_chunks --data-dir DIR   # ingests everything under DIR instead
"""

import argparse
import json
from pathlib import Path

from docling.document_converter import DocumentConverter
from docling_core.transforms.chunker.hybrid_chunker import HybridChunker
from docling_core.transforms.chunker.tokenizer.base import BaseTokenizer
from docling_core.transforms.chunker.tokenizer.huggingface import HuggingFaceTokenizer
from docling_core.types.doc.labels import DocItemLabel

from medibot.core.access import COLLECTION_ACCESS_ROLES
from medibot.core.config import CHUNKS_PATH, SOURCE_DATA_DIR


# Match this to whatever embedding model you plan to use for the dense
# vectors in Qdrant (Component 2) — the chunker's token limit must reflect
# what your actual embedder accepts.
EMBEDDING_MODEL_NAME = "sentence-transformers/all-MiniLM-L6-v2"
MAX_TOKENS = 256

SUPPORTED_EXTENSIONS = {".pdf", ".md"}

# Map Docling's internal item labels to the assignment's required chunk_type values
_LABEL_TO_CHUNK_TYPE = {
    DocItemLabel.TABLE: "table",
    DocItemLabel.SECTION_HEADER: "heading",
    DocItemLabel.TITLE: "heading",
    DocItemLabel.CODE: "code",
}


def _infer_chunk_type(chunk) -> str:
    """Look at what kind of Docling items make up this chunk to assign chunk_type."""
    labels = {getattr(item, "label", None) for item in chunk.meta.doc_items}
    for label, chunk_type in _LABEL_TO_CHUNK_TYPE.items():
        if label in labels:
            return chunk_type
    return "text"


class _OfflineWordTokenizer(BaseTokenizer):
    """Word-count stand-in for testing without network/model-download access.
    Do NOT use this for your real embeddings — token counts won't match your
    actual embedding model, so chunk sizing will be off. Use --offline only
    to sanity-check the pipeline before you have internet access set up."""
    max_tokens: int = MAX_TOKENS

    def count_tokens(self, text: str) -> int:
        return len(text.split())

    def get_max_tokens(self) -> int:
        return self.max_tokens

    def get_tokenizer(self):
        return None


def _build_chunker(offline: bool = False) -> HybridChunker:
    if offline:
        tokenizer = _OfflineWordTokenizer(max_tokens=MAX_TOKENS)
    else:
        from transformers import AutoTokenizer
        tokenizer = HuggingFaceTokenizer(
            tokenizer=AutoTokenizer.from_pretrained(EMBEDDING_MODEL_NAME),
            max_tokens=MAX_TOKENS,
        )
    return HybridChunker(tokenizer=tokenizer)


def ingest_document(file_path: str, collection: str, chunker: HybridChunker) -> list[dict]:
    """Parse + chunk a single document, returning Qdrant-ready chunk dicts."""
    if collection not in COLLECTION_ACCESS_ROLES:
        raise ValueError(f"Unknown collection: {collection}")

    source_document = Path(file_path).name
    access_roles = COLLECTION_ACCESS_ROLES[collection]

    converter = DocumentConverter()
    result = converter.convert(file_path)
    doc = result.document

    chunks = list(chunker.chunk(dl_doc=doc))

    records = []
    for i, chunk in enumerate(chunks):
        records.append({
            "chunk_id": f"{source_document}::chunk_{i}",
            "text": chunker.contextualize(chunk=chunk),  # heading-context-injected text to embed
            "metadata": {
                "source_document": source_document,
                "collection": collection,
                "access_roles": access_roles,
                "section_title": " > ".join(chunk.meta.headings) if chunk.meta.headings else None,
                "chunk_type": _infer_chunk_type(chunk),
            },
        })
    return records


def ingest_collection(folder_path: Path, collection: str, chunker: HybridChunker) -> list[dict]:
    """Ingest every supported file in a single collection's folder."""
    records = []
    if not folder_path.exists():
        return records
    for file_path in sorted(folder_path.iterdir()):
        if file_path.suffix.lower() not in SUPPORTED_EXTENSIONS:
            continue
        try:
            records.extend(ingest_document(str(file_path), collection, chunker))
        except Exception as e:
            print(f"  [FAILED] {file_path.name}: {e}")
    return records


def ingest_all(data_dir: str, offline: bool = False) -> list[dict]:
    """Walk data_dir/<collection>/ subfolders and ingest everything."""
    data_path = Path(data_dir)
    chunker = _build_chunker(offline=offline)
    all_records = []

    for collection in COLLECTION_ACCESS_ROLES:
        folder = data_path / collection
        print(f"Ingesting collection '{collection}' from {folder} ...")
        records = ingest_collection(folder, collection, chunker)
        print(f"  -> {len(records)} chunks")
        all_records.extend(records)

    return all_records


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--data-dir", default=str(SOURCE_DATA_DIR), help="Root folder with one subfolder per collection")
    parser.add_argument("--out", default=str(CHUNKS_PATH), help="Where to save the resulting chunk records")
    parser.add_argument("--offline", action="store_true", help="Use a word-count tokenizer instead of downloading a real one (testing only)")
    args = parser.parse_args()
    print(f"CHUNKS_PATH: {str(CHUNKS_PATH)} SOURCE_DATA_DIR {str(SOURCE_DATA_DIR)}")
    all_records = ingest_all(args.data_dir, offline=args.offline)

    print(f"DEBUG: Total records to write: {len(all_records)}")  # <- Add this
    print(f"DEBUG: Output path: {args.out}")                    # <- Add this
    with open(args.out, "w") as f:
        json.dump(all_records, f, indent=2)

    print(f"\nTotal chunks: {len(all_records)}")
    print(f"Saved to {args.out}")