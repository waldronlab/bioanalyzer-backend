"""
Tests for API endpoints in app/api/routers/
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# Try to import FastAPI-dependent modules, skip tests if not available
try:
    from fastapi.testclient import TestClient

    from app.api.app import app
    from app.api.dependencies import (
        get_pubmed_retriever,
        get_unified_qa,
        get_unified_qa_optional,
    )
    from app.services.system_service import get_system_service

    FASTAPI_AVAILABLE = True
except ImportError:
    FASTAPI_AVAILABLE = False
    TestClient = None
    app = None
    get_unified_qa = None
    get_unified_qa_optional = None
    get_pubmed_retriever = None
    get_system_service = None


@pytest.fixture
def client():
    """Create a test client for the FastAPI app.

    raise_server_exceptions=False so an unhandled exception in an
    endpoint comes back as a normal 500 response (what these tests
    assert on), instead of re-raising into the test process — Starlette
    always re-raises past a bare-Exception handler for debugging,
    regardless of whether one is registered.
    """
    if not FASTAPI_AVAILABLE:
        pytest.skip("FastAPI not available")
    return TestClient(app, raise_server_exceptions=False)


@pytest.mark.skipif(not FASTAPI_AVAILABLE, reason="FastAPI not available")
class TestRootEndpoint:
    """Tests for root endpoint."""

    def test_root_endpoint(self, client):
        """Test root endpoint returns basic info."""
        response = client.get("/")
        assert response.status_code == 200
        data = response.json()
        assert "message" in data
        assert "version" in data
        assert "BioAnalyzer" in data["message"]


@pytest.mark.skipif(not FASTAPI_AVAILABLE, reason="FastAPI not available")
class TestHealthEndpoints:
    """Tests for health check endpoints."""

    def test_health_check(self, client):
        """Test basic health check endpoint."""
        response = client.get("/health")
        assert response.status_code == 200
        data = response.json()
        assert "status" in data
        assert "timestamp" in data
        assert "version" in data
        assert data["status"] in ["healthy", "unhealthy"]

    def test_health_check_api_v1(self, client):
        """Test health check via API v1 endpoint."""
        response = client.get("/api/v1/health")
        assert response.status_code == 200
        data = response.json()
        assert "status" in data

    def test_gemini_health_check_success(self, client, override_deps):
        """Test Gemini health check with successful response."""
        mock_qa = MagicMock()
        mock_service = MagicMock()
        mock_service.check_gemini_health = AsyncMock(
            return_value={
                "status": "healthy",
                "api_key_configured": True,
            }
        )

        with override_deps(
            {
                get_unified_qa_optional: lambda: mock_qa,
                get_system_service: lambda: mock_service,
            }
        ):
            response = client.get("/api/v1/health/gemini")
            assert response.status_code == 200
            data = response.json()
            assert "status" in data
            assert "api_key_configured" in data
            assert data["status"] == "healthy"

    def test_gemini_health_check_failure(self, client, override_deps):
        """Test Gemini health check with failed response."""
        mock_qa = MagicMock()
        mock_service = MagicMock()
        mock_service.check_gemini_health = AsyncMock(
            return_value={
                "status": "unhealthy",
                "api_key_configured": False,
            }
        )

        with override_deps(
            {
                get_unified_qa_optional: lambda: mock_qa,
                get_system_service: lambda: mock_service,
            }
        ):
            response = client.get("/api/v1/health/gemini")
            assert response.status_code == 200
            data = response.json()
            assert data["status"] == "unhealthy"

    def test_ncbi_health_check(self, client, override_deps):
        """Test NCBI health check endpoint."""
        mock_retriever = MagicMock()
        mock_retriever.fetch_paper_metadata.return_value = {
            "title": "Test Title",
            "abstract": "Test abstract",
        }
        mock_service = MagicMock()
        mock_service.check_ncbi_health.return_value = {
            "status": "healthy",
            "pmid": "31452104",
        }

        with override_deps(
            {
                get_pubmed_retriever: lambda: mock_retriever,
                get_system_service: lambda: mock_service,
            }
        ):
            response = client.get("/api/v1/health/ncbi")
            assert response.status_code == 200
            data = response.json()
            assert "status" in data
            assert "pmid" in data


@pytest.mark.skipif(not FASTAPI_AVAILABLE, reason="FastAPI not available")
class TestConfigEndpoints:
    """Tests for configuration endpoints."""

    def test_get_config(self, client):
        """Test getting configuration."""
        response = client.get("/api/v1/config")
        assert response.status_code == 200
        data = response.json()
        assert "available_models" in data
        assert "default_model" in data
        assert "frontend_timeout" in data


@pytest.mark.skipif(not FASTAPI_AVAILABLE, reason="FastAPI not available")
class TestSystemEndpoints:
    """Tests for system endpoints."""

    def test_ping_endpoint(self, client):
        """Test ping endpoint."""
        response = client.get("/api/v1/ping")
        assert response.status_code == 200
        data = response.json()
        assert data["message"] == "pong"
        assert "timestamp" in data

    def test_version_endpoint(self, client):
        """Test version endpoint."""
        response = client.get("/api/v1/version")
        assert response.status_code == 200
        data = response.json()
        assert "application_version" in data
        assert "python_version" in data

    @patch("app.api.routers.system.health_check")
    @patch("app.api.routers.system.get_config")
    def test_system_status(self, mock_config, mock_health, client, override_deps):
        """Test system status endpoint.

        /status calls health_check()/get_config() directly (still
        patchable by name), but delegates metrics/gemini checks to the
        injected SystemService, so those are overridden via
        override_deps rather than patched by name.
        """
        mock_health.return_value = {
            "status": "healthy",
            "timestamp": "2023-01-01",
            "version": "1.0.0",
        }
        mock_config.return_value = {"available_models": []}

        mock_service = MagicMock()
        mock_service.get_metrics.return_value = {"total_requests": 0}
        mock_service.check_gemini_health = AsyncMock(return_value={"status": "healthy"})

        with override_deps({get_system_service: lambda: mock_service}):
            response = client.get("/api/v1/status")
            assert response.status_code == 200
            data = response.json()
            assert "overall_status" in data
            assert "health" in data
            assert "config" in data
            assert "metrics" in data


@pytest.mark.skipif(not FASTAPI_AVAILABLE, reason="FastAPI not available")

@pytest.mark.skipif(not FASTAPI_AVAILABLE, reason="FastAPI not available")
class TestQAEndpoint:
    """Tests for Q&A endpoint."""

    def test_ask_question_success(self, client, override_deps):
        """Test Q&A endpoint with successful response."""
        mock_qa = AsyncMock()
        mock_qa.chat = AsyncMock(
            return_value={"text": "This is a test answer", "confidence": 0.9}
        )

        with override_deps({get_unified_qa: lambda: mock_qa}):
            response = client.post(
                "/api/v1/qa", json={"question": "What is the microbiome?"}
            )
            assert response.status_code == 200
            data = response.json()
            assert "answer" in data
            assert "confidence" in data
            assert "timestamp" in data
            assert data["answer"] == "This is a test answer"

    def test_ask_question_missing_question(self, client, override_deps):
        """Test Q&A endpoint with missing question."""
        # Override so Depends does not return 503 before body validation
        mock_qa = AsyncMock()
        with override_deps({get_unified_qa: lambda: mock_qa}):
            response = client.post("/api/v1/qa", json={})
            assert response.status_code == 400
            assert "required" in response.json()["detail"].lower()

    def test_ask_question_empty_question(self, client, override_deps):
        """Test Q&A endpoint with empty question."""
        mock_qa = AsyncMock()
        with override_deps({get_unified_qa: lambda: mock_qa}):
            response = client.post("/api/v1/qa", json={"question": "   "})
            assert response.status_code == 400

    def test_ask_question_no_answer(self, client, override_deps):
        """Test Q&A endpoint when no answer is generated."""
        mock_qa = AsyncMock()
        mock_qa.chat = AsyncMock(return_value={"text": "", "confidence": 0.0})

        with override_deps({get_unified_qa: lambda: mock_qa}):
            response = client.post("/api/v1/qa", json={"question": "Test question"})
            assert response.status_code == 500
            assert "no answer" in response.json()["detail"].lower()

    def test_ask_question_error(self, client, override_deps):
        """Test Q&A endpoint with error."""
        mock_qa = AsyncMock()
        mock_qa.chat = AsyncMock(side_effect=Exception("Test error"))

        with override_deps({get_unified_qa: lambda: mock_qa}):
            response = client.post("/api/v1/qa", json={"question": "Test question"})
            assert response.status_code == 500


@pytest.mark.skipif(not FASTAPI_AVAILABLE, reason="FastAPI not available")
class TestMetricsEndpoint:
    """Tests for metrics endpoint."""

    def test_get_metrics(self, client, override_deps):
        """Test getting system metrics."""
        # Build a mock that serializes like MetricsResponse.
        # memory_usage MUST be a dict — the endpoint is typed
        # `-> MetricsResponse`, so FastAPI validates the return value
        # against that model even when it comes from a mock, and a
        # non-dict value here raises ResponseValidationError.
        mock_metrics = MagicMock()
        mock_metrics.model_dump.return_value = {
            "total_requests": 100,
            "successful_requests": 95,
            "failed_requests": 5,
            "average_response_time": 1.5,
            "cache_hit_rate": 0.8,
            "memory_usage": {
                "total_gb": 8,
                "available_gb": 4,
                "used_percent": 50.0,
            },
        }
        # Also support .dict() for older pydantic paths
        mock_metrics.dict.return_value = mock_metrics.model_dump.return_value
        # And attribute access if FastAPI serializes the model directly
        mock_metrics.total_requests = 100
        mock_metrics.successful_requests = 95
        mock_metrics.failed_requests = 5
        mock_metrics.average_response_time = 1.5
        mock_metrics.cache_hit_rate = 0.8
        mock_metrics.memory_usage = {
            "total_gb": 8,
            "available_gb": 4,
            "used_percent": 50.0,
        }

        mock_service = MagicMock()
        mock_service.get_metrics.return_value = mock_metrics

        with override_deps({get_system_service: lambda: mock_service}):
            response = client.get("/api/v1/metrics")
            assert response.status_code == 200
            data = response.json()
            assert "total_requests" in data
            assert "successful_requests" in data
            assert "failed_requests" in data
            assert "average_response_time" in data
            assert "cache_hit_rate" in data
            assert "memory_usage" in data
