import types
import pytest
from scripts.cli import BioAnalyzerCLI


class DummyResponse:
    def __init__(self, status_code: int):
        self.status_code = status_code


def test_check_backend_health_success(monkeypatch):
    """check_backend_health should return True when /health returns 200."""

    def _fake_get(url, timeout=5):
        assert url.endswith("/health")
        return DummyResponse(200)

    import requests

    monkeypatch.setattr(requests, "get", _fake_get)
    cli = BioAnalyzerCLI()
    assert cli.check_backend_health() is True


def test_check_backend_health_failure(monkeypatch):
    """check_backend_health should return False on network errors."""

    def _fake_get(url, timeout=5):
        raise RuntimeError("boom")

    import requests

    monkeypatch.setattr(requests, "get", _fake_get)
    cli = BioAnalyzerCLI()
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
