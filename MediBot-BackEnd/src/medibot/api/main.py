"""
MediBot API entry point: src/medibot/api/main.py.

Wires together:
    - medibot.core.auth -> /login and JWT verification for protected routes
    - medibot.rag.retrieval.qdrant_search -> RBAC-filtered document retrieval
    - medibot.rag.retrieval.reranker -> narrows top-10 candidates to top-3
    - medibot.rag.retrieval.sql_rag -> SQL RAG and billing/admin access control

Startup loads the embedding model, BM25 stats, Qdrant client, reranker
model, and Groq LLM client ONCE (in `lifespan`), not per-request -- these
are all expensive to load and safe to share across requests.
"""

import logging
from contextlib import asynccontextmanager
from typing import Literal

from dotenv import load_dotenv
load_dotenv()

from fastapi import FastAPI, Depends, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import OAuth2PasswordRequestForm
from pydantic import BaseModel

from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import StrOutputParser

from medibot.core.auth import authenticate_user, create_access_token, get_current_user, TokenData
from medibot.rag.shared.embeddings import get_embedder
from medibot.rag.shared.bm25_common import BM25Stats
from medibot.rag.retrieval.qdrant_search import hybrid_search_full
from medibot.rag.shared.qdrant_common import get_client
from medibot.rag.retrieval.reranker import get_reranker, qdrant_hits_to_candidates, rerank_chunks
from medibot.rag.retrieval.sql_rag import (
    sql_rag_chain, check_billing_access, AccessDeniedError, get_llm,
)
from medibot.core.access import COLLECTION_ACCESS_ROLES
from medibot.core.config import BM25_STATS_PATH, CORS_ORIGINS, EMBEDDER_OFFLINE

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("medibot.api.main")

def get_accessible_collections(role: str) -> list[str]:
    return sorted(c for c, roles in COLLECTION_ACCESS_ROLES.items() if role in roles)


# --------------------------------------------------------------------------
# Startup / shutdown: load everything expensive exactly once
# --------------------------------------------------------------------------
@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Loading Qdrant client, embedder, BM25 stats, reranker, and LLM...")
    app.state.qdrant_client = get_client()
    app.state.embedder = get_embedder(offline=EMBEDDER_OFFLINE)
    with open(BM25_STATS_PATH) as f:
        app.state.bm25_stats = BM25Stats.from_json(f.read())
    get_reranker()  # warms the cross-encoder model cache
    get_llm()        # warms the Groq client used by both routing and SQL RAG
    logger.info(f"Startup complete. EMBEDDER_OFFLINE={EMBEDDER_OFFLINE}")
    yield
    logger.info("Shutting down.")


app = FastAPI(title="MediBot API", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# --------------------------------------------------------------------------
# Question router: analytical/numbers question -> SQL RAG, else -> Hybrid RAG
# --------------------------------------------------------------------------
ROUTER_PROMPT = ChatPromptTemplate.from_messages([
    ("system",
     "You classify hospital-staff questions into exactly one category.\n\n"
     "Reply with ONLY the single word SQL or DOCUMENT -- nothing else.\n\n"
     "SQL: the question asks for counts, totals, averages, statuses, dates, "
     "amounts, or other structured data lookups from operational/billing "
     "records (e.g. 'how many claims were escalated last month', "
     "'what is the status of invoice INV-2044', 'average pump downtime this quarter').\n\n"
     "DOCUMENT: the question asks about policies, procedures, protocols, "
     "dosages, guidelines, definitions, or how-to instructions found in "
     "written documents (e.g. 'what is the hand hygiene protocol', "
     "'how do I calibrate the infusion pump', 'how many days of annual leave do staff get' "
     "-- note: this last example is DOCUMENT, not SQL, because it's a policy lookup, "
     "not a query against live operational records).\n\n"
     "When genuinely uncertain, prefer DOCUMENT."),
    ("human", "{question}"),
])


def classify_question(question: str) -> Literal["SQL", "DOCUMENT"]:
    chain = ROUTER_PROMPT | get_llm() | StrOutputParser()
    raw = chain.invoke({"question": question}).strip().upper()
    return "SQL" if "SQL" in raw else "DOCUMENT"


# --------------------------------------------------------------------------
# Hybrid RAG answer generation (post-rerank)
# --------------------------------------------------------------------------
HYBRID_ANSWER_PROMPT = ChatPromptTemplate.from_messages([
    ("system",
     "You are MediBot, a hospital knowledge assistant. Answer the question "
     "using ONLY the context chunks below -- never invent facts.\n\n"
     "If the context does not contain enough information to answer, say so "
     "plainly and suggest the user may need a different role's document "
     "access, or should ask someone with that access. Do not guess.\n\n"
     "Context:\n{context}"),
    ("human", "{question}"),
])


def generate_hybrid_answer(question: str, ranked_chunks) -> str:
    if not ranked_chunks:
        context = "(no relevant context found in the documents you have access to)"
    else:
        context = "\n\n---\n\n".join(
            f"[{r.metadata['source_document']} > {r.metadata['section_title']}]\n{r.text}"
            for r in ranked_chunks
        )
    chain = HYBRID_ANSWER_PROMPT | get_llm() | StrOutputParser()
    return chain.invoke({"question": question, "context": context}).strip()


# --------------------------------------------------------------------------
# Schemas
# --------------------------------------------------------------------------
class ChatRequest(BaseModel):
    question: str


class SourceItem(BaseModel):
    source_document: str
    section_title: str
    collection: str


class ChatResponse(BaseModel):
    answer: str
    sources: list[SourceItem]
    retrieval_type: Literal["hybrid_rag", "sql_rag"]
    role: str


class LoginResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    role: str


# --------------------------------------------------------------------------
# Routes
# --------------------------------------------------------------------------
@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/login", response_model=LoginResponse)
def login(form_data: OAuth2PasswordRequestForm = Depends()):
    user = authenticate_user(form_data.username, form_data.password)
    if user is None:
        raise HTTPException(status_code=401, detail="Incorrect username or password")
    token = create_access_token(username=user["username"], role=user["role"])
    return LoginResponse(access_token=token, role=user["role"])


@app.get("/collections/{role}")
def collections_for_role(role: str, current_user: TokenData = Depends(get_current_user)):
    if role not in ALL_KNOWN_ROLES:
        raise HTTPException(status_code=404, detail=f"Unknown role '{role}'")
    return {"role": role, "collections": get_accessible_collections(role)}


ALL_KNOWN_ROLES = {"doctor", "nurse", "billing_executive", "technician", "admin"}


@app.post("/chat", response_model=ChatResponse)
def chat(req: ChatRequest, current_user: TokenData = Depends(get_current_user)):
    role = current_user.role
    question = req.question.strip()
    if not question:
        raise HTTPException(status_code=400, detail="question must not be empty")

    category = classify_question(question)
    logger.info(f"Routed question ({role}): {category!r} <- {question!r}")

    if category == "SQL":
        try:
            check_billing_access(role)
        except AccessDeniedError as e:
            return ChatResponse(
                answer=(
                    f"As a {role}, you do not have access to operational/billing data queries. "
                    f"SQL-based analytics are only available to billing_executive and admin roles."
                ),
                sources=[],
                retrieval_type="sql_rag",
                role=role,
            )
        answer = sql_rag_chain(question)
        return ChatResponse(answer=answer, sources=[], retrieval_type="sql_rag", role=role)

    # DOCUMENT path: Hybrid Retrieval (RBAC-filtered, top-10) -> Rerank (top-3) -> LLM
    raw_hits = hybrid_search_full(
        app.state.qdrant_client, question, role=role,
        embedder=app.state.embedder, stats=app.state.bm25_stats, top_k=10,
    )
    candidates = qdrant_hits_to_candidates(raw_hits)
    ranked = rerank_chunks(question, candidates, top_k=3)

    answer = generate_hybrid_answer(question, ranked)
    sources = [
        SourceItem(
            source_document=r.metadata["source_document"],
            section_title=r.metadata["section_title"],
            collection=r.metadata["collection"],
        )
        for r in ranked
    ]
    return ChatResponse(answer=answer, sources=sources, retrieval_type="hybrid_rag", role=role)
