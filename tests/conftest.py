"""
Pytest configuration for BioAnalyzer tests.

This file ensures the `app` package is importable in both local and Docker
environments by configuring `sys.path` and `PYTHONPATH`.

It also re-applies the configuration during pytest startup and collection,
since pytest may adjust import paths.
"""

import importlib
import importlib.util
import os
import shutil
import sys
import tempfile
from contextlib import contextmanager
from pathlib import Path
from unittest.mock import AsyncMock, Mock

import pytest
import requests

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


def import_with_fallback(
    module_name: str, class_name: str, *, on_missing: str = "skip"
):
    """
    Import `class_name` from app.services.<module_name>, falling back to
    loading the module directly from its file under app/services/ when the
    normal package import fails (e.g. an unrelated broken import elsewhere
    in the app.* import chain).

    This is the try/except-with-importlib boilerplate previously
    copy-pasted across test_cache_manager.py, test_integration.py (x4), and
    test_pubmed_retriever_errors.py.

    on_missing controls what happens if the fallback file can't be found or
    loaded:
      - "skip" (default): pytest.skip(...) - matches the behavior used by
        test_integration.py and test_pubmed_retriever_errors.py.
      - "raise": re-raise the original ImportError - matches the behavior
        used by test_cache_manager.py.
    """
    dotted = f"app.services.{module_name}"
    try:
        module = importlib.import_module(dotted)
        return getattr(module, class_name)
    except (ImportError, AttributeError):
        service_path = PROJECT_ROOT / "app" / "services" / f"{module_name}.py"
        if not service_path.exists():
            if on_missing == "raise":
                raise
            pytest.skip(f"{module_name}.py not found")
        spec = importlib.util.spec_from_file_location(module_name, str(service_path))
        if spec is None or spec.loader is None:
            if on_missing == "raise":
                raise
            pytest.skip(f"Could not load {module_name} module")
        loaded_module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(loaded_module)
        return getattr(loaded_module, class_name)


def make_fake_response_class(set_response_on_error: bool = False):
    """
    Build a minimal fake `requests` response class for monkeypatching
    `session.get()` in PubMed retriever tests.

    set_response_on_error controls whether raise_for_status() attaches
    itself as the raised HTTPError's `.response` attribute:
      - False (default): matches
        tests/test_standalone_pubmed_retriever.py's _FakeResponse.
      - True: matches tests/test_data_retrieval.py's _FakeResponse, needed
        by tests there that inspect `err.response` after catching the
        HTTPError.
    """

    class _FakeResponse:
        def __init__(self, text="", status_code=200):
            self.text = text
            self.status_code = status_code

        def raise_for_status(self):
            if self.status_code >= 400:
                err = requests.exceptions.HTTPError(f"{self.status_code} error")
                if set_response_on_error:
                    err.response = self
                raise err

    return _FakeResponse


@pytest.fixture
def temp_cache_dir():
    """Create a temporary cache directory for a RAG service under test.

    Shared by test_advanced_rag.py and test_contextual_summarization.py,
    which previously redefined this identically.
    """
    temp_dir = tempfile.mkdtemp()
    yield Path(temp_dir)
    shutil.rmtree(temp_dir, ignore_errors=True)


@pytest.fixture
def mock_llm_provider():
    """Create a mock LLM provider returning a fixed chat() response.

    Shared by test_advanced_rag.py and test_contextual_summarization.py,
    which previously redefined this identically. test_chunk_reranking.py
    needs a different return value (score/reasoning text) so it keeps its
    own local override of the same fixture name.
    """
    mock = Mock()
    mock.chat = AsyncMock(
        return_value={
            "text": "This study analyzed the gut microbiome in human participants with IBD using 16S sequencing. Key findings include genus-level analysis of 100 participants."
        }
    )
    return mock


@pytest.fixture
def client():
    """Shared FastAPI TestClient fixture.

    raise_server_exceptions=False so an unhandled exception in an
    endpoint comes back as a normal 500 response (what these tests
    assert on), instead of re-raising into the test process — Starlette
    always re-raises past a bare-Exception handler for debugging,
    regardless of whether one is registered.
    """
    if not FASTAPI_AVAILABLE:
        pytest.skip("FastAPI not available")
    from fastapi.testclient import TestClient

    return TestClient(fastapi_app, raise_server_exceptions=False)


# ---------------------------------------------------------------------
# Shared "real local ontology store" skip guard
# ---------------------------------------------------------------------
#
# Real, severe CI gap found 2026-08-10 (PR #120): several tests
# (test_local_lookup.py, parts of test_confidence_tier_invariants.py,
# test_grounding_backends.py's NCBITaxon performance test) assert
# specific answers from LocalOntologyBackend against the *real*, fully
# synced local ontology store (ontology_store/ontology_store.db, built
# by scripts/ontology_sync.py - ~4.6M terms across 10 ontologies). That
# file is gitignored (1.6GB+) and CI has no step that builds it, so in
# CI - and in any fresh clone that hasn't run a real sync - the local
# store has no data at all, and every one of those tests fails.
#
# This is not a production bug: app.normalization.grounding.tiering's
# module docstring already documents this exact degraded mode as
# intentional and safe - "an empty local store just means every check
# falls through to OLS, identical to the old ols-only default." Only
# tests asserting a *specific* real-data answer need to skip; nothing
# about production correctness or safety depends on this.
#
# A prior version of this guard (in test_grounding_backends.py) checked
# `os.path.exists(DEFAULT_DB_PATH)` only - insufficient, and confirmed
# wrong in CI: sqlite3 lazily creates an empty file at the connection
# path on first use, so "the file exists" became true as soon as
# *anything* in the same test session opened a LocalOntologyBackend at
# the default path, even with zero rows inside. Checking a real
# ontology's `is_complete()` flag (only ever set by a real sync) is what
# actually distinguishes "no data" from "a lazily-created empty file."
def _real_ontology_store_available() -> bool:
    try:
        from app.normalization.grounding.local_backend import (
            DEFAULT_DB_PATH,
            LocalOntologyBackend,
        )
    except ImportError:
        return False

    db_path = os.getenv("LOCAL_ONTOLOGY_DB_PATH", DEFAULT_DB_PATH)
    if not Path(db_path).exists():
        return False
    try:
        backend = LocalOntologyBackend(db_path=db_path)
        try:
            return backend.is_complete("ncbitaxon")
        finally:
            backend.close()
    except Exception:
        return False


requires_real_ontology_store = pytest.mark.skipif(
    not _real_ontology_store_available(),
    reason="requires a real, fully-synced local ontology store "
    "(scripts/ontology_sync.py) - not present in this environment "
    "(e.g. CI, or a fresh clone that hasn't run a sync)",
)


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
