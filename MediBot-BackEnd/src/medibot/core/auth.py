"""
JWT-based authentication: src/medibot/core/auth.py.

- Passwords are bcrypt-hashed in auth_data/users.json (created by seed_users.py).
- /login verifies username+password, then issues a JWT with `sub` (username)
  and `role` claims, signed with JWT_SECRET, expiring after JWT_EXPIRE_MINUTES.
- /chat and /collections/{role} verify the JWT via get_current_user() instead
  of trusting a role passed in the request body/path -- this is what makes
  the RBAC gate genuinely server-side rather than client-trusted.

Uses the `bcrypt` library directly (not passlib) -- passlib is unmaintained
and has a known compatibility bug with bcrypt>=4.1 that raises a spurious
"password cannot be longer than 72 bytes" error even for short passwords.
"""
import json
import logging
from datetime import datetime, timedelta, timezone

import bcrypt
import jwt
from fastapi import Depends, HTTPException
from fastapi.security import OAuth2PasswordBearer
from pydantic import BaseModel

from .config import JWT_EXPIRE_MINUTES, JWT_SECRET, USERS_PATH

logger = logging.getLogger("medibot.auth")

JWT_ALGORITHM = "HS256"

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="login")


class TokenData(BaseModel):
    username: str
    role: str


def _load_users() -> list[dict]:
    if not USERS_PATH.exists():
        raise RuntimeError(
            "auth_data/users.json not found. Run `uv run python -m scripts.auth.seed_users` once to create it."
        )
    return json.loads(USERS_PATH.read_text())


def authenticate_user(username: str, password: str) -> dict | None:
    """Returns the user dict if username+password match, else None."""
    users = _load_users()
    for user in users:
        if user["username"] == username:
            if bcrypt.checkpw(password.encode("utf-8"), user["password_hash"].encode("utf-8")):
                return user
            return None
    return None


def create_access_token(username: str, role: str) -> str:
    expire = datetime.now(timezone.utc) + timedelta(minutes=JWT_EXPIRE_MINUTES)
    payload = {"sub": username, "role": role, "exp": expire}
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)


def get_current_user(token: str = Depends(oauth2_scheme)) -> TokenData:
    """
    FastAPI dependency: decodes and validates the JWT from the
    Authorization: Bearer <token> header. Raises 401 if invalid/expired.
    /chat and /collections/{role} use this to get the TRUE role -- never
    trust a role field sent directly in the request body.
    """
    try:
        payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
        username = payload.get("sub")
        role = payload.get("role")
        if username is None or role is None:
            raise HTTPException(status_code=401, detail="Invalid token payload")
        return TokenData(username=username, role=role)
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Token expired, please log in again")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="Invalid authentication token")
