"""Optional API-key authentication for every route.

Off unless ``BIOANALYZER_API_KEYS`` is set. When on, requests must send one of
the configured keys in the ``X-API-Key`` header, except liveness endpoints in
``PUBLIC_PATHS`` (used by Docker healthchecks and the CLI's startup probe).
"""

import secrets
from typing import Optional

from fastapi import HTTPException, Request, Security
from fastapi.security import APIKeyHeader

from app.utils import config

API_KEY_HEADER = "X-API-Key"

PUBLIC_PATHS = frozenset({"/", "/health", "/api/v1/", "/api/v1/health", "/api/v1/ping"})

_api_key_header = APIKeyHeader(name=API_KEY_HEADER, auto_error=False)


def _is_valid_key(candidate: str) -> bool:
    # Constant-time compare, and no early exit, so response timing doesn't
    # reveal how much of a key was right or which key matched.
    candidate_bytes = candidate.encode()
    matched = False
    for key in config.API_KEYS:
        matched |= secrets.compare_digest(candidate_bytes, key.encode())
    return matched


async def require_api_key(
    request: Request, api_key: Optional[str] = Security(_api_key_header)
) -> None:
    """FastAPI dependency: 401 unless auth is off, the path is public, or the key is valid."""
    if not config.API_KEYS or request.url.path in PUBLIC_PATHS:
        return
    if api_key and _is_valid_key(api_key):
        return
    raise HTTPException(
        status_code=401,
        detail=f"Missing or invalid API key. Send it in the {API_KEY_HEADER} header.",
        headers={"WWW-Authenticate": "ApiKey"},
    )
