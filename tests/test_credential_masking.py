"""
Tests for credential masking utility.

Tests that API keys and other sensitive credentials are properly masked
in logs and error messages.
"""

import pytest

from app.utils.credential_masking import (
    mask_credential,
    mask_dict,
    mask_exception_message,
    mask_string,
    safe_log_message,
)


class TestMaskCredential:
    """Test the mask_credential function."""

    def test_mask_long_api_key(self):
        """Test masking a long API key."""
        api_key = "AIzaSyD1234567890abcdefghijklmnopqrstuvwxyz"
        masked = mask_credential(api_key)
        assert masked.endswith("xyz")
        assert masked.startswith("****")
        assert len(masked) > 4
        assert api_key not in masked

    def test_mask_short_value(self):
        """Test masking a short value."""
        short_key = "short"
        masked = mask_credential(short_key)
        assert masked == "****"

    def test_mask_empty_string(self):
        """Test masking an empty string."""
        assert mask_credential("") == "****"

    def test_mask_none(self):
        """Test masking None value."""
        assert mask_credential(None) == "****"

    def test_mask_custom_show_last(self):
        """Test masking with custom show_last parameter."""
        api_key = "AIzaSyD1234567890abcdef"
        masked = mask_credential(api_key, show_last=6)
        assert masked.endswith("abcdef")
        assert len(masked) == len(api_key) - 6 + 6  # All but last 6 are masked

    def test_mask_openai_key(self):
        """Test masking OpenAI API key format."""
        openai_key = "sk-1234567890abcdefghijklmnopqrstuvwxyz"
        masked = mask_credential(openai_key)
        assert masked.endswith("xyz")
        assert "sk-" not in masked or masked.count("sk-") == 0  # Should be masked


class TestMaskString:
    """Test the mask_string function."""

    def test_mask_api_key_in_text(self):
        """Test masking API key found in text."""
        text = "Error: API key AIzaSyD1234567890abcdef is invalid"
        masked = mask_string(text)
        assert "AIzaSyD1234567890abcdef" not in masked
        assert "****" in masked or "cdef" in masked

    def test_mask_multiple_keys(self):
        """Test masking multiple API keys in text."""
        text = "Keys: AIzaSyD1234567890abcdef and sk-1234567890abcdef"
        masked = mask_string(text)
        assert "AIzaSyD1234567890abcdef" not in masked
        assert "sk-1234567890abcdef" not in masked

    def test_mask_env_var_format(self):
        """Test masking environment variable format."""
        text = "GEMINI_API_KEY=AIzaSyD1234567890abcdef"
        masked = mask_string(text)
        assert "AIzaSyD1234567890abcdef" not in masked

    def test_no_mask_regular_text(self):
        """Test that regular text is not masked."""
        text = "This is a regular error message without any API keys"
        masked = mask_string(text)
        assert masked == text

    def test_mask_bearer_token(self):
        """Test masking Bearer token format."""
        text = "Authorization: Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9"
        masked = mask_string(text)
        assert "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9" not in masked


class TestMaskDict:
    """Test the mask_dict function."""

    def test_mask_api_key_in_dict(self):
        """Test masking API key in dictionary."""
        data = {"api_key": "AIzaSyD1234567890abcdef", "name": "test", "other": "value"}
        masked = mask_dict(data)
        assert masked["api_key"] != data["api_key"]
        assert masked["api_key"].startswith("****")
        assert masked["name"] == "test"  # Non-sensitive keys unchanged
        assert masked["other"] == "value"

    def test_mask_nested_dict(self):
        """Test masking in nested dictionaries."""
        data = {"config": {"api_key": "AIzaSyD1234567890abcdef", "other": "value"}}
        masked = mask_dict(data)
        assert masked["config"]["api_key"] != data["config"]["api_key"]
        assert masked["config"]["other"] == "value"

    def test_mask_multiple_key_names(self):
        """Test masking various key name formats."""
        data = {"api_key": "key1", "API_KEY": "key2", "secret": "secret1", "token": "token1"}
        masked = mask_dict(data)
        assert masked["api_key"].startswith("****")
        assert masked["API_KEY"].startswith("****")
        assert masked["secret"].startswith("****")
        assert masked["token"].startswith("****")


class TestSafeLogMessage:
    """Test the safe_log_message function."""

    def test_safe_log_with_api_key(self):
        """Test creating safe log message with API key."""
        api_key = "AIzaSyD1234567890abcdef"
        message = safe_log_message("API key %s failed", api_key)
        assert api_key not in message
        assert "****" in message

    def test_safe_log_with_format_string(self):
        """Test safe log message with format string."""
        api_key = "AIzaSyD1234567890abcdef"
        message = safe_log_message("Error: API key {} is invalid", api_key)
        assert api_key not in message


class TestMaskExceptionMessage:
    """Test the mask_exception_message function."""

    def test_mask_exception_with_api_key(self):
        """Test masking exception message containing API key."""
        error_msg = "API key AIzaSyD1234567890abcdef is invalid"
        exc = ValueError(error_msg)
        masked = mask_exception_message(exc)
        assert "AIzaSyD1234567890abcdef" not in masked
        assert "invalid" in masked  # Non-sensitive parts should remain

    def test_mask_exception_without_credentials(self):
        """Test masking exception without credentials."""
        exc = ValueError("Regular error message")
        masked = mask_exception_message(exc)
        assert "Regular error message" in masked

    def test_mask_exception_with_env_var(self):
        """Test masking exception with environment variable."""
        error_msg = "GEMINI_API_KEY=AIzaSyD1234567890abcdef not found"
        exc = ValueError(error_msg)
        masked = mask_exception_message(exc)
        assert "AIzaSyD1234567890abcdef" not in masked


class TestRealWorldScenarios:
    """Test real-world scenarios where credentials might be exposed."""

    def test_error_message_with_full_key(self):
        """Test error message that might contain full API key."""
        error = "Authentication failed with key: AIzaSyD1234567890abcdef"
        masked = mask_string(error)
        assert "AIzaSyD1234567890abcdef" not in masked

    def test_log_message_with_key(self):
        """Test log message that might contain API key."""
        log_msg = "Request failed: {'api_key': 'AIzaSyD1234567890abcdef', 'status': 'error'}"
        masked = mask_string(log_msg)
        assert "AIzaSyD1234567890abcdef" not in masked

    def test_traceback_with_key(self):
        """Test traceback that might contain API key."""
        traceback_text = """
        File "test.py", line 10, in function
            api_key = "AIzaSyD1234567890abcdef"
        ValueError: Invalid API key
        """
        masked = mask_string(traceback_text)
        assert "AIzaSyD1234567890abcdef" not in masked
