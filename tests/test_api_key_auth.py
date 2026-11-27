"""Optional API-key auth (app/api/security.py) and the analyze-url model allowlist.

Both are off unless configured, so the first tests pin that today's open
behavior is unchanged.
"""

from unittest.mock import AsyncMock, patch

import pytest

from app.api.routers import study_analysis
from app.utils import config

# `client` fixture comes from tests/conftest.py.

PROTECTED_GET = "/api/v2/fields"  # cheap route, no external calls


@pytest.fixture
def auth_on(monkeypatch):
    monkeypatch.setattr(config, "API_KEYS", frozenset({"key-one", "key-two"}))


# --------------------------------------------------------------------------- #
# Auth disabled (default)
# --------------------------------------------------------------------------- #


def test_auth_disabled_by_default_allows_requests_without_key(client, monkeypatch):
    monkeypatch.setattr(config, "API_KEYS", frozenset())
    assert client.get(PROTECTED_GET).status_code == 200


# --------------------------------------------------------------------------- #
# Auth enabled
# --------------------------------------------------------------------------- #


def test_missing_key_is_rejected(client, auth_on):
    response = client.get(PROTECTED_GET)
    assert response.status_code == 401
    assert response.headers["WWW-Authenticate"] == "ApiKey"


def test_wrong_key_is_rejected(client, auth_on):
    response = client.get(PROTECTED_GET, headers={"X-API-Key": "nope"})
    assert response.status_code == 401


def test_non_ascii_key_is_rejected_not_500(client, auth_on):
    response = client.get(
        PROTECTED_GET, headers={"X-API-Key": "k\u00e9y".encode("latin-1")}
    )
    assert response.status_code == 401


@pytest.mark.parametrize("key", ["key-one", "key-two"])
def test_any_configured_key_is_accepted(client, auth_on, key):
    assert client.get(PROTECTED_GET, headers={"X-API-Key": key}).status_code == 200


@pytest.mark.parametrize(
    "path",
    [
        "/api/v1/analyze/12345678",
        "/api/v2/analyze/12345678",
        "/api/v1/analysis-status/some-job",
        "/api/v1/config",
    ],
)
def test_expensive_and_internal_routes_require_key(client, auth_on, path):
    assert client.get(path).status_code == 401


def test_post_routes_require_key(client, auth_on):
    assert client.post("/api/v1/qa", json={"question": "hi"}).status_code == 401
    assert (
        client.post(
            "/api/v1/analyze-url", json={"url": "https://example.org"}
        ).status_code
        == 401
    )


@pytest.mark.parametrize(
    "path", ["/", "/health", "/api/v1/", "/api/v1/health", "/api/v1/ping"]
)
def test_liveness_routes_stay_public(client, auth_on, path):
    assert client.get(path).status_code != 401


def test_cors_preflight_is_not_blocked_by_auth(client, auth_on):
    # Preflights never carry the key; CORSMiddleware answers them (200 for an
    # allowed origin, 400 otherwise) before auth runs - never 401.
    response = client.options(
        PROTECTED_GET,
        headers={
            "Origin": "https://curator.example",
            "Access-Control-Request-Method": "GET",
            "Access-Control-Request-Headers": "X-API-Key",
        },
    )
    assert response.status_code != 401


# --------------------------------------------------------------------------- #
# /api/v1/analyze-url model allowlist
# --------------------------------------------------------------------------- #


@pytest.fixture
def no_background_job():
    study_analysis.job_store.clear()
    with patch.object(study_analysis, "process_url_analysis", AsyncMock()) as m:
        yield m
    study_analysis.job_store.clear()


def test_model_allowlist_off_accepts_any_model(client, monkeypatch, no_background_job):
    monkeypatch.setattr(config, "URL_ANALYSIS_ALLOWED_MODELS", frozenset())
    response = client.post(
        "/api/v1/analyze-url",
        json={"url": "https://example.org", "llm_model": "openai/some-big-model"},
    )
    assert response.status_code == 200


def test_model_allowlist_rejects_unlisted_model(client, monkeypatch, no_background_job):
    monkeypatch.setattr(
        config,
        "URL_ANALYSIS_ALLOWED_MODELS",
        frozenset({"gemini/gemini-2.0-flash", "gemini/text-embedding-004"}),
    )
    response = client.post(
        "/api/v1/analyze-url",
        json={"url": "https://example.org", "llm_model": "openai/some-big-model"},
    )
    assert response.status_code == 422
    assert "llm_model" in response.json()["detail"]
    no_background_job.assert_not_called()
    assert study_analysis.job_store == {}


def test_model_allowlist_accepts_listed_defaults(
    client, monkeypatch, no_background_job
):
    monkeypatch.setattr(
        config,
        "URL_ANALYSIS_ALLOWED_MODELS",
        frozenset({"gemini/gemini-2.0-flash", "gemini/text-embedding-004"}),
    )
    response = client.post("/api/v1/analyze-url", json={"url": "https://example.org"})
    assert response.status_code == 200
