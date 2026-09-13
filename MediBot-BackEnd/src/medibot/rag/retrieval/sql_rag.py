"""
SQL RAG retrieval workflow: src/medibot/rag/retrieval/sql_rag.py.

Translates a natural-language question into SQL (via Groq LLM), cleans the
raw LLM output down to a single executable SQL statement, runs it against
mediassist.db, and asks the LLM to turn the raw result into a natural-
language answer.

sql_rag_chain(question: str) -> str matches the assignment's required
signature exactly -- it does NOT take a role parameter. Access control is
handled by a separate wrapper (sql_rag_with_access_check) that the calling
layer (FastAPI endpoint, Node.js API route, agentic router) uses instead.
This mirrors how it will actually be wired in production: the endpoint
already knows the authenticated user's role from the JWT/session, and
decides whether to call sql_rag_chain at all -- the chain itself stays a
pure, role-agnostic function.

Access to the WRAPPER is restricted to billing_executive and admin roles.
This is a SEPARATE gate from the Qdrant metadata RBAC filter used in
Component 2 (hybrid_search_full); it protects the SQL database, not the
vector store.
"""

import re
import sqlite3
import logging

from dotenv import load_dotenv
load_dotenv()

from langchain_groq import ChatGroq
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import StrOutputParser

from medibot.core.config import GROQ_MODEL, SQLITE_DB_PATH

logger = logging.getLogger("medibot.sql_rag")

ALLOWED_ROLES = {"billing_executive", "admin"}
DB_PATH = SQLITE_DB_PATH

_llm = None


def get_llm():
    """Lazy-load the Groq LLM client once and reuse it across calls."""
    global _llm
    if _llm is None:
        _llm = ChatGroq(model=GROQ_MODEL, temperature=0)
    return _llm


class AccessDeniedError(Exception):
    """Raised when a role without SQL RAG access attempts to use it."""


def check_billing_access(role: str) -> None:
    """
    Second RBAC gate -- protects the SQL database itself, independent of
    the vector-store metadata filtering used in hybrid_search_full().
    Call this (via sql_rag_with_access_check) BEFORE sql_rag_chain, so
    unauthorized roles never trigger an LLM call or a DB query.
    """
    if role not in ALLOWED_ROLES:
        raise AccessDeniedError(
            f"Role '{role}' is not permitted to query billing/maintenance records. "
            f"Allowed roles: {sorted(ALLOWED_ROLES)}"
        )


def get_schema_description() -> str:
    """
    Introspects mediassist.db live via PRAGMA table_info() so the prompt
    always reflects the real schema -- column names are never hardcoded.
    """
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
    tables = [row[0] for row in cursor.fetchall()]

    lines = []
    for table in tables:
        cursor.execute(f"PRAGMA table_info({table});")
        cols = cursor.fetchall()
        col_desc = ", ".join(f"{c[1]} {c[2]}" for c in cols)
        lines.append(f"Table {table}({col_desc})")

        cursor.execute(f"SELECT * FROM {table} LIMIT 2;")
        sample = cursor.fetchall()
        if sample:
            lines.append(f"  Sample rows: {sample}")

    conn.close()
    return "\n".join(lines)


SQL_GEN_PROMPT = ChatPromptTemplate.from_messages([
    ("system",
     "You are a SQLite expert. Given the schema below, write ONE syntactically "
     "correct SQLite SELECT query that answers the user's question.\n\n"
     "Schema:\n{schema}\n\n"
     "Rules:\n"
     "- Output ONLY the SQL statement, nothing else -- no markdown fences, "
     "no explanation, no comments.\n"
     "- Only generate SELECT statements. Never generate INSERT, UPDATE, "
     "DELETE, DROP, ALTER, or any other write/DDL statement.\n"
     "- Use only the tables and columns shown in the schema.\n"
     "- If the question cannot be answered with these tables, output: "
     "SELECT 'CANNOT_ANSWER' AS error;"),
    ("human", "{question}"),
])

ANSWER_PROMPT = ChatPromptTemplate.from_messages([
    ("system",
     "You are a helpful hospital operations assistant. Given the user's "
     "question, the SQL query that was run, and its result, answer the "
     "question in clear, natural language. Be concise and factual -- do "
     "not invent data beyond what's in the result. If the result is empty, "
     "say no matching records were found."),
    ("human",
     "Question: {question}\n\nSQL query: {sql}\n\nQuery result: {result}\n\n"
     "Answer:"),
])


def clean_sql(raw_output: str) -> str:
    """
    Step 2 of the pipeline: strips markdown code fences, leading/trailing
    explanation text, and trailing semicolons/whitespace from a raw LLM SQL
    response, leaving a single executable SQL statement.
    """
    text = raw_output.strip()

    # Strip ```sql ... ``` or ``` ... ``` fences
    fence_match = re.search(r"```(?:sql)?\s*(.*?)```", text, re.DOTALL | re.IGNORECASE)
    if fence_match:
        text = fence_match.group(1).strip()

    # Cut to the first SELECT keyword in case of leading prose
    select_match = re.search(r"\bSELECT\b", text, re.IGNORECASE)
    if select_match:
        text = text[select_match.start():]

    # Drop trailing semicolon(s) and whitespace
    text = text.strip().rstrip(";").strip()

    return text


def is_safe_select(sql: str) -> bool:
    """
    Guardrail: only allow single SELECT statements, block any write/DDL
    keywords even if the LLM ignored the prompt instruction.
    """
    lowered = sql.lower()
    if not lowered.startswith("select"):
        return False
    forbidden = ["insert", "update", "delete", "drop", "alter", "create",
                 "attach", "pragma", "--"]
    return not any(word in lowered for word in forbidden)


def execute_sql(sql: str):
    """Step 3a: executes the cleaned SQL against mediassist.db."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    try:
        cursor.execute(sql)
        rows = cursor.fetchall()
        columns = [desc[0] for desc in cursor.description] if cursor.description else []
        return columns, rows
    finally:
        conn.close()


def sql_rag_chain(question: str) -> str:
    """
    Required signature per assignment: sql_rag_chain(question: str) -> str.

    Three explicit steps:
      1. Translate the natural language question into SQL, using an LLM.
      2. Clean the raw LLM output to extract only the SQL statement.
      3. Execute the SQL against mediassist.db, then pass the result back
         to the LLM for a natural language answer.

    NOTE: this function does NOT check roles. Role-based access is enforced
    by the caller via sql_rag_with_access_check() below, or directly by the
    FastAPI/Node.js layer using check_billing_access() before invoking this.
    """
    llm = get_llm()
    schema = get_schema_description()

    # --- Step 1: NL -> SQL ---
    sql_chain = SQL_GEN_PROMPT | llm | StrOutputParser()
    raw_sql = sql_chain.invoke({"schema": schema, "question": question})
    logger.info(f"Raw LLM SQL output: {raw_sql!r}")

    # --- Step 2: clean raw LLM output ---
    sql = clean_sql(raw_sql)
    logger.info(f"Cleaned SQL: {sql!r}")

    if not is_safe_select(sql):
        return ("I couldn't safely translate that question into a query. "
                "Please rephrase it as a data lookup (e.g. counts, statuses, amounts).")

    # --- Step 3: execute, then LLM -> natural language ---
    try:
        columns, rows = execute_sql(sql)
    except sqlite3.Error as e:
        logger.error(f"SQL execution failed: {e}")
        return f"I generated a query but it failed to run against the database: {e}"

    result_str = f"columns={columns}, rows={rows}"

    answer_chain = ANSWER_PROMPT | llm | StrOutputParser()
    answer = answer_chain.invoke({"question": question, "sql": sql, "result": result_str})

    return answer.strip()


def sql_rag_with_access_check(question: str, role: str) -> str:
    """
    Convenience wrapper for callers that need BOTH the role check and the
    chain in one call (used by test scripts here; your FastAPI/Node.js
    endpoint will more likely call check_billing_access(role) itself right
    after reading the user's role from the JWT, then call sql_rag_chain(question)
    directly -- both patterns are supported.
    """
    check_billing_access(role)
    return sql_rag_chain(question)
