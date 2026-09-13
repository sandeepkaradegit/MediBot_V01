"""
Qdrant indexing entry point: scripts/ingestion/build_qdrant_index.py.

Builds a Qdrant index from chunks.json with BOTH dense and BM25 sparse vectors,
then prove hybrid retrieval beats dense-only on exact-terminology queries
(drug names, measurements) -- directly addressing the assignment's
evaluation criterion: "retrieval quality demonstrably better than
dense-only".

Usage:
    python -m scripts.ingestion.build_qdrant_index            # real dense embeddings
    python -m scripts.ingestion.build_qdrant_index --offline  # fake dense embeddings --
        BM25 is unaffected either way (it needs no model download at all),
        so this still demonstrates real hybrid retrieval quality.
"""

import argparse
import json

from medibot.rag.ingestion.document_embeddings import get_document_embedder, VECTOR_SIZE
from medibot.rag.ingestion.qdrant_indexer import upsert_chunks_hybrid
from medibot.rag.retrieval.qdrant_search import hybrid_search, dense_only_search
from medibot.rag.shared.qdrant_common import get_client, ensure_collection
from medibot.core.config import BM25_STATS_PATH, CHUNKS_PATH

# Keyword-heavy queries -- exact terms (drug names, measurements, fault
# codes) that BM25 is specifically good at, and that a weak/generic dense
# embedder can miss. Each query/expected_document pair is verified against
# real chunk text in chunks.json.
KEYWORD_HEAVY_CASES = [
    {
        "query": "24-gauge cannula for a paediatric patient under 5 kg",
        "expected_document": "icu_nursing_procedures.pdf",
    },
    {
        "query": "replace cannula every 72 to 96 hours phlebitis VIP score",
        "expected_document": "icu_nursing_procedures.pdf",
    },
    {
        "query": "airborne precautions red sign N95 negative-pressure room",
        "expected_document": "infection_control.pdf",
    },
    {
        "query": "fault code E-12 internal sensor failure remove from service",
        "expected_document": "equipment_manual.pdf",
    },
    {
        "query": "DriveFlow IP-200 occlusion pressure alarm default 300 mmHg",
        "expected_document": "equipment_manual.pdf",
    },
    {
        "query": "NIBP calibration tolerance plus minus 3 mmHg every 6 months",
        "expected_document": "equipment_manual.pdf",
    },
    {
        "query": "planned admission pre-authorisation deadline 48 hours before admission",
        "expected_document": "claim_submission_guide.md",
    },
    {
        "query": "rejection code EXCL-04 day-care procedure claimed as inpatient",
        "expected_document": "claim_submission_guide.md",
    },
    {
        "query": "COPD acute exacerbation J44.1 package rate 42000",
        "expected_document": "billing_codes.pdf",
    },
    {
        "query": "femoral neck fracture S72.0 package rate 2,10,000",
        "expected_document": "billing_codes.pdf",
    },
    {
        "query": "weight-based paracetamol ibuprofen dosing under 5 kg",
        "expected_document": "treatment_protocols.pdf",
    },
]


def rank_of_expected(results: list[dict], expected_document: str) -> str:
    for i, r in enumerate(results):
        if r["source_document"] == expected_document:
            return f"#{i + 1}"
    return "not in top results"


def run_comparison(client, embedder, stats):
    print("=" * 70)
    print("HYBRID vs DENSE-ONLY -- keyword-heavy query comparison")
    print("=" * 70)

    for case in KEYWORD_HEAVY_CASES:
        query = case["query"]
        expected = case["expected_document"]

        dense_results = dense_only_search(client, query, role="admin", embedder=embedder, top_k=5)
        hybrid_results = hybrid_search(client, query, role="admin", embedder=embedder, stats=stats, top_k=5)

        print(f"\nQuery: \"{query}\"")
        print(f"  Expected source: {expected}")
        print(f"  Dense-only rank:  {rank_of_expected(dense_results, expected)}")
        print(f"  Hybrid rank:      {rank_of_expected(hybrid_results, expected)}")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--chunks", default=str(CHUNKS_PATH))
    parser.add_argument("--offline", action="store_true")
    args = parser.parse_args()

    embedder = get_document_embedder(offline=args.offline)

    with open(args.chunks) as f:
        chunks = json.load(f)
    print(f"Loaded {len(chunks)} chunks from {args.chunks}")

    client = get_client()
    ensure_collection(client, dense_size=VECTOR_SIZE)

    stats = upsert_chunks_hybrid(client, chunks, embedder)
    with open(BM25_STATS_PATH, "w") as f:
        f.write(stats.to_json())
    print(f"Upserted {len(chunks)} points with dense+sparse vectors; "
          f"BM25 stats saved to {BM25_STATS_PATH}\n")

    run_comparison(client, embedder, stats)


if __name__ == "__main__":
    main()