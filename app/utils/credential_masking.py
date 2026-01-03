"""
Credential masking utility for secure logging.

This module provides functions to mask sensitive credentials (API keys, tokens, etc.)
in logs and error messages to prevent security vulnerabilities.
"""

import re
from typing import Optional, Union


# Common API key patterns to detect and mask
API_KEY_PATTERNS = [
    r'api[_-]?key["\']?\s*[:=]\s*["\']?([a-zA-Z0-9_\-]{20,})["\']?',  # api_key: "value"
    r'apikey["\']?\s*[:=]\s*["\']?([a-zA-Z0-9_\-]{20,})["\']?',  # apikey: "value"
    r'["\']?([a-zA-Z0-9_\-]{32,})["\']?',  # Long alphanumeric strings (potential keys)
    r'Bearer\s+([a-zA-Z0-9_\-\.]+)',  # Bearer tokens
    r'token["\']?\s*[:=]\s*["\']?([a-zA-Z0-9_\-]{20,})["\']?',  # token: "value"
]

# Known API key environment variable names
API_KEY_ENV_VARS = [
    'GEMINI_API_KEY',
    'OPENAI_API_KEY',
    'ANTHROPIC_API_KEY',
    'NCBI_API_KEY',
    'API_KEY',
    'SECRET_KEY',
    'ACCESS_TOKEN',
    'AUTH_TOKEN',
]


def mask_credential(value: Optional[str], show_last: int = 4) -> str:
    """
    Mask a credential value, showing only the last N characters.
    
    Args:
        value: The credential value to mask
        show_last: Number of characters to show at the end (default: 4)
        
    Returns:
        Masked credential string (e.g., "****1234" for "abcdef1234")
        
    Examples:
        >>> mask_credential("AIzaSyD1234567890abcdef")
        '****cdef'
        >>> mask_credential("sk-1234567890abcdef")
        '****cdef'
        >>> mask_credential(None)
        '****'
        >>> mask_credential("")
        '****'
        >>> mask_credential("short")
        '****'
    """
    if not value or not isinstance(value, str):
        return "****"
    
    value = value.strip()
    
    # For very short values, just mask everything
    if len(value) <= show_last:
        return "****"
    
    # Show only the last N characters
    masked = "*" * max(4, len(value) - show_last) + value[-show_last:]
    return masked


def mask_string(text: str, show_last: int = 4) -> str:
    """
    Mask all potential credentials found in a text string.
    
    This function searches for common API key patterns and masks them.
    
    Args:
        text: The text string that may contain credentials
        show_last: Number of characters to show at the end of masked values
        
    Returns:
        Text with all potential credentials masked
        
    Examples:
        >>> mask_string("Error: API key AIzaSyD1234567890abcdef is invalid")
        'Error: API key ****cdef is invalid'
        >>> mask_string("api_key=sk-1234567890abcdef")
        'api_key=****cdef'
    """
    if not text or not isinstance(text, str):
        return str(text) if text is not None else ""
    
    masked_text = text
    
    # Mask known API key patterns
    for pattern in API_KEY_PATTERNS:
        def replace_match(match):
            full_match = match.group(0)
            # Try to extract the key value
            if match.lastindex and match.group(1):
                key_value = match.group(1)
                masked_value = mask_credential(key_value, show_last)
                # Replace the key value in the original match
                return full_match.replace(key_value, masked_value)
            return "****"
        
        masked_text = re.sub(pattern, replace_match, masked_text, flags=re.IGNORECASE)
    
    # Also mask any environment variable values that might be in the text
    for env_var in API_KEY_ENV_VARS:
        # Pattern: ENV_VAR=value or ENV_VAR: value
        env_pattern = rf'{re.escape(env_var)}\s*[:=]\s*([a-zA-Z0-9_\-\.]+)'
        def replace_env(match):
            if match.lastindex and match.group(1):
                key_value = match.group(1)
                masked_value = mask_credential(key_value, show_last)
                return match.group(0).replace(key_value, masked_value)
            return match.group(0)
        
        masked_text = re.sub(env_pattern, replace_env, masked_text, flags=re.IGNORECASE)
    
    return masked_text


def mask_dict(data: dict, keys_to_mask: Optional[list] = None) -> dict:
    """
    Mask sensitive values in a dictionary.
    
    Args:
        data: Dictionary that may contain sensitive values
        keys_to_mask: List of keys to mask. If None, uses default list of common key names.
        
    Returns:
        New dictionary with sensitive values masked
        
    Examples:
        >>> mask_dict({"api_key": "secret123", "name": "test"})
        {'api_key': '****t123', 'name': 'test'}
    """
    if keys_to_mask is None:
        keys_to_mask = [
            'api_key', 'apikey', 'api-key',
            'api_secret', 'secret', 'secret_key',
            'token', 'access_token', 'auth_token',
            'password', 'passwd', 'pwd',
            'gemini_api_key', 'openai_api_key', 'anthropic_api_key', 'ncbi_api_key',
            'GEMINI_API_KEY', 'OPENAI_API_KEY', 'ANTHROPIC_API_KEY', 'NCBI_API_KEY',
        ]
    
    masked_data = {}
    for key, value in data.items():
        # Check if this key should be masked
        key_lower = str(key).lower()
        should_mask = any(mask_key.lower() in key_lower for mask_key in keys_to_mask)
        
        if should_mask and isinstance(value, str):
            masked_data[key] = mask_credential(value)
        elif isinstance(value, dict):
            masked_data[key] = mask_dict(value, keys_to_mask)
        elif isinstance(value, str) and len(value) > 20:
            # Mask long strings that might be credentials
            masked_data[key] = mask_credential(value)
        else:
            masked_data[key] = value
    
    return masked_data


def safe_log_message(message: str, *args, **kwargs) -> str:
    """
    Create a safe log message by masking any credentials in the message and arguments.
    
    Args:
        message: Log message format string
        *args: Positional arguments for the message
        *kwargs: Keyword arguments for the message
        
    Returns:
        Safe log message with all credentials masked
        
    Examples:
        >>> safe_log_message("API key %s failed", "AIzaSyD1234567890abcdef")
        'API key ****cdef failed'
    """
    # Format the message first
    try:
        formatted = message % args if args else message
        if kwargs:
            formatted = formatted.format(**kwargs)
    except (ValueError, KeyError, TypeError):
        # If formatting fails, just use the message as-is
        formatted = str(message)
    
    # Mask any credentials in the formatted message
    return mask_string(formatted)


def mask_exception_message(exception: Exception) -> str:
    """
    Get a safe string representation of an exception, masking any credentials.
    
    Args:
        exception: Exception object
        
    Returns:
        Safe exception message with credentials masked
        
    Examples:
        >>> exc = ValueError("API key AIzaSyD1234567890abcdef is invalid")
        >>> mask_exception_message(exc)
        'API key ****cdef is invalid'
    """
    error_msg = str(exception)
    return mask_string(error_msg)

