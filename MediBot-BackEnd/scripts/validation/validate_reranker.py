"""
Reranker validator: scripts/validation/validate_reranker.py.

Proves the reranker itself works correctly, independent of retrieval
quality — feeds a fixed, hand-ordered candidate list (simulating a
plausible but WRONG hybrid-fusion order) and checks that the
cross-encoder promotes the truly relevant chunk to rank 0.

No Qdrant / BM25 / embedding dependency; isolates
medibot.rag.retrieval.reranker.
"""

import logging

# Without this, reranker's logger.info() calls (rank-shift logging)
# produce no output at all — no handler is attached by default.
logging.basicConfig(level=logging.INFO, format="%(message)s")

from medibot.rag.retrieval.reranker import rerank_chunks

query = "what gauge cannula should I use for a paediatric patient under 5 kg?"

# Deliberately "wrong" order: a keyword-adjacent but off-topic chunk first
# (dosing table shares "paediatric"/"5 kg" vocabulary), an NGT-sizing chunk
# second (shares "sizing"/"paediatric"), and the ACTUAL correct answer
# (cannula gauge table) pushed to last place — simulating a real
# hybrid-fusion misordering that reranking should fix.
candidates = [
    {
        "chunk_id": "treatment_protocols.pdf::chunk_22",
        "text": "Weight-based dosing\n< 5 kg, Paracetamol (oral) = 60 mg Q6H. "
                "< 5 kg, Ibuprofen (oral) = Not recommended. < 5 kg, IV Paracetamol = 7.5 mg/kg Q6H.",
        "metadata": {
            "source_document": "treatment_protocols.pdf",
            "section_title": "Weight-based dosing",
            "collection": "clinical",
            "access_roles": ["doctor", "admin"],
            "chunk_type": "table",
        },
        "score": 0.91,  # highest fused score — but wrong chunk for this query
    },
    {
        "chunk_id": "icu_nursing_procedures.pdf::chunk_9",
        "text": "Sizing\nAdult: 14-16 Fr. Paediatric: select by age-appropriate formula.",
        "metadata": {
            "source_document": "icu_nursing_procedures.pdf",
            "section_title": "Sizing",
            "collection": "nursing",
            "access_roles": ["nurse", "doctor", "admin"],
            "chunk_type": "text",
        },
        "score": 0.85,  # sounds related but this is NGT tube sizing, not cannula
    },
    {
        "chunk_id": "icu_nursing_procedures.pdf::chunk_14",
        "text": "Cannula sizing by indication\nBlood transfusion, Recommended Gauge = >= 18G. "
                "Rapid fluid resuscitation, Recommended Gauge = >= 16G. Routine medication, Recommended Gauge = 20-22G. "
                "Paediatric < 5 kg, Recommended Gauge = 24G. Paediatric 5-20 kg, Recommended Gauge = 22G. "
                "Paediatric > 20 kg, Recommended Gauge = 20G",
        "metadata": {
            "source_document": "icu_nursing_procedures.pdf",
            "section_title": "Cannula sizing by indication",
            "collection": "nursing",
            "access_roles": ["nurse", "doctor", "admin"],
            "chunk_type": "table",
        },
        "score": 0.79,  # lowest fused score — but this is THE correct answer
    },
]

print("=" * 70)
print(f"Query: {query!r}")
print("=" * 70)

print("\nBEFORE (hybrid fusion order):")
for i, c in enumerate(candidates):
    print(f"  #{i}  score={c['score']:.2f}  [{c['chunk_id']}]  {c['metadata']['section_title']}")

print("\n--- reranker log output ---")
top_chunks = rerank_chunks(query=query, candidates=candidates, top_k=3)
print("--- end log output ---\n")

print("AFTER (cross-encoder rerank order):")
for c in top_chunks:
    shift = c.initial_rank - c.final_rank
    arrow = "up" if shift > 0 else ("down" if shift < 0 else "=")
    print(f"  #{c.final_rank}  rerank_score={c.rerank_score:.4f}  "
          f"(was #{c.initial_rank}, {arrow} {abs(shift)})  [{c.chunk_id}]  {c.metadata['section_title']}")

# Assertion: the correct cannula-sizing chunk should now outrank the
# dosing table and the NGT-sizing chunk, despite starting last.
assert top_chunks[0].chunk_id == "icu_nursing_procedures.pdf::chunk_14", \
    f"Reranker failed to promote the correct chunk to rank 0 (got {top_chunks[0].chunk_id} instead)"
print("\nPASSED: correct chunk promoted from rank 2 -> rank 0")
