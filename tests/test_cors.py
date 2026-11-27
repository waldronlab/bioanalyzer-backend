"""CORS: same-origin by default; CORS_ORIGINS is honored in every environment.

Server-side clients (CLI, scripts, Streamlit, Shiny) never send an Origin
header and are unaffected. The default used to be "*", and CORS_ORIGINS was
ignored unless ENVIRONMENT=production.
"""

import json
import os
import subprocess
import sys
import textwrap

import pytest

from app.core.settings import BioAnalyzerSettings
from app.utils import config

PREFLIGHT = {
    "Access-Control-Request-Method": "POST",
    "Access-Control-Request-Headers": "content-type",
}


@pytest.mark.skipif(
    bool(os.getenv("CORS_ORIGINS")), reason="CORS_ORIGINS set in the test env"
)
def test_default_allows_no_cross_origin_browser_calls(client):
    assert config.CORS_ORIGINS == []

    preflight = client.options(
        "/api/v1/qa", headers={"Origin": "https://evil.example", **PREFLIGHT}
    )
    assert preflight.status_code == 400
    assert "access-control-allow-origin" not in preflight.headers

    simple = client.get("/api/v1/ping", headers={"Origin": "https://evil.example"})
    assert "access-control-allow-origin" not in simple.headers


def test_same_origin_and_server_side_requests_still_work(client):
    # No Origin header, like the CLI / requests / Streamlit.
    assert client.get("/api/v1/ping").status_code == 200


@pytest.mark.parametrize(
    "raw, expected",
    [
        ("", []),
        ("https://a.example", ["https://a.example"]),
        (
            "https://a.example, https://b.example ,",
            ["https://a.example", "https://b.example"],
        ),
        ("*", ["*"]),
    ],
)
def test_settings_parse_cors_origins(monkeypatch, raw, expected):
    monkeypatch.setenv("CORS_ORIGINS", raw)
    assert BioAnalyzerSettings.from_env().security.cors_origins == expected


def test_settings_default_and_production_preset_are_same_origin(monkeypatch):
    monkeypatch.delenv("CORS_ORIGINS", raising=False)
    assert BioAnalyzerSettings().security.cors_origins == []
    assert BioAnalyzerSettings.from_preset("production").security.cors_origins == []


_PROBE = textwrap.dedent(
    """
    import json
    from fastapi.testclient import TestClient
    from app.api.app import app

    c = TestClient(app)
    out = {}
    for origin in ("https://curator.example", "https://evil.example"):
        r = c.options("/api/v1/qa", headers={
            "Origin": origin,
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "content-type",
        })
        out[origin] = [r.status_code, r.headers.get("access-control-allow-origin")]
    print("RESULT" + json.dumps(out))
    """
)


def _probe(env_overrides):
    """Import the app fresh with the given env (middleware is set at import)."""
    env = {**os.environ, **env_overrides}
    proc = subprocess.run(
        [sys.executable, "-c", _PROBE],
        env=env,
        capture_output=True,
        text=True,
        timeout=180,
    )
    line = next(
        (ln for ln in proc.stdout.splitlines() if ln.startswith("RESULT")), None
    )
    assert line, proc.stderr[-2000:]
    return json.loads(line[len("RESULT") :])


def test_configured_origins_are_honored_outside_production():
    result = _probe(
        {
            "ENVIRONMENT": "development",
            "CORS_ORIGINS": "https://curator.example, https://other.example",
        }
    )
    assert result["https://curator.example"] == [200, "https://curator.example"]
    assert result["https://evil.example"][0] == 400
    assert result["https://evil.example"][1] is None
