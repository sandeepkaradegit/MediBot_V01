"""
Hybrid retrieval validator: scripts/validation/validate_hybrid.py.

Validates the Qdrant HYBRID vector store (dense + BM25 sparse) before
moving on to Reranking. Checks, in order:

  1. Point count in Qdrant matches chunk count in chunks.json
  2. Every point's payload has all required fields, non-empty
  3. Every point has BOTH a correctly-sized dense vector AND a non-empty
     sparse vector
  4. Sparse vector term consistency: the number of terms stored in each
     point's sparse vector matches re-tokenizing its own payload text --
     catches a point whose sparse vector is stale relative to its text
  5. No duplicate chunk_ids
  6. Every point's access_roles matches what COLLECTION_ACCESS_ROLES
     expects for its collection
  7. RBAC search integrity -- run for BOTH dense_only_search AND
     hybrid_search_full (the actual production retrieval path used by
    medibot.api.main, via medibot.rag.retrieval.reranker), for every role, confirming neither
     retrieval path ever leaks a disallowed collection. hybrid_search_full
     is used here (not the short-preview hybrid_search) because that is
     what production actually calls -- a filter bug specific to that
     function's code path would otherwise go undetected.
  8. (Real embeddings only) Dense semantic sanity checks
  9. Keyword/BM25 sanity checks via hybrid_search (short-preview path) --
     these work regardless of --offline, since BM25 needs no model
     download at all. Kept on hybrid_search deliberately: this is the
     Topic 5 dense-vs-hybrid comparison demo, not a production-path check.

The collection access matrix is imported from medibot.core.access so ingestion,
the API, and validation use the same RBAC rules.

Usage:
    python -m scripts.validation.validate_hybrid
    python -m scripts.validation.validate_hybrid --offline
    python -m scripts.validation.validate_hybrid --chunks other.json
"""

import argparse
import json
from collections import defaultdict

from medibot.rag.shared.embeddings import get_embedder, VECTOR_SIZE
from medibot.rag.shared.bm25_common import BM25Stats, tokenize
from medibot.rag.retrieval.qdrant_search import (
    dense_only_search,
    hybrid_search,
    hybrid_search_full,
    scored_points_to_dicts,
)
from medibot.rag.shared.qdrant_common import COLLECTION_NAME, get_client
from medibot.core.access import ALL_ROLES, COLLECTION_ACCESS_ROLES
from medibot.core.config import BM25_STATS_PATH, CHUNKS_PATH

REQUIRED_PAYLOAD_FIELDS = ["chunk_id", "source_document", "collection", "access_roles", "section_title", "chunk_type", "text"]

SEMANTIC_SANITY_CASES = [
    ("What is the recommended amoxicillin dose for a small child?", "clinical"),
    ("How often should the infusion pump be calibrated?", "equipment"),
    ("What is the hand hygiene protocol in the ICU?", "nursing"),
    ("How are insurance claims escalated?", "billing"),
    ("How many days of paid annual leave do staff get?", "general"),
]

KEYWORD_SANITY_CASES = [
    ("24-gauge cannula for a paediatric patient under 5 kg", "icu_nursing_procedures.pdf"),
    ("DriveFlow IP-200 occlusion pressure alarm default 300 mmHg", "equipment_manual.pdf"),
    ("ICD-10 diagnosis codes and procedure codes insurer package rates", "billing_codes.pdf"),
]

def scroll_all_points(client):
    points = []
    offset = None
    while True:
        batch, offset = client.scroll(
            collection_name=COLLECTION_NAME, with_payload=True, with_vectors=True,
            limit=256, offset=offset,
        )
        points.extend(batch)
        if offset is None:
            break
    return points


def check_point_count(points, expected_count) -> list[str]:
    problems = []
    if len(points) != expected_count:
        problems.append(
            f"Point count mismatch: Qdrant has {len(points)} points, "
            f"chunks.json has {expected_count}."
        )
    return problems


def check_payload_completeness(points) -> list[str]:
    problems = []
    for p in points:
        payload = p.payload or {}
        for field in REQUIRED_PAYLOAD_FIELDS:
            if field not in payload or payload[field] in (None, "", []):
                problems.append(f"Point {p.id}: missing/empty payload field '{field}'")
    return problems


def check_vector_dimensions(points) -> list[str]:
    """Points carry NAMED vectors: {"dense": [...], "sparse": SparseVector(...)}."""
    problems = []
    for p in points:
        vectors = p.vector or {}
        dense = vectors.get("dense")
        sparse = vectors.get("sparse")

        if dense is None:
            problems.append(f"Point {p.id}: missing 'dense' vector")
        elif len(dense) != VECTOR_SIZE:
            problems.append(f"Point {p.id}: dense vector dimension {len(dense)}, expected {VECTOR_SIZE}")

        if sparse is None:
            problems.append(f"Point {p.id}: missing 'sparse' vector")
        elif not getattr(sparse, "indices", None):
            problems.append(f"Point {p.id}: sparse vector has zero terms")
    return problems


def check_sparse_term_consistency(points) -> list[str]:
    """Re-tokenize each point's own payload text and confirm the sparse
    vector's term count matches. A mismatch means the sparse vector is
    stale relative to the text it's supposed to represent -- e.g. text
    was edited/re-ingested without regenerating the sparse vector."""
    problems = []
    for p in points:
        payload = p.payload or {}
        text = payload.get("text", "")
        sparse = (p.vector or {}).get("sparse")
        if sparse is None or not text:
            continue  # already flagged by other checks
        expected_term_count = len(set(tokenize(text)))
        actual_term_count = len(sparse.indices)
        if actual_term_count != expected_term_count:
            problems.append(
                f"Point {p.id}: sparse vector has {actual_term_count} terms, "
                f"but re-tokenizing its payload text gives {expected_term_count} unique terms"
            )
    return problems


def check_duplicate_chunk_ids(points) -> list[str]:
    problems = []
    seen = defaultdict(int)
    for p in points:
        seen[(p.payload or {}).get("chunk_id")] += 1
    return [f"chunk_id '{cid}' appears on {n} points (should be 1)" for cid, n in seen.items() if n > 1]


def check_access_roles_consistency(points) -> list[str]:
    problems = []
    for p in points:
        payload = p.payload or {}
        collection = payload.get("collection")
        access_roles = payload.get("access_roles")
        if collection in COLLECTION_ACCESS_ROLES and access_roles is not None:
            expected = set(COLLECTION_ACCESS_ROLES[collection])
            actual = set(access_roles)
            if actual != expected:
                problems.append(
                    f"Point {p.id} (collection={collection}): access_roles {sorted(actual)} "
                    f"!= expected {sorted(expected)}"
                )
    return problems


def check_rbac_search_integrity(client, embedder, stats) -> list[str]:
    """Runs for BOTH retrieval paths -- dense-only AND hybrid_search_full
    (the fused, full-payload path actually used in production by main.py
    via medibot.rag.retrieval.reranker) -- since a filter bug could exist in one path and
    not the other."""
    problems = []
    for role in ALL_ROLES:
        allowed = {c for c, roles in COLLECTION_ACCESS_ROLES.items() if role in roles}
        query = "general question about hospital procedures"

        dense_results = dense_only_search(client, query, role=role, embedder=embedder, top_k=100)
        leaked = {r["collection"] for r in dense_results} - allowed
        if leaked:
            problems.append(f"[dense_only_search] Role '{role}': leaked disallowed collections {leaked}")

        hybrid_full_raw = hybrid_search_full(client, query, role=role, embedder=embedder, stats=stats, top_k=100)
        hybrid_full_results = scored_points_to_dicts(hybrid_full_raw)
        leaked = {r["collection"] for r in hybrid_full_results} - allowed
        if leaked:
            problems.append(f"[hybrid_search_full] Role '{role}': leaked disallowed collections {leaked}")
    return problems


def run_semantic_sanity_checks(client, embedder, stats):
    print("Dense semantic sanity checks (informational):")
    for query, expected_collection in SEMANTIC_SANITY_CASES:
        results = dense_only_search(client, query=query, role="admin", embedder=embedder, top_k=1)
        if not results:
            print(f"  WARN: no results for \"{query}\"")
            continue
        top = results[0]
        status = "PASS" if top["collection"] == expected_collection else "WARN"
        print(
            f"  {status}: \"{query}\" -> '{top['collection']}' "
            f"(expected '{expected_collection}'), score={top['score']:.3f}"
        )
    print()


def run_keyword_sanity_checks(client, embedder, stats):
    print("Keyword/BM25 sanity checks via hybrid_search (informational, no network needed):")
    for query, expected_document in KEYWORD_SANITY_CASES:
        results = hybrid_search(
            client, query=query, role="admin", embedder=embedder, stats=stats, top_k=5
        )
        rank = next(
            (index + 1 for index, result in enumerate(results)
             if result["source_document"] == expected_document),
            None,
        )
        status = "PASS" if rank == 1 else ("WARN" if rank else "FAIL")
        print(f"  {status}: \"{query}\" -> expected '{expected_document}' at rank {rank or 'not found'}")
    print()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--chunks", default=str(CHUNKS_PATH))
    parser.add_argument("--offline", action="store_true")
    args = parser.parse_args()

    with open(args.chunks) as f:
        expected_chunks = json.load(f)
    with open(BM25_STATS_PATH) as f:
        stats = BM25Stats.from_json(f.read())

    client = get_client()
    points = scroll_all_points(client)
    print(f"Found {len(points)} points in Qdrant collection '{COLLECTION_NAME}'")
    print(f"Expected {len(expected_chunks)} chunks from {args.chunks}\n")

    embedder = get_embedder(offline=args.offline)

    all_problems = []
    all_problems += check_point_count(points, len(expected_chunks))
    all_problems += check_payload_completeness(points)
    all_problems += check_vector_dimensions(points)
    all_problems += check_sparse_term_consistency(points)
    all_problems += check_duplicate_chunk_ids(points)
    all_problems += check_access_roles_consistency(points)
    all_problems += check_rbac_search_integrity(client, embedder, stats)

    print("=" * 70)
    print("STRUCTURAL + RBAC CHECKS (dense AND sparse)")
    print("=" * 70)
    if all_problems:
        print(f"{len(all_problems)} PROBLEM(S) FOUND:\n")
        for p in all_problems:
            print(f"  - {p}")
    else:
        print("All structural and RBAC integrity checks passed (dense + sparse, both search paths).")
    print()

    run_keyword_sanity_checks(client, embedder, stats)  # BM25 -- works offline too

    if not args.offline:
        run_semantic_sanity_checks(client, embedder, stats)
    else:
        print("Skipping dense semantic sanity checks (--offline mode).")


if __name__ == "__main__":
    main()
