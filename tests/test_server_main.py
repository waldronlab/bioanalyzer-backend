"""scripts/main.py warns when it starts more than one worker.

URL-analysis jobs and rate-limit counts live in each worker process's memory,
so they don't work across workers. Every shipped config runs one worker; the
warning makes the assumption visible the moment someone scales up.
"""

import sys
import types

import pytest

from scripts import main as server_main


@pytest.fixture
def fake_uvicorn(monkeypatch):
    calls = []
    module = types.SimpleNamespace(run=lambda *a, **k: calls.append(k))
    monkeypatch.setitem(sys.modules, "uvicorn", module)
    monkeypatch.setattr(sys, "argv", ["main.py"])
    monkeypatch.delenv("UVICORN_RELOAD", raising=False)
    return calls


def test_warns_with_multiple_workers(monkeypatch, capsys, fake_uvicorn):
    monkeypatch.setenv("UVICORN_WORKERS", "4")
    server_main.main()
    out = capsys.readouterr().out
    assert "Warning: 4 workers" in out
    assert fake_uvicorn[0]["workers"] == 4


def test_no_warning_with_one_worker(monkeypatch, capsys, fake_uvicorn):
    monkeypatch.delenv("UVICORN_WORKERS", raising=False)
    server_main.main()
    assert "Warning" not in capsys.readouterr().out
    assert fake_uvicorn  # server still started
