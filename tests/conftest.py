"""
Pytest configuration for BioAnalyzer tests.

This file ensures the `app` package is importable in both local and Docker
environments by configuring `sys.path` and `PYTHONPATH`.

It also re-applies the configuration during pytest startup and collection,
since pytest may adjust import paths.
"""

import os
import sys
from contextlib import contextmanager
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).parent.parent.resolve()
PROJECT_ROOT_STR = str(PROJECT_ROOT)

IS_DOCKER = Path("/app").is_dir()

DOCKER_PATHS = ["/app"]
FALLBACK_PATHS = [
    PROJECT_ROOT_STR,
    str(PROJECT_ROOT / "app"),
    "/app",
    "/app/app",
]


def _ensure_paths() -> None:
    """Ensure required paths exist in sys.path and PYTHONPATH."""
    paths = DOCKER_PATHS if IS_DOCKER else []
    paths = paths + [PROJECT_ROOT_STR]

    # sys.path
    for p in reversed(paths):  # first item ends up at index 0
        if p not in sys.path:
            sys.path.insert(0, p)

    # PYTHONPATH
    existing = os.environ.get("PYTHONPATH", "")
    parts = [p for p in existing.split(":") if p]
    for p in reversed(paths):
        if p not in parts:
            parts.insert(0, p)
    os.environ["PYTHONPATH"] = ":".join(parts)


def _ensure_app_importable() -> None:
    """Try importing app; if it fails, try common fallback paths."""
    try:
        import app  # noqa: F401

        return
    except ImportError:
        pass

    for p in FALLBACK_PATHS:
        if Path(p).exists() and p not in sys.path:
            sys.path.insert(0, p)
            try:
                import app  # noqa: F401

                return
            except ImportError:
                continue


# Apply immediately when conftest is imported
_ensure_paths()
_ensure_app_importable()


def pytest_configure(config):
    """Runs before test collection."""
    _ensure_paths()
    try:
        import app  # noqa: F401
    except ImportError as e:
        print(f"WARNING: Cannot import app module: {e}")
        print(f"Python path: {sys.path}")
        print(f"Project root: {PROJECT_ROOT_STR}")
        print(f"Is Docker: {IS_DOCKER}")


def pytest_collection_modifyitems(config, items):
    """Runs after collection but before test execution."""
    _ensure_paths()


# ---------------------------------------------------------------------
# Shared FastAPI dependency-override helper
# ---------------------------------------------------------------------
#
# Endpoints under app/api/routers/ get their services (UnifiedQA,
# PubMedRetriever, SystemService, ...) via Depends() rather than module
# globals (see app/api/dependencies.py, app/services/system_service.py).
# Tests must replace those with app.dependency_overrides, not by
# @patch-ing a module attribute — FastAPI captures the actual callable
# in each route's dependency graph at import time, so patching the name
# afterward doesn't change what a request actually resolves.
#
# This fixture is shared so every test module (test_api_endpoints.py,
# test_integration.py, ...) uses the same override/cleanup logic
# instead of each redefining its own copy.

try:
    from app.api.app import app as fastapi_app

    FASTAPI_AVAILABLE = True
except ImportError:
    fastapi_app = None
    FASTAPI_AVAILABLE = False


@pytest.fixture
def override_deps():
    """
    Temporarily override FastAPI dependencies for a test.

    Usage:
        def test_x(client, override_deps):
            with override_deps({get_unified_qa: lambda: mock_qa}):
                response = client.post("/api/v1/qa", json={...})
    """

    @contextmanager
    def _override(overrides: dict):
        if not FASTAPI_AVAILABLE:
            yield
            return
        for dep, replacement in overrides.items():
            fastapi_app.dependency_overrides[dep] = replacement
        try:
            yield
        finally:
            for dep in overrides:
                fastapi_app.dependency_overrides.pop(dep, None)

    return _override
