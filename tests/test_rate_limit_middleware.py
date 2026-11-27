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


# ---------------------------------------------------------------------------
# Client IP extraction: forwarding headers count only from trusted proxies
# ---------------------------------------------------------------------------

from types import SimpleNamespace


def _client_ip(peer, headers=None, trusted_proxies=None):
    middleware = RateLimitMiddleware(
        FastAPI(), requests_per_minute=3, trusted_proxies=trusted_proxies
    )
    request = SimpleNamespace(
        client=SimpleNamespace(host=peer) if peer else None,
        headers=headers or {},
    )
    return middleware._get_client_ip(request)


def test_direct_public_client_cannot_spoof_forwarded_for():
    assert (
        _client_ip("203.0.113.9", {"X-Forwarded-For": "198.51.100.1"}) == "203.0.113.9"
    )


def test_direct_public_client_cannot_spoof_real_ip():
    assert _client_ip("203.0.113.9", {"X-Real-IP": "198.51.100.1"}) == "203.0.113.9"


def test_trusted_proxy_forwarded_for_is_used():
    assert _client_ip("172.18.0.5", {"X-Forwarded-For": "203.0.113.9"}) == (
        "203.0.113.9"
    )


def test_spoofed_leftmost_forwarded_for_entry_is_ignored():
    # Client sent "X-Forwarded-For: 1.2.3.4"; the proxy appended the real peer.
    headers = {"X-Forwarded-For": "1.2.3.4, 203.0.113.9"}
    assert _client_ip("127.0.0.1", headers) == "203.0.113.9"


def test_trusted_hops_in_forwarded_for_are_skipped():
    headers = {"X-Forwarded-For": "203.0.113.9, 10.0.0.7"}
    assert _client_ip("127.0.0.1", headers) == "203.0.113.9"


def test_trusted_proxy_real_ip_is_used_without_forwarded_for():
    assert _client_ip("10.0.0.2", {"X-Real-IP": "203.0.113.9"}) == "203.0.113.9"


def test_trusted_proxy_without_headers_uses_peer():
    assert _client_ip("10.0.0.2") == "10.0.0.2"


def test_missing_client_is_unknown():
    assert _client_ip(None) == "unknown"


def test_custom_trusted_proxies_replace_defaults():
    headers = {"X-Forwarded-For": "203.0.113.9"}
    # Public load balancer listed explicitly -> trusted.
    assert _client_ip("198.51.100.7", headers, "198.51.100.0/24") == "203.0.113.9"
    # Private range no longer trusted once the list is overridden.
    assert _client_ip("10.0.0.2", headers, "198.51.100.0/24") == "10.0.0.2"


def test_wildcard_restores_trust_everyone_behavior():
    headers = {"X-Forwarded-For": "198.51.100.1"}
    assert _client_ip("203.0.113.9", headers, "*") == "198.51.100.1"


def test_rotating_spoofed_forwarded_for_does_not_reset_limit(client):
    # TestClient's peer ("testclient") isn't a trusted proxy, so each new fake
    # X-Forwarded-For value must not get a fresh rate-limit bucket.
    for i in range(3):
        headers = {"X-Forwarded-For": f"198.51.100.{i}"}
        assert client.get("/ping", headers=headers).status_code == 200
    resp = client.get("/ping", headers={"X-Forwarded-For": "198.51.100.99"})
    assert resp.status_code == 429
