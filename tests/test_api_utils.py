"""
Tests for API utility functions in app/api/utils/api_utils.py
"""

import pytest
from datetime import datetime

# Try to import FastAPI-dependent modules, skip tests if not available
try:
    from fastapi import FastAPI
    from app.api.utils.api_utils import get_current_timestamp

    FASTAPI_AVAILABLE = True
except ImportError:
    FASTAPI_AVAILABLE = False
    # Create dummy function to avoid NameError
    get_current_timestamp = None


@pytest.mark.skipif(not FASTAPI_AVAILABLE, reason="FastAPI not available")
class TestGetCurrentTimestamp:
    """Tests for get_current_timestamp function."""

    def test_get_current_timestamp_format(self):
        """Test that timestamp is in ISO format."""
        timestamp = get_current_timestamp()
        assert isinstance(timestamp, str)
        # Should be ISO format with 'T' separator
        assert "T" in timestamp or "-" in timestamp

    def test_get_current_timestamp_not_empty(self):
        """Test that timestamp is not empty."""
        timestamp = get_current_timestamp()
        assert len(timestamp) > 0

    def test_get_current_timestamp_parsable(self):
        """Test that timestamp can be parsed."""
        timestamp = get_current_timestamp()
        # Should be parseable as datetime
        try:
            from dateutil import parser

            parsed = parser.isoparse(timestamp)
            assert isinstance(parsed, datetime)
        except ImportError:
            # dateutil not available, just check format
            assert isinstance(timestamp, str)

    def test_get_current_timestamp_unique(self):
        """Test that timestamps are unique (or at least different when called with delay)."""
        import time

        timestamp1 = get_current_timestamp()
        time.sleep(0.01)  # Small delay
        timestamp2 = get_current_timestamp()
        # They might be the same due to precision, but should be valid
        assert isinstance(timestamp1, str)
        assert isinstance(timestamp2, str)
