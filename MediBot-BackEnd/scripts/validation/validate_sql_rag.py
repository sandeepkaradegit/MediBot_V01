"""
SQL RAG validator: scripts/validation/validate_sql_rag.py.

Tests, in order:
  1. clean_sql() in isolation -- proves the cleaning step works on messy
     LLM output shapes without needing any API call.
  2. RBAC gate (check_billing_access) -- unauthorized roles must be denied.
  3. sql_rag_with_access_check() -- proves the gate blocks BEFORE any LLM
     call happens for an unauthorized role, and works end-to-end for
     authorized roles.
  4. sql_rag_chain() called directly with the exact required signature
     (question: str) -> str, no role param -- proves the pure 3-step
     pipeline works standalone, as it will when called from inside your
     FastAPI/Node.js layer after that layer's own role check passes.
"""

import logging
logging.basicConfig(level=logging.INFO, format="%(message)s")

from medibot.rag.retrieval.sql_rag import (
    clean_sql,
    check_billing_access,
    AccessDeniedError,
    sql_rag_chain,
    sql_rag_with_access_check,
)

print("=" * 70)
print("STEP 1: clean_sql() unit tests")
print("=" * 70)

test_cases = [
    ("```sql\nSELECT COUNT(*) FROM claims WHERE status = 'pending';\n```",
     "SELECT COUNT(*) FROM claims WHERE status = 'pending'"),
    ("Here is the query:\n```\nSELECT * FROM maintenance_tickets WHERE status='in_progress';\n```",
     "SELECT * FROM maintenance_tickets WHERE status='in_progress'"),
    ("SELECT department, COUNT(*) FROM claims GROUP BY department;",
     "SELECT department, COUNT(*) FROM claims GROUP BY department"),
]

all_passed = True
for raw, expected in test_cases:
    cleaned = clean_sql(raw)
    passed = cleaned == expected
    all_passed = all_passed and passed
    status = "PASS" if passed else "FAIL"
    print(f"[{status}] raw={raw[:50]!r}...")
    print(f"       cleaned={cleaned!r}")
    if not passed:
        print(f"       expected={expected!r}")

print(f"\nStep 1 result: {'ALL PASSED' if all_passed else 'SOME FAILED'}")

print("\n" + "=" * 70)
print("STEP 2: RBAC gate tests (check_billing_access)")
print("=" * 70)

for role in ["nurse", "doctor", "billing_executive", "admin"]:
    try:
        check_billing_access(role)
        print(f"  role={role:20s} -> ALLOWED")
    except AccessDeniedError as e:
        print(f"  role={role:20s} -> DENIED ({e})")

print("\n" + "=" * 70)
print("STEP 3: sql_rag_with_access_check() end-to-end")
print("=" * 70)

print("\n-- Unauthorized role (nurse) -- must be blocked BEFORE any LLM call --")
try:
    sql_rag_with_access_check("How many pending claims are there?", role="nurse")
    print("FAIL: expected AccessDeniedError")
except AccessDeniedError as e:
    print(f"PASS: correctly denied -- {e}")

print("\n-- billing_executive: claims question --")
answer = sql_rag_with_access_check(
    "How many claims are currently pending, and what is their total claimed amount?",
    role="billing_executive",
)
print(f"Answer: {answer}")

print("\n-- admin: maintenance question --")
answer = sql_rag_with_access_check(
    "How many maintenance tickets are still in_progress, grouped by category?",
    role="admin",
)
print(f"Answer: {answer}")

print("\n" + "=" * 70)
print("STEP 4: sql_rag_chain() called directly (required signature, no role param)")
print("=" * 70)

answer = sql_rag_chain("What is the average claimed amount across all departments?")
print(f"Answer: {answer}")

answer = sql_rag_chain("Which insurer has the highest total approved amount?")
print(f"\nAnswer: {answer}")

print("\n" + "=" * 70)
print("ALL STEPS COMPLETE")
print("=" * 70)
