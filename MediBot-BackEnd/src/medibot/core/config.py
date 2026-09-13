"""Shared paths and settings: src/medibot/core/config.py."""

import os
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[3]


def _path_from_env(name: str, default: Path) -> Path:
    value = os.environ.get(name)
    return Path(value).expanduser() if value else default


SOURCE_DATA_DIR = _path_from_env(
    "MEDIBOT_SOURCE_DATA_DIR", PROJECT_ROOT / "raw_data" / "mediassist_data"
)
PROCESSED_DATA_DIR = _path_from_env(
    "MEDIBOT_PROCESSED_DATA_DIR", PROJECT_ROOT / "processed_data"
)
CHUNKS_PATH = _path_from_env("MEDIBOT_CHUNKS_PATH", PROCESSED_DATA_DIR / "chunks.json")
BM25_STATS_PATH = _path_from_env(
    "MEDIBOT_BM25_STATS_PATH", PROCESSED_DATA_DIR / "bm25_stats.json"
)
QDRANT_DB_PATH = _path_from_env(
    "MEDIBOT_QDRANT_DB_PATH", PROCESSED_DATA_DIR / "qdrant_hybrid_db"
)
USERS_PATH = _path_from_env(
    "MEDIBOT_USERS_PATH", PROJECT_ROOT / "auth_data" / "users.json"
)
SQLITE_DB_PATH = _path_from_env(
    "MEDIBOT_SQLITE_DB_PATH", PROJECT_ROOT / "raw_data" / "db" / "mediassist.db"
)

EMBEDDER_OFFLINE = os.environ.get("EMBEDDER_OFFLINE", "false").lower() == "true"
JWT_SECRET = os.environ.get("JWT_SECRET", "dev-secret-change-in-production")
JWT_EXPIRE_MINUTES = int(os.environ.get("JWT_EXPIRE_MINUTES", "120"))
GROQ_MODEL = os.environ.get("GROQ_MODEL", "openai/gpt-oss-120b")
CORS_ORIGINS = os.environ.get("CORS_ORIGINS", "http://localhost:3000").split(",")
