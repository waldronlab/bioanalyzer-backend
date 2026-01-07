"""
Tests for performance logger in app/utils/performance_logger.py
"""

import pytest
import tempfile
import os
from unittest.mock import patch, MagicMock
from app.utils.performance_logger import PerformanceLogger, perf_logger


class TestPerformanceLogger:
    """Tests for PerformanceLogger class."""

    def test_init(self):
        """Test logger initialization."""
        logger = PerformanceLogger()
        assert logger is not None
        assert logger.logger is not None

    def test_log_pmid_query_start(self):
        """Test logging PMID query start."""
        logger = PerformanceLogger()
        # Should not raise exception
        logger.log_pmid_query_start(
            "12345678", user_agent="Test", ip_address="127.0.0.1"
        )

    def test_log_pmid_query_start_minimal(self):
        """Test logging PMID query start with minimal params."""
        logger = PerformanceLogger()
        logger.log_pmid_query_start("12345678")

    def test_log_pmid_query_end_success(self):
        """Test logging PMID query end with success."""
        logger = PerformanceLogger()
        logger.log_pmid_query_end("12345678", duration=1.5, success=True, cached=False)

    def test_log_pmid_query_end_failure(self):
        """Test logging PMID query end with failure."""
        logger = PerformanceLogger()
        logger.log_pmid_query_end(
            "12345678", duration=2.0, success=False, error="Test error"
        )

    def test_log_pmid_query_end_cached(self):
        """Test logging PMID query end with cached result."""
        logger = PerformanceLogger()
        logger.log_pmid_query_end("12345678", duration=0.1, success=True, cached=True)

    def test_log_api_call_success(self):
        """Test logging successful API call."""
        logger = PerformanceLogger()
        logger.log_api_call(
            "pubmed", "fetch_metadata", "12345678", duration=0.5, success=True
        )

    def test_log_api_call_failure(self):
        """Test logging failed API call."""
        logger = PerformanceLogger()
        logger.log_api_call(
            "gemini",
            "analyze",
            "12345678",
            duration=1.0,
            success=False,
            error="Timeout",
        )

    def test_log_cache_operation(self):
        """Test logging cache operation."""
        logger = PerformanceLogger()
        logger.log_cache_operation(
            "STORE", "12345678", "analysis", duration=0.01, success=True
        )

    def test_log_cache_operation_failure(self):
        """Test logging failed cache operation."""
        logger = PerformanceLogger()
        logger.log_cache_operation(
            "GET", "12345678", "metadata", duration=0.02, success=False
        )

    def test_log_analysis_step(self):
        """Test logging analysis step."""
        logger = PerformanceLogger()
        logger.log_analysis_step("12345678", "field_extraction", duration=0.5)

    def test_log_analysis_step_with_details(self):
        """Test logging analysis step with details."""
        logger = PerformanceLogger()
        details = {"field": "host_species", "confidence": 0.95}
        logger.log_analysis_step(
            "12345678", "field_extraction", duration=0.5, details=details
        )

    def test_log_performance_metrics(self):
        """Test logging performance metrics."""
        logger = PerformanceLogger()
        metrics = {
            "total_time": 2.5,
            "api_calls": 3,
            "cache_hits": 2,
            "cache_misses": 1,
        }
        logger.log_performance_metrics("12345678", metrics)

    def test_log_error(self):
        """Test logging error."""
        logger = PerformanceLogger()
        error = ValueError("Test error message")
        logger.log_error("12345678", error, context="test_context")

    def test_log_error_without_context(self):
        """Test logging error without context."""
        logger = PerformanceLogger()
        error = Exception("Another test error")
        logger.log_error("12345678", error)


class TestGlobalPerfLogger:
    """Tests for global perf_logger instance."""

    def test_perf_logger_exists(self):
        """Test that global perf_logger instance exists."""
        assert perf_logger is not None
        assert isinstance(perf_logger, PerformanceLogger)

    def test_perf_logger_methods(self):
        """Test that global perf_logger has all methods."""
        assert hasattr(perf_logger, "log_pmid_query_start")
        assert hasattr(perf_logger, "log_pmid_query_end")
        assert hasattr(perf_logger, "log_api_call")
        assert hasattr(perf_logger, "log_cache_operation")
        assert hasattr(perf_logger, "log_analysis_step")
        assert hasattr(perf_logger, "log_performance_metrics")
        assert hasattr(perf_logger, "log_error")

    def test_perf_logger_get_metrics(self):
        """Test getting metrics from perf_logger."""
        # The get_metrics method should exist and return a dict
        if hasattr(perf_logger, "get_metrics"):
            metrics = perf_logger.get_metrics()
            assert isinstance(metrics, dict)


class TestPerformanceLoggerIntegration:
    """Integration tests for performance logger."""

    def test_full_query_logging_flow(self):
        """Test complete logging flow for a query."""
        logger = PerformanceLogger()

        # Start query
        logger.log_pmid_query_start(
            "12345678", user_agent="Test", ip_address="127.0.0.1"
        )

        # Log API calls
        logger.log_api_call(
            "pubmed", "fetch_metadata", "12345678", duration=0.3, success=True
        )
        logger.log_api_call("gemini", "analyze", "12345678", duration=1.2, success=True)

        # Log cache operations
        logger.log_cache_operation(
            "STORE", "12345678", "analysis", duration=0.01, success=True
        )

        # Log analysis steps
        logger.log_analysis_step("12345678", "field_extraction", duration=0.5)
        logger.log_analysis_step("12345678", "validation", duration=0.2)

        # End query
        logger.log_pmid_query_end("12345678", duration=2.0, success=True, cached=False)

        # Log metrics
        metrics = {
            "total_time": 2.0,
            "api_calls": 2,
            "cache_operations": 1,
            "analysis_steps": 2,
        }
        logger.log_performance_metrics("12345678", metrics)

    def test_error_logging_flow(self):
        """Test error logging flow."""
        logger = PerformanceLogger()

        # Start query
        logger.log_pmid_query_start("12345678")

        # Log failed API call
        logger.log_api_call(
            "pubmed",
            "fetch_metadata",
            "12345678",
            duration=5.0,
            success=False,
            error="Timeout",
        )

        # Log error
        error = Exception("Failed to fetch paper")
        logger.log_error("12345678", error, context="metadata_retrieval")

        # End query with failure
        logger.log_pmid_query_end(
            "12345678", duration=5.0, success=False, error="Timeout"
        )
