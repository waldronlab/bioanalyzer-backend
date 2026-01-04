"""
Tests for API endpoints in app/api/routers/
"""

import pytest
from unittest.mock import patch, AsyncMock, MagicMock

# Try to import FastAPI-dependent modules, skip tests if not available
try:
    from fastapi.testclient import TestClient
    from app.api.app import app

    FASTAPI_AVAILABLE = True
except ImportError:
    FASTAPI_AVAILABLE = False
    TestClient = None
    app = None


@pytest.fixture
def client():
    """Create a test client for the FastAPI app."""
    if not FASTAPI_AVAILABLE:
        pytest.skip("FastAPI not available")
    return TestClient(app)


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

    @patch("app.api.routers.system.unified_qa")
    def test_gemini_health_check_success(self, mock_qa, client):
        """Test Gemini health check with successful response."""
        mock_qa.ask_question = AsyncMock(return_value={"answer": "Test response"})
        response = client.get("/api/v1/health/gemini")
        assert response.status_code == 200
        data = response.json()
        assert "status" in data
        assert "api_key_configured" in data

    @patch("app.api.routers.system.unified_qa")
    def test_gemini_health_check_failure(self, mock_qa, client):
        """Test Gemini health check with failed response."""
        mock_qa.ask_question = AsyncMock(return_value={})
        response = client.get("/api/v1/health/gemini")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "unhealthy"

    @patch("app.api.routers.system.PubMedRetriever")
    def test_ncbi_health_check(self, mock_retriever_class, client):
        """Test NCBI health check endpoint."""
        mock_retriever = MagicMock()
        mock_retriever.fetch_paper_metadata.return_value = {
            "title": "Test Title",
            "abstract": "Test abstract",
        }
        mock_retriever_class.return_value = mock_retriever

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
    @patch("app.api.routers.system.get_metrics")
    @patch("app.api.routers.system.gemini_health_check")
    def test_system_status(
        self, mock_gemini, mock_metrics, mock_config, mock_health, client
    ):
        """Test system status endpoint."""
        mock_health.return_value = {
            "status": "healthy",
            "timestamp": "2023-01-01",
            "version": "1.0.0",
        }
        mock_config.return_value = {"available_models": []}
        mock_metrics.return_value = {"total_requests": 0}
        mock_gemini.return_value = {"status": "healthy"}

        response = client.get("/api/v1/status")
        assert response.status_code == 200
        data = response.json()
        assert "overall_status" in data
        assert "health" in data
        assert "config" in data
        assert "metrics" in data


@pytest.mark.skipif(not FASTAPI_AVAILABLE, reason="FastAPI not available")
class TestBugSigDBAnalysisEndpoints:
    """Tests for BugSigDB analysis endpoints."""

    def test_get_essential_fields(self, client):
        """Test getting essential fields information."""
        response = client.get("/api/v1/fields")
        assert response.status_code == 200
        data = response.json()
        assert "essential_fields" in data
        assert "status_values" in data

        # Check all 6 essential fields are present
        essential_fields = data["essential_fields"]
        assert "host_species" in essential_fields
        assert "body_site" in essential_fields
        assert "condition" in essential_fields
        assert "sequencing_type" in essential_fields
        assert "taxa_level" in essential_fields
        assert "sample_size" in essential_fields

        # Check field structure
        for field_name, field_info in essential_fields.items():
            assert "name" in field_info
            assert "description" in field_info
            assert "required" in field_info
            assert field_info["required"] is True

    @patch("app.api.routers.bugsigdb_analysis.analyze_paper_simple")
    def test_analyze_paper_success(self, mock_analyze, client):
        """Test paper analysis endpoint with successful response."""
        mock_result = {
            "pmid": "12345678",
            "title": "Test Paper",
            "fields": {
                "host_species": {
                    "status": "PRESENT",
                    "value": "Human",
                    "confidence": 0.95,
                }
            },
        }
        mock_analyze.return_value = mock_result

        response = client.get("/api/v1/analyze/12345678")
        assert response.status_code == 200
        data = response.json()
        assert data["pmid"] == "12345678"
        assert "fields" in data

    @patch("app.api.routers.bugsigdb_analysis.analyze_paper_simple")
    def test_analyze_paper_not_found(self, mock_analyze, client):
        """Test paper analysis endpoint when paper not found."""
        mock_analyze.return_value = None

        response = client.get("/api/v1/analyze/12345678")
        assert response.status_code == 404
        assert "failed" in response.json()["detail"].lower()

    @patch("app.api.routers.bugsigdb_analysis.analyze_paper_simple")
    def test_analyze_paper_error(self, mock_analyze, client):
        """Test paper analysis endpoint with error."""
        mock_analyze.side_effect = Exception("Test error")

        response = client.get("/api/v1/analyze/12345678")
        assert response.status_code == 500
        assert "error" in response.json()["detail"].lower()


@pytest.mark.skipif(not FASTAPI_AVAILABLE, reason="FastAPI not available")
class TestQAEndpoint:
    """Tests for Q&A endpoint."""

    @patch("app.api.routers.system.get_unified_qa")
    def test_ask_question_success(self, mock_get_qa, client):
        """Test Q&A endpoint with successful response."""
        mock_qa = AsyncMock()
        mock_qa.chat = AsyncMock(
            return_value={"text": "This is a test answer", "confidence": 0.9}
        )
        mock_get_qa.return_value = mock_qa

        response = client.post(
            "/api/v1/qa", json={"question": "What is the microbiome?"}
        )
        assert response.status_code == 200
        data = response.json()
        assert "answer" in data
        assert "confidence" in data
        assert "timestamp" in data
        assert data["answer"] == "This is a test answer"

    def test_ask_question_missing_question(self, client):
        """Test Q&A endpoint with missing question."""
        response = client.post("/api/v1/qa", json={})
        assert response.status_code == 400
        assert "required" in response.json()["detail"].lower()

    def test_ask_question_empty_question(self, client):
        """Test Q&A endpoint with empty question."""
        response = client.post("/api/v1/qa", json={"question": "   "})
        assert response.status_code == 400

    @patch("app.api.routers.system.get_unified_qa")
    def test_ask_question_no_answer(self, mock_get_qa, client):
        """Test Q&A endpoint when no answer is generated."""
        mock_qa = AsyncMock()
        mock_qa.chat = AsyncMock(return_value={"text": "", "confidence": 0.0})
        mock_get_qa.return_value = mock_qa

        response = client.post("/api/v1/qa", json={"question": "Test question"})
        assert response.status_code == 500
        assert "no answer" in response.json()["detail"].lower()

    @patch("app.api.routers.system.get_unified_qa")
    def test_ask_question_error(self, mock_get_qa, client):
        """Test Q&A endpoint with error."""
        mock_qa = AsyncMock()
        mock_qa.chat = AsyncMock(side_effect=Exception("Test error"))
        mock_get_qa.return_value = mock_qa

        response = client.post("/api/v1/qa", json={"question": "Test question"})
        assert response.status_code == 500


@pytest.mark.skipif(not FASTAPI_AVAILABLE, reason="FastAPI not available")
class TestMetricsEndpoint:
    """Tests for metrics endpoint."""

    @patch("app.api.routers.system.perf_logger")
    @patch("app.api.routers.system.CacheManager")
    def test_get_metrics(self, mock_cache_class, mock_perf_logger, client):
        """Test getting system metrics."""
        mock_perf_logger.get_metrics.return_value = {
            "total_requests": 100,
            "successful_requests": 95,
            "failed_requests": 5,
            "average_response_time": 1.5,
        }

        mock_cache = MagicMock()
        mock_cache.get_cache_stats.return_value = {
            "total_requests": 100,
            "cache_hits": 80,
        }
        mock_cache_class.return_value = mock_cache

        response = client.get("/api/v1/metrics")
        assert response.status_code == 200
        data = response.json()
        assert "total_requests" in data
        assert "successful_requests" in data
        assert "failed_requests" in data
        assert "average_response_time" in data
        assert "cache_hit_rate" in data
        assert "memory_usage" in data
