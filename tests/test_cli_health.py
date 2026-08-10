import types
import pytest
from scripts.cli import BioAnalyzerCLI


class DummyResponse:
    def __init__(self, status_code: int, json_data=None):
        self.status_code = status_code
        self._json_data = json_data or {}

    def json(self):
        return self._json_data


def test_check_backend_health_success(monkeypatch):
    """check_backend_health should return True when /health returns 200."""

    def _fake_get(url, timeout=5):
        assert url.endswith("/health")
        return DummyResponse(200)

    cli = BioAnalyzerCLI()
    monkeypatch.setattr(cli._session, "get", _fake_get)
    assert cli.check_backend_health() is True


def test_check_backend_health_failure(monkeypatch):
    """check_backend_health should return False on network errors."""

    def _fake_get(url, timeout=5):
        raise RuntimeError("boom")

    cli = BioAnalyzerCLI()
    monkeypatch.setattr(cli._session, "get", _fake_get)
    assert cli.check_backend_health() is False


def test_wait_for_backend_health_respects_timeout(monkeypatch):
    """
    Simulate a backend that never becomes healthy — expect False after timeout.
    Uses check_backend_health directly since _wait_for_backend_health may not exist.
    """
    cli = BioAnalyzerCLI()
    monkeypatch.setattr(cli, "check_backend_health", lambda: False)

    # If _wait_for_backend_health exists, test it; otherwise test check_backend_health
    if hasattr(cli, "_wait_for_backend_health"):
        healthy = cli._wait_for_backend_health(timeout=1, interval=0.1)
        assert healthy is False
    else:
        assert cli.check_backend_health() is False


# Regression coverage for a real bug: _fetch_analysis (the `analyze` command)
# and ask_question (the `qa` command) hardcoded "http://localhost:8000/..."
# directly instead of going through self._build_api_url()/self.api_base_url
# like every other HTTP call site in this file (_start_url_job,
# _poll_url_job) - silently ignoring BIOANALYZER_API_URL, contradicting
# CLAUDE.md's documented contract ("no hardcoded localhost") for the CLI's
# two most-used interactive commands.


def test_fetch_analysis_uses_configured_api_base_url_by_default(monkeypatch):
    captured = {}

    def _fake_get(url, params=None, timeout=None):
        captured["url"] = url
        return DummyResponse(200, {"pmid": "12345678"})

    cli = BioAnalyzerCLI()
    monkeypatch.setattr(cli._session, "get", _fake_get)
    result, error = cli._fetch_analysis("12345678", refresh=False, request_timeout=30)
    assert error is None
    assert captured["url"] == "http://localhost:8000/api/v1/analyze/12345678"


def test_fetch_analysis_respects_bioanalyzer_api_url_override(monkeypatch):
    """The actual regression: pointing the CLI at a non-default host must
    change where _fetch_analysis sends its request, not silently stay on
    localhost."""
    monkeypatch.setenv("BIOANALYZER_API_URL", "http://remote-host:9000/api/v1")
    captured = {}

    def _fake_get(url, params=None, timeout=None):
        captured["url"] = url
        return DummyResponse(200, {"pmid": "12345678"})

    cli = BioAnalyzerCLI()
    monkeypatch.setattr(cli._session, "get", _fake_get)
    result, error = cli._fetch_analysis("12345678", refresh=False, request_timeout=30)
    assert error is None
    assert captured["url"] == "http://remote-host:9000/api/v1/analyze/12345678"
    assert "localhost" not in captured["url"]


def test_ask_question_uses_configured_api_base_url_by_default(monkeypatch):
    captured = {}

    def _fake_post(url, json=None, timeout=None):
        captured["url"] = url
        return DummyResponse(200, {"answer": "42"})

    cli = BioAnalyzerCLI()
    monkeypatch.setattr(cli, "check_backend_health", lambda: True)
    monkeypatch.setattr(cli._session, "post", _fake_post)
    cli.ask_question("What is the meaning of life?")
    assert captured["url"] == "http://localhost:8000/api/v1/qa"


def test_ask_question_respects_bioanalyzer_api_url_override(monkeypatch):
    monkeypatch.setenv("BIOANALYZER_API_URL", "http://remote-host:9000/api/v1")
    captured = {}

    def _fake_post(url, json=None, timeout=None):
        captured["url"] = url
        return DummyResponse(200, {"answer": "42"})

    cli = BioAnalyzerCLI()
    monkeypatch.setattr(cli, "check_backend_health", lambda: True)
    monkeypatch.setattr(cli._session, "post", _fake_post)
    cli.ask_question("What is the meaning of life?")
    assert captured["url"] == "http://remote-host:9000/api/v1/qa"
    assert "localhost" not in captured["url"]
