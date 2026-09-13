# MediBot

MediBot is a FastAPI hospital knowledge assistant. It combines JWT authentication, role-based access control (RBAC), hybrid document retrieval, cross-encoder reranking, and SQL RAG for operational and billing questions.

## Capabilities

- JWT login with bcrypt-hashed demo users.
- Role-filtered document retrieval using Qdrant.
- Hybrid search: dense sentence embeddings plus BM25 sparse vectors with reciprocal-rank fusion.
- Cross-encoder reranking of the best document candidates.
- Natural-language answers grounded in retrieved document chunks.
- SQL RAG for structured operational and billing lookups.
- Separate billing/admin access control for SQL queries.

## Refactoring Progress

Completed steps:

- Created the `src/medibot/` package with `__init__.py`.
- Moved the FastAPI entry point to `src/medibot/api/main.py` and added `src/medibot/api/__init__.py`.
- Moved authentication, configuration, and access rules to `src/medibot/core/`.
- Created the empty RAG subpackages: `shared/`, `ingestion/`, and `retrieval/`.
- Moved `sql_rag.py` and `reranker.py` into `src/medibot/rag/retrieval/`.
- Split Qdrant indexing and retrieval into shared, ingestion, and retrieval modules.
- Split embedding workflows: shared model logic, document embedding, and query embedding adapters.
- Split BM25 workflows: shared BM25 primitives, document sparse vectors, and query sparse vectors.

The active application and RAG modules now live under `src/medibot/`. The command-line entry points live under `scripts/`.

Current API package structure:

```text
src/
└── medibot/
    ├── __init__.py
    ├── api/
    │   ├── __init__.py
    │   └── main.py
    ├── core/
    │   ├── __init__.py
    │   ├── auth.py
    │   ├── config.py
    │   └── access.py
    └── rag/
        ├── __init__.py
        ├── shared/
        │   ├── __init__.py
        │   ├── embeddings.py
        │   ├── bm25_common.py
        │   └── qdrant_common.py
        ├── ingestion/
        │   ├── __init__.py
        │   ├── document_embeddings.py
        │   ├── document_bm25.py
        │   └── qdrant_indexer.py
        └── retrieval/
            ├── __init__.py
            ├── query_embeddings.py
            ├── query_bm25.py
            ├── qdrant_search.py
            ├── reranker.py
            └── sql_rag.py
```

Current command-script structure:

```text
scripts/
├── __init__.py
├── ingestion/
│   ├── __init__.py
│   ├── create_chunks.py
│   └── build_qdrant_index.py
├── validation/
│   ├── __init__.py
│   ├── validate_chunks.py
│   ├── validate_hybrid.py
│   ├── validate_reranker.py
│   ├── validate_sql_rag.py
│   └── validate_db_schema.py
└── auth/
    ├── __init__.py
    └── seed_users.py
```

Run these scripts as modules from the repository root. The `-m` form is intentional: it keeps the repository root and the installed `medibot` package on Python's import path, so scripts can use package imports consistently.

For example:

```powershell
uv run python -m scripts.ingestion.create_chunks
python -m scripts.ingestion.create_chunks
```

You can also run a script by its file path. Set `PYTHONPATH` to the repository root first so the installed project package resolves correctly:

```powershell
$env:PYTHONPATH = (Get-Location).Path
uv run python .\scripts\ingestion\create_chunks.py
python .\scripts\ingestion\create_chunks.py
```

For example, the Qdrant indexer can be started by file path as follows:

```powershell
$env:PYTHONPATH = (Get-Location).Path
uv run python .\scripts\ingestion\build_qdrant_index.py
python .\scripts\ingestion\build_qdrant_index.py
```

Run these commands from the repository root. Module execution with `-m` remains the preferred form because it handles the package import path without setting `PYTHONPATH` manually.

## Roles and Access

| Role | Document collections | SQL RAG |
| --- | --- | --- |
| `doctor` | `general`, `clinical`, `nursing` | No |
| `nurse` | `general`, `nursing` | No |
| `billing_executive` | `general`, `billing` | Yes |
| `technician` | `general`, `equipment` | No |
| `admin` | All collections | Yes |

The Qdrant filter applies `access_roles` metadata before results are returned. SQL RAG has an independent allow-list for `billing_executive` and `admin`.

## Architecture

```text
Source documents
    |  scripts/ingestion/create_chunks.py (Docling + HybridChunker)
    v
processed_data/chunks.json
    |  scripts/ingestion/build_qdrant_index.py
  |       -> shared/embeddings.py -> dense vectors (all-MiniLM-L6-v2)
    +--> BM25 sparse vectors + processed_data/bm25_stats.json
  |  rag/shared/qdrant_common.py -> named vectors + RBAC payload metadata
  v
Local Qdrant: processed_data/qdrant_hybrid_db/ (medibot_hybrid collection)

POST /chat
    |
    +--> Groq question router
  |       +--> SQL -> medibot.rag.retrieval.sql_rag -> access check -> SQLite -> Groq answer
  |       +--> DOCUMENT -> rag/retrieval/qdrant_search.py
  |                         -> retrieval/query_embeddings.py + BM25 sparse search
  |                         -> Qdrant RRF/RBAC filtering
  |                         -> medibot.rag.retrieval.reranker -> Groq answer
    v
ChatResponse with answer, sources, retrieval type, and role
```

## Module Call Flow

### Application startup

```text
uvicorn
  -> medibot.api.main.app
  -> medibot.api.main.lifespan()
    -> rag.shared.qdrant_common.get_client()
    -> rag.shared.embeddings.get_embedder(offline=...)
    -> BM25Stats.from_json(processed_data/bm25_stats.json)
    -> reranker.get_reranker()
    -> sql_rag.get_llm()
```

The lifespan function stores the Qdrant client, embedder, and BM25 statistics on `app.state`. The reranker and LLM use module-level lazy singletons, so later requests reuse the loaded objects.

### Login flow

```text
POST /login
  -> medibot.api.main.login()
  -> medibot.core.auth.authenticate_user(username, password)
    -> auth_data/users.json
    -> bcrypt password verification
  -> auth.create_access_token(username, role)
  -> LoginResponse(access_token, role)
```

Protected routes first call `auth.get_current_user()`, which reads the bearer token, verifies the JWT signature and expiration, and returns the authenticated username and role.

### Document question flow

```text
POST /chat {question}
  -> medibot.api.main.chat()
  -> auth.get_current_user()
  -> medibot.api.main.classify_question(question)
    -> sql_rag.get_llm()
    -> Groq router prompt
    -> DOCUMENT
  -> rag.retrieval.qdrant_search.hybrid_search_full(..., role)
    -> embeddings embedder: question -> dense vector
    -> retrieval/query_bm25.py: question -> sparse vector
    -> rag.shared.qdrant_common.rbac_filter(role)
    -> Qdrant dense + sparse search with RRF fusion
  -> reranker.qdrant_hits_to_candidates(raw_hits)
  -> reranker.rerank_chunks(question, candidates, top_k=3)
    -> cross-encoder/ms-marco-MiniLM-L-6-v2
  -> medibot.api.main.generate_hybrid_answer(question, ranked_chunks)
    -> sql_rag.get_llm()
    -> Groq grounded-answer prompt
  -> ChatResponse(answer, sources, retrieval_type="hybrid_rag", role)
```

Only chunks allowed for the authenticated role are passed to the reranker and answer prompt. The answer prompt is instructed to use only those chunks and to say when the available context is insufficient.

### SQL question flow

```text
POST /chat {question}
  -> medibot.api.main.chat()
  -> auth.get_current_user()
  -> medibot.api.main.classify_question(question)
    -> sql_rag.get_llm()
    -> Groq router prompt
    -> SQL
  -> sql_rag.check_billing_access(role)
    -> allow billing_executive/admin
    -> deny other roles with a ChatResponse
  -> sql_rag.sql_rag_chain(question)
    -> sql_rag.get_llm()
    -> sql_rag.get_schema_description()
      -> SQLite PRAGMA/schema inspection
    -> Groq SQL generation prompt
    -> sql_rag.clean_sql(raw_output)
    -> sql_rag.is_safe_select(sql)
    -> sql_rag.execute_sql(sql)
      -> raw_data/db/mediassist.db
    -> Groq result-summary prompt
  -> ChatResponse(answer, sources=[], retrieval_type="sql_rag", role)
```

The SQL chain is role-agnostic by itself. `medibot.api.main.chat()` performs `check_billing_access()` before calling it; `sql_rag_with_access_check()` is also available for callers that want both steps in one wrapper.

At API startup, `src/medibot/api/main.py` eagerly loads the Qdrant client, embedder, BM25 statistics, reranker, and Groq client once. This avoids loading expensive components per request, but means any missing model, invalid configuration, or unavailable service can prevent Uvicorn from starting.

## Requirements

- Windows, macOS, or Linux
- Python 3.10 or newer
- [`uv`](https://docs.astral.sh/uv/)
- A Groq API key for routing and answer generation
- Internet access on first use to download Docling, embedding, and reranker models, unless the required models are already cached

`pyproject.toml` is the authoritative dependency file and `uv.lock` pins the resolved UV environment. A separate `requirements.txt` is intentionally not maintained; both UV and pip install dependencies from `pyproject.toml`.

All shared filesystem paths and environment-backed settings are defined in `src/medibot/core/config.py`. By default, paths are resolved from the repository root rather than from the process working directory. Override them with these environment variables when needed:

| Variable | Default |
| --- | --- |
| `MEDIBOT_SOURCE_DATA_DIR` | `raw_data/mediassist_data/` |
| `MEDIBOT_PROCESSED_DATA_DIR` | `processed_data/` |
| `MEDIBOT_CHUNKS_PATH` | `processed_data/chunks.json` |
| `MEDIBOT_BM25_STATS_PATH` | `processed_data/bm25_stats.json` |
| `MEDIBOT_QDRANT_DB_PATH` | `processed_data/qdrant_hybrid_db/` |
| `MEDIBOT_USERS_PATH` | `auth_data/users.json` |
| `MEDIBOT_SQLITE_DB_PATH` | `raw_data/db/mediassist.db` |

## Setup

From the repository root:

```powershell
uv sync
```

If you prefer standard pip instead of UV, create and activate a virtual environment, then install the project in editable mode. This reads the dependencies from `pyproject.toml`:

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -e .
```

Create or update `.env` with local values. Never commit real credentials:

```dotenv
GROQ_API_KEY=your-groq-api-key
JWT_SECRET=replace-with-a-long-random-secret
JWT_EXPIRE_MINUTES=120
EMBEDDER_OFFLINE=false
CORS_ORIGINS=http://localhost:3000
# Optional:
# GROQ_MODEL=openai/gpt-oss-120b
# EMBEDDING_MODEL_PATH=C:\path\to\local\embedding\model
```

The checked-in `.env` contains credential-like values. Rotate them before sharing or deploying this project, and replace them with local secrets.

## New Laptop Quick Start

Run these commands from the repository root. Choose either UV or standard pip for installation; do not run both installation paths in the same virtual environment.

### Option A: UV

```powershell
uv sync
Copy-Item .env.example .env
uv run python -m scripts.auth.seed_users
uv run python -m scripts.ingestion.create_chunks
uv run python -m scripts.validation.validate_chunks
uv run python -m scripts.ingestion.build_qdrant_index
uv run python -m scripts.validation.validate_hybrid
uv run uvicorn medibot.api.main:app --reload --port 8000
```

### Option B: Standard Python and pip

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -e .
Copy-Item .env.example .env
python -m scripts.auth.seed_users
python -m scripts.ingestion.create_chunks
python -m scripts.validation.validate_chunks
python -m scripts.ingestion.build_qdrant_index
python -m scripts.validation.validate_hybrid
python -m uvicorn medibot.api.main:app --reload --port 8000
```

After copying `.env.example` to `.env`, open `.env` and set a real `GROQ_API_KEY` and a strong `JWT_SECRET`. The first ingestion and API startup may download Docling, embedding, and reranker models.

## Build the Data Stores

### 1. Generate chunks

The source corpus is under `raw_data/mediassist_data/`, organized by collection. The default configuration points there:

```powershell
uv run python -m scripts.ingestion.create_chunks --data-dir raw_data/mediassist_data --out processed_data/chunks.json
```

Using the activated pip virtual environment:

```powershell
python -m scripts.ingestion.create_chunks --data-dir raw_data/mediassist_data --out processed_data/chunks.json
```

For a tokenizer-only pipeline check when Hugging Face model downloads are unavailable:

```powershell
uv run python -m scripts.ingestion.create_chunks --data-dir raw_data/mediassist_data --out processed_data/chunks.json --offline
```

Using standard Python:

```powershell
python -m scripts.ingestion.create_chunks --data-dir raw_data/mediassist_data --out processed_data/chunks.json --offline
```

Offline mode uses word counts and is for validation only; it is not a substitute for the real embedding tokenizer in production.

### 2. Validate chunks

```powershell
uv run python -m scripts.validation.validate_chunks
```

```powershell
python -m scripts.validation.validate_chunks
```

This checks chunk metadata, supported chunk types, collection roles, empty text, and document summaries.

### 3. Ingest Qdrant

```powershell
uv run python -m scripts.ingestion.build_qdrant_index
```

```powershell
python -m scripts.ingestion.build_qdrant_index
```

Use the following only for an offline dense-vector sanity check:

```powershell
uv run python -m scripts.ingestion.build_qdrant_index --offline
```

```powershell
python -m scripts.ingestion.build_qdrant_index --offline
```

Ingestion creates or updates the local hybrid collection under `processed_data/qdrant_hybrid_db/` and writes BM25 corpus statistics to `processed_data/bm25_stats.json`. The current generated corpus contains 257 chunks.

## Run the API

```powershell
uv run uvicorn medibot.api.main:app --reload --port 8000
```

Using standard Python:

```powershell
python -m uvicorn medibot.api.main:app --reload --port 8000
```

Open the interactive API documentation at <http://localhost:8000/docs>.

The API module imports successfully in the current workspace. Startup still performs model and Groq initialization, so an exit code of `1` from Uvicorn is most likely caused by a missing/invalid `GROQ_API_KEY`, model download or Transformers failure, malformed `processed_data/bm25_stats.json`, or incompatible local Qdrant data. Run without `--reload` when diagnosing the full traceback:

```powershell
uv run uvicorn medibot.api.main:app --port 8000
```

```powershell
python -m uvicorn medibot.api.main:app --port 8000
```

`EMBEDDER_OFFLINE=true` only changes the dense embedder. The API still warms the cross-encoder and Groq client during startup.

## API Usage

### Health check

```http
GET /health
```

Response:

```json
{"status":"ok"}
```

### Login

`/login` uses OAuth2 form fields named `username` and `password`:

```powershell
curl.exe -X POST http://localhost:8000/login `
  -H "Content-Type: application/x-www-form-urlencoded" `
  -d "username=dr.mehta&password=doctor"
```

The response contains a bearer token and the user role. Use that token for protected endpoints:

```powershell
$token = "paste-access-token-here"
curl.exe http://localhost:8000/collections/doctor `
  -H "Authorization: Bearer $token"
```

### Chat

```powershell
curl.exe -X POST http://localhost:8000/chat `
  -H "Authorization: Bearer $token" `
  -H "Content-Type: application/json" `
  -d '{"question":"What is the hand hygiene protocol?"}'
```

`POST /chat` routes each question to either document hybrid RAG or SQL RAG. The response includes `answer`, `sources`, `retrieval_type`, and `role`.

Available endpoints:

| Method | Endpoint | Authentication |
| --- | --- | --- |
| `GET` | `/health` | No |
| `POST` | `/login` | No |
| `GET` | `/collections/{role}` | Bearer token |
| `POST` | `/chat` | Bearer token |

## Demo Users

Run the seeder to create or refresh the users in `auth_data/users.json`:

```powershell
uv run python -m scripts.auth.seed_users
```

```powershell
python -m scripts.auth.seed_users
```

The seeder is the source of truth for the demo credentials. Do not use demo credentials in a real deployment.

## Validation Commands

Run these after setup or ingestion:

```powershell
uv run python -m scripts.validation.validate_chunks
uv run python -m scripts.validation.validate_hybrid
uv run python -m scripts.validation.validate_reranker
uv run python -m scripts.validation.validate_sql_rag
uv run python -m scripts.validation.validate_db_schema
```

Using standard Python:

```powershell
python -m scripts.validation.validate_chunks
python -m scripts.validation.validate_hybrid
python -m scripts.validation.validate_reranker
python -m scripts.validation.validate_sql_rag
python -m scripts.validation.validate_db_schema
```

The validation scripts cover chunk metadata, dense and sparse vectors, hybrid retrieval, RBAC filtering, reranking, SQL cleaning/safety checks, and the SQLite schema.

## Source Corpus

`raw_data/mediassist_data/` contains these collection folders:

- `general`: hospital-wide policies, FAQs, leave policy, and staff handbook
- `clinical`: diagnostic reference, drug formulary, and treatment protocols
- `nursing`: ICU nursing procedures and infection control
- `equipment`: equipment manual
- `billing`: billing codes and claim submission guide

The source files are parsed by Docling. Supported input extensions are `.pdf` and `.md`.

## Important Files

- `src/medibot/api/main.py`: FastAPI application, startup lifecycle, routing, response models, and endpoints
- `src/medibot/core/config.py`: repository-root-relative paths and environment-backed settings
- `src/medibot/core/access.py`: single source of truth for document-collection RBAC rules and known roles
- `src/medibot/core/auth.py`: bcrypt authentication and JWT creation/validation
- `scripts/auth/seed_users.py`: demo-user generation
- `scripts/ingestion/create_chunks.py`: Docling parsing and hierarchical chunk generation
- `scripts/ingestion/build_qdrant_index.py`: dense/BM25 vector generation and Qdrant ingestion
- `src/medibot/rag/shared/embeddings.py`: shared real and deterministic offline embedders
- `src/medibot/rag/ingestion/document_embeddings.py`: document embedding workflow
- `src/medibot/rag/retrieval/query_embeddings.py`: user-query embedding workflow
- `src/medibot/rag/shared/bm25_common.py`: shared BM25 tokenization, hashing, constants, and statistics
- `src/medibot/rag/ingestion/document_bm25.py`: document statistics and sparse-vector workflow
- `src/medibot/rag/retrieval/query_bm25.py`: query sparse-vector workflow
- `src/medibot/rag/shared/qdrant_common.py`: Qdrant client, collection, and RBAC helpers
- `src/medibot/rag/ingestion/qdrant_indexer.py`: Qdrant document indexing
- `src/medibot/rag/retrieval/qdrant_search.py`: dense, sparse, and hybrid retrieval
- `src/medibot/rag/retrieval/reranker.py`: cross-encoder loading and candidate reranking
- `src/medibot/rag/retrieval/sql_rag.py`: SQLite schema introspection, NL-to-SQL, safety checks, and summaries
- `raw_data/db/mediassist.db`: operational and billing SQLite database
- `auth_data/users.json`: generated bcrypt-hashed authentication records
- `processed_data/chunks.json`: generated chunk records
- `processed_data/bm25_stats.json`: generated BM25 corpus statistics
- `processed_data/qdrant_hybrid_db/`: current local hybrid Qdrant store

## Security and Production Notes

- Keep `.env`, JWT secrets, API keys, local databases, model caches, and generated vector stores out of source control where appropriate.
- Replace the fallback JWT secret in `src/medibot/core/auth.py` with a required deployment secret.
- `is_safe_select()` is a basic LLM-output guardrail, not a complete SQL security boundary. Use a read-only database user, strict query validation, and additional isolation in production.
- The current `/collections/{role}` route requires authentication but returns the collection list for the role in the URL. Enforce that the requested role matches the authenticated role if this endpoint is exposed beyond a demo.
- Qdrant paths are relative to the process working directory. Run commands from the repository root or configure paths before deployment.
- Generated artifacts under `processed_data/` can be deleted and rebuilt after source documents change.
