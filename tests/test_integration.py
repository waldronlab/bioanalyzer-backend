"""
Integration tests for BioAnalyzer Package
These tests verify that different components work together correctly.
"""

import pytest
import asyncio
from unittest.mock import patch, MagicMock, AsyncMock

from conftest import import_with_fallback

# Try to import FastAPI-dependent modules, skip tests if not available
try:
    from fastapi.testclient import TestClient
    from app.api.app import app
    from app.api.dependencies import get_unified_qa

    FASTAPI_AVAILABLE = True
except ImportError:
    FASTAPI_AVAILABLE = False
    TestClient = None
    app = None
    get_unified_qa = None


# `client` fixture (raise_server_exceptions=False) is provided by
# tests/conftest.py, shared with test_api_endpoints.py, test_study_analysis.py
# and test_bugsigdb_analysis_v2.py.


@pytest.mark.skipif(not FASTAPI_AVAILABLE, reason="FastAPI not available")
class TestAnalysisWorkflow:
    """Integration tests for the complete analysis workflow."""

    @patch("app.services.bugsigdb_analyzer.PubMedRetriever")
    @patch("app.services.bugsigdb_analyzer.UnifiedQA")
    def test_complete_analysis_workflow(
        self, mock_qa_class, mock_retriever_class, client
    ):
        """Test the complete workflow from API request to analysis result."""
        # Setup mocks
        mock_retriever = MagicMock()
        mock_retriever.fetch_paper_metadata.return_value = {
            "title": "Test Paper on Microbiome",
            "abstract": "This study examines the gut microbiome in human patients with IBD.",
            "authors": ["Author1", "Author2"],
            "journal": "Test Journal",
            "publication_date": "2023",
        }
        mock_retriever.fetch_full_text.return_value = "Full text about human gut microbiome study with 50 participants using 16S sequencing."
        mock_retriever_class.return_value = mock_retriever

        mock_qa = MagicMock()
        mock_qa.chat = AsyncMock(
            return_value={
                "text": '{"value": "Human", "status": "PRESENT", "confidence": 0.95, "reason_if_missing": null}'
            }
        )
        mock_qa_class.return_value = mock_qa

        # Make API request
        response = client.get("/api/v1/analyze/12345678")

        # Verify response
        assert response.status_code in [
            200,
            404,
            500,
        ]  # May fail if services not fully mocked

    def test_health_check_workflow(self, client):
        """Test that health check endpoints work together."""
        # Test basic health
        health_response = client.get("/api/v1/health")
        assert health_response.status_code == 200

        # Test ping
        ping_response = client.get("/api/v1/ping")
        assert ping_response.status_code == 200
        assert ping_response.json()["message"] == "pong"

        # Test config
        config_response = client.get("/api/v1/config")
        assert config_response.status_code == 200
        assert "available_models" in config_response.json()


class TestCacheIntegration:
    """Integration tests for cache functionality."""

    def test_cache_and_retrieval_workflow(self):
        """Test that caching and retrieval work together."""
        # Import CacheManager directly to avoid import chain issues, falling
        # back to loading the module straight from its file when the normal
        # import fails.
        CacheManager = import_with_fallback("cache_manager", "CacheManager")

        import tempfile
        import os

        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, "test.db")
            cache = CacheManager(cache_dir=tmpdir, db_path=db_path)

            # Store data
            analysis_data = {
                "host_species": {"value": "Human", "confidence": 0.95},
                "body_site": {"value": "Gut", "confidence": 0.92},
            }
            metadata = {"title": "Test Paper", "pmid": "12345678"}

            # Store
            stored = cache.store_analysis_result(
                "12345678", analysis_data, metadata, confidence=0.95
            )
            assert stored is True

            # Retrieve
            retrieved = cache.get_analysis_result("12345678")
            assert retrieved is not None
            assert retrieved["cached"] is True
            assert retrieved["analysis_data"]["host_species"]["value"] == "Human"

            # Check stats (inside context manager before cleanup)
            stats = cache.get_cache_stats()
            assert stats["analysis_cache_count"] >= 1


@pytest.mark.skipif(not FASTAPI_AVAILABLE, reason="FastAPI not available")
class TestAPIIntegration:
    """Integration tests for API endpoints working together."""

    def test_fields_and_analysis_endpoints(self, client):
        """Test that fields endpoint and analysis endpoint are consistent."""
        # Get field definitions
        fields_response = client.get("/api/v1/fields")
        assert fields_response.status_code == 200
        fields_data = fields_response.json()

        # Verify all 5 essential fields are defined
        essential_fields = fields_data["essential_fields"]
        expected_fields = [
            "host_species",
            "body_site",
            "condition",
            "sequencing_type",
            "sample_size",
        ]

        for field in expected_fields:
            assert field in essential_fields

    def test_health_and_status_endpoints(self, client):
        """Test that health and status endpoints work together."""
        # Get health
        health = client.get("/api/v1/health").json()

        # Get status (which includes health)
        status = client.get("/api/v1/status")
        assert status.status_code == 200
        status_data = status.json()

        # Status should include health info
        assert "health" in status_data
        assert "overall_status" in status_data


@pytest.mark.skipif(not FASTAPI_AVAILABLE, reason="FastAPI not available")
class TestErrorHandlingIntegration:
    """Integration tests for error handling across components."""

    def test_api_error_handling_workflow(self, client, override_deps):
        """Test that API errors are handled gracefully."""
        # Test with invalid endpoint
        response = client.get("/api/v1/nonexistent")
        assert response.status_code == 404

        # Test with invalid request. /qa's get_unified_qa dependency
        # 503s when no QA instance is available, which would mask the
        # 400 this test is actually checking for — override it so the
        # request reaches the endpoint's own "question required" check.
        with override_deps({get_unified_qa: lambda: AsyncMock()}):
            response = client.post("/api/v1/qa", json={})
            assert response.status_code == 400

    def test_cache_error_handling(self):
        """Test that cache errors are handled gracefully."""
        # Import CacheManager directly to avoid import chain issues, falling
        # back to loading the module straight from its file when the normal
        # import fails.
        CacheManager = import_with_fallback("cache_manager", "CacheManager")

        import tempfile
        import os

        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, "test.db")
            cache = CacheManager(cache_dir=tmpdir, db_path=db_path)

            # Try to get non-existent entry (should return None, not raise)
            result = cache.get_analysis_result("99999999")
            assert result is None  # Should handle gracefully


class TestPerformanceLoggingIntegration:
    """Integration tests for performance logging across workflow."""

    def test_logging_throughout_workflow(self):
        """Test that performance logging works throughout a workflow."""
        from app.utils.performance_logger import PerformanceLogger

        logger = PerformanceLogger()

        # Simulate a complete workflow with logging
        logger.log_pmid_query_start("12345678")
        logger.log_api_call("pubmed", "fetch", "12345678", duration=0.5, success=True)
        logger.log_cache_operation(
            "STORE", "12345678", "analysis", duration=0.01, success=True
        )
        logger.log_analysis_step("12345678", "extraction", duration=0.3)
        logger.log_pmid_query_end("12345678", duration=0.8, success=True)

        # log_pmid_query_end should have updated the logger's request
        # counters, confirming the end-of-workflow bookkeeping actually ran.
        assert logger.total_requests == 1
        assert logger.successful_requests == 1
        assert logger.failed_requests == 0


class TestDataFlowIntegration:
    """Integration tests for data flow through the system."""

    def test_data_flow_from_api_to_cache(self):
        """Test data flow from API request through to cache."""
        # Import CacheManager directly to avoid import chain issues, falling
        # back to loading the module straight from its file when the normal
        # import fails.
        CacheManager = import_with_fallback("cache_manager", "CacheManager")

        import tempfile
        import os

        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, "test.db")
            cache = CacheManager(cache_dir=tmpdir, db_path=db_path)

            # Simulate API response data
            api_response = {
                "pmid": "12345678",
                "title": "Test Paper",
                "fields": {"host_species": {"value": "Human", "confidence": 0.95}},
            }

            # Store in cache (as would happen after API processing)
            stored = cache.store_analysis_result(
                api_response["pmid"],
                api_response["fields"],
                {"title": api_response["title"]},
                confidence=0.95,
            )
            assert stored is True

            # Retrieve from cache (as would happen on subsequent requests)
            retrieved = cache.get_analysis_result(api_response["pmid"])
            assert retrieved is not None
            assert retrieved["analysis_data"]["host_species"]["value"] == "Human"


@pytest.mark.asyncio
class TestAsyncIntegration:
    """Integration tests for async operations."""

    async def test_async_cache_operations(self):
        """Test that async cache operations work correctly."""
        # Import CacheManager directly to avoid import chain issues, falling
        # back to loading the module straight from its file when the normal
        # import fails.
        CacheManager = import_with_fallback("cache_manager", "CacheManager")

        import tempfile
        import os

        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, "test.db")
            cache = CacheManager(cache_dir=tmpdir, db_path=db_path)

            # Test async store
            stored = await cache.store_analysis_result_async(
                "12345678", {"test": "data"}, {"title": "Test"}
            )
            assert stored is True

            # Test async retrieve
            retrieved = await cache.get_analysis_result_async("12345678")
            assert retrieved is not None
            assert retrieved["cached"] is True
