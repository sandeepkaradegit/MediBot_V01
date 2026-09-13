"""
Chunk metadata validator: scripts/validation/validate_chunks.py.

Reads chunks.json (output of create_chunks.py) and reports:
  1. Chunk count per source document, and per collection
  2. Chunk_type breakdown per document
  3. Metadata completeness checks (missing/empty required fields)
  4. The actual role x collection access matrix, derived from the data,
     compared against the shared RBAC matrix from medibot.core.access

Run this after every ingestion run, before moving on to embedding/Qdrant —
catching a metadata bug here is much cheaper than catching it after you've
built RBAC filtering on top of bad data.

Usage:
    python -m scripts.validation.validate_chunks
    python -m scripts.validation.validate_chunks --chunks other.json
"""

import argparse
import json
from collections import defaultdict

from medibot.core.access import COLLECTION_ACCESS_ROLES
from medibot.core.config import CHUNKS_PATH

REQUIRED_METADATA_FIELDS = ["source_document", "collection", "access_roles", "section_title", "chunk_type"]
VALID_CHUNK_TYPES = {"text", "table", "heading", "code"}
ALL_ROLES = ["doctor", "nurse", "billing_executive", "technician", "admin"]
ALL_COLLECTIONS = list(COLLECTION_ACCESS_ROLES.keys())


def load_chunks(path: str) -> list[dict]:
    with open(path) as f:
        return json.load(f)


def check_metadata_completeness(chunks: list[dict]) -> list[str]:
    """Return a list of human-readable problems found, empty if clean."""
    problems = []
    for chunk in chunks:
        cid = chunk.get("chunk_id", "<missing chunk_id>")
        meta = chunk.get("metadata", {})

        for field in REQUIRED_METADATA_FIELDS:
            if field not in meta or meta[field] in (None, "", []):
                problems.append(f"{cid}: missing/empty required field '{field}'")

        collection = meta.get("collection")
        if collection is not None and collection not in COLLECTION_ACCESS_ROLES:
            problems.append(f"{cid}: unknown collection '{collection}'")

        chunk_type = meta.get("chunk_type")
        if chunk_type is not None and chunk_type not in VALID_CHUNK_TYPES:
            problems.append(f"{cid}: invalid chunk_type '{chunk_type}' (expected one of {VALID_CHUNK_TYPES})")

        access_roles = meta.get("access_roles")
        if collection in COLLECTION_ACCESS_ROLES and access_roles is not None:
            expected = set(COLLECTION_ACCESS_ROLES[collection])
            actual = set(access_roles)
            if actual != expected:
                problems.append(
                    f"{cid}: access_roles {sorted(actual)} does not match expected "
                    f"{sorted(expected)} for collection '{collection}'"
                )

        if not chunk.get("text", "").strip():
            problems.append(f"{cid}: empty embedded text")

    return problems


def summarize_per_document(chunks: list[dict]):
    """Chunk count + chunk_type breakdown per (collection, source_document)."""
    doc_counts = defaultdict(lambda: defaultdict(int))
    doc_collection = {}

    for chunk in chunks:
        meta = chunk.get("metadata", {})
        doc = meta.get("source_document", "<unknown>")
        collection = meta.get("collection", "<unknown>")
        chunk_type = meta.get("chunk_type", "<unknown>")
        doc_counts[doc][chunk_type] += 1
        doc_collection[doc] = collection

    print("Per-document chunk summary:")
    print(f"{'Document':<32} {'Collection':<12} {'Total':<7} {'text':<6} {'table':<7} {'heading':<9} {'code':<6}")
    for doc in sorted(doc_counts):
        counts = doc_counts[doc]
        total = sum(counts.values())
        print(
            f"{doc:<32} {doc_collection[doc]:<12} {total:<7} "
            f"{counts.get('text', 0):<6} {counts.get('table', 0):<7} "
            f"{counts.get('heading', 0):<9} {counts.get('code', 0):<6}"
        )
    print()


def summarize_per_collection(chunks: list[dict]):
    counts = defaultdict(int)
    for chunk in chunks:
        counts[chunk.get("metadata", {}).get("collection", "<unknown>")] += 1

    print("Per-collection chunk totals:")
    for collection in ALL_COLLECTIONS:
        print(f"  {collection:<12} {counts.get(collection, 0)} chunks")
    print()


def print_access_matrix(chunks: list[dict]):
    """Derive the actual role x collection access matrix from the data,
    and flag any cell that doesn't match what create_chunks.py's
    COLLECTION_ACCESS_ROLES expects."""
    actual = defaultdict(set)  # collection -> set of roles seen in the data
    for chunk in chunks:
        meta = chunk.get("metadata", {})
        collection = meta.get("collection")
        for role in meta.get("access_roles", []) or []:
            actual[collection].add(role)

    header = f"{'Role':<20}" + "".join(f"{c:<12}" for c in ALL_COLLECTIONS)
    print("Access matrix (from actual ingested data):")
    print(header)
    all_ok = True
    for role in ALL_ROLES:
        row = f"{role:<20}"
        for collection in ALL_COLLECTIONS:
            expected_has_role = role in COLLECTION_ACCESS_ROLES.get(collection, [])
            actual_has_role = role in actual.get(collection, set())
            if not actual.get(collection):
                # no chunks at all for this collection - can't confirm either way
                symbol = "?"
            elif expected_has_role == actual_has_role:
                symbol = "\u2705" if actual_has_role else "\u274c"
            else:
                symbol = "\u26a0"  # mismatch between expected and actual
                all_ok = False
            row += f"{symbol:<12}"
        print(row)
    print()
    if all_ok:
        print("Access matrix matches expectations (no \u26a0 mismatches).")
    else:
        print("MISMATCHES found (\u26a0) \u2014 check COLLECTION_ACCESS_ROLES vs actual chunk metadata above.")
    print("('?' means no chunks were found for that collection at all \u2014 ingest some documents first.)\n")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--chunks", default=str(CHUNKS_PATH))
    args = parser.parse_args()

    chunks = load_chunks(args.chunks)
    print(f"Loaded {len(chunks)} chunks from {args.chunks}\n")

    summarize_per_document(chunks)
    summarize_per_collection(chunks)
    print_access_matrix(chunks)

    problems = check_metadata_completeness(chunks)
    if problems:
        print(f"METADATA PROBLEMS FOUND ({len(problems)}):")
        for p in problems:
            print(f"  - {p}")
    else:
        print("No metadata problems found \u2014 all chunks have complete, consistent metadata.")


if __name__ == "__main__":
    main()