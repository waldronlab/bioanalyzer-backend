"""Tests for app/api/middleware/rate_limit.py.

Regression coverage for a real bug: RateLimitMiddleware used to `raise
HTTPException(429, ...)` from inside its `dispatch()`. Because
BaseHTTPMiddleware sits outside Starlette's ExceptionMiddleware layer (the
thing that normally turns a raised HTTPException into a same-status JSON
response), that exception instead propagated to the app's catch-all
`Exception` handler and got flattened into a generic 500 - silently
discarding the real 429 status code a caller needs to distinguish "back off
and retry" from a genuine server error (this broke the BioAnalyzer CLI's
retry-on-429 logic in scripts/cli.py::analyze_papers).
"""

import pytest

try:
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from app.api.middleware.rate_limit import RateLimitMiddleware, _rate_limit_store

    FASTAPI_AVAILABLE = True
except ImportError:
    FASTAPI_AVAILABLE = False
    FastAPI = None
    TestClient = None
    RateLimitMiddleware = None
    _rate_limit_store = None


pytestmark = pytest.mark.skipif(not FASTAPI_AVAILABLE, reason="FastAPI not available")


@pytest.fixture
def client():
    _rate_limit_store.clear()
    app = FastAPI()
    app.add_middleware(RateLimitMiddleware, requests_per_minute=3, enabled=True)

    @app.get("/ping")
    async def ping():
        return {"ok": True}

    return TestClient(app, raise_server_exceptions=False)


def test_requests_within_limit_succeed(client):
    for _ in range(3):
        resp = client.get("/ping")
        assert resp.status_code == 200


def test_exceeding_limit_returns_429_not_500(client):
    for _ in range(3):
        assert client.get("/ping").status_code == 200

    resp = client.get("/ping")
    assert resp.status_code == 429
    assert "Rate limit exceeded" in resp.json()["detail"]


def test_429_response_has_no_500_wrapper(client):
    for _ in range(3):
        client.get("/ping")
    resp = client.get("/ping")
    body = resp.json()
    assert body.get("error") != "Internal Server Error"
