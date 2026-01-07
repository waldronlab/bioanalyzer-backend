import types

import pytest

from cli import BioAnalyzerCLI


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
    _wait_for_backend_health should poll check_backend_health until timeout.

    We simulate a backend that never becomes healthy by always returning False.
    """
    cli = BioAnalyzerCLI()

    # Patch check_backend_health on the instance to avoid any network access.
    cli.check_backend_health = types.MethodType(lambda self: False, cli)

    # Use a very small timeout/interval so the test runs quickly.
    healthy = cli._wait_for_backend_health(timeout=1, interval=0.1)
    assert healthy is False
