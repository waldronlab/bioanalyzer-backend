"""
Credential masking utility for secure logging.

Safely masks API keys, tokens, and secrets without over-masking
scientific identifiers or normal text.
"""

import re
from typing import Optional, Iterable


# Environment / config keys that should always be masked
API_KEY_ENV_VARS: set[str] = {
    "gemini_api_key",
    "openai_api_key",
    "anthropic_api_key",
    "ncbi_api_key",
    "api_key",
    "apikey",
    "api-key",
    "api_secret",
    "secret",
    "secret_key",
    "token",
    "access_token",
    "auth_token",
    "authorization",
    "password",
    "passwd",
    "pwd",
}


def mask_credential(value: Optional[str], show_last: int = 4) -> str:
    """
    Mask a credential value while preserving total length.
    
    For very short values (<= 8 chars), return fixed "****" for security.
    For longer values, ensure at least 4 asterisks at the start, then show last N characters.
    """
    if not value:
        return "****"

    value = str(value)

    # For very short values (<= 8 chars), return fixed "****" for security
    # This prevents leaking any part of short secrets
    if len(value) <= 8:
        return "****"
    
    # If value is shorter than or equal to show_last, fully mask with fixed "****"
    if len(value) <= show_last:
        return "****"

    # For longer values, ensure at least 4 asterisks, then show last N characters
    # This ensures all masked values start with "****" for consistency
    masked_len = len(value) - show_last
    # Ensure minimum 4 asterisks
    if masked_len < 4:
        # If we need to show more than (len - 4) chars, just return "****"
        if show_last > len(value) - 4:
            return "****"
        # Otherwise, use 4 asterisks and show remaining chars
        return "****" + value[-(len(value) - 4):]
    
    return "*" * masked_len + value[-show_last:]


def mask_string(text: str, show_last: int = 4) -> str:
    """
    Mask credentials inside free text.

    Only masks:
    - Google API keys (AIza...)
    - OpenAI-style keys (sk-...)
    - Bearer tokens
    - key=value / key: value patterns
    """
    if not isinstance(text, str):
        return str(text) if text is not None else ""

    masked = text

    # 1. Explicit API key formats
    explicit_patterns = [
        r"(AIza[0-9A-Za-z\-_]{15,})",
        r"(sk-[0-9A-Za-z]{10,})",
    ]

    for pattern in explicit_patterns:
        masked = re.sub(
            pattern,
            lambda m: mask_credential(m.group(1), show_last),
            masked,
            flags=re.IGNORECASE,
        )

    # 2. Bearer tokens
    masked = re.sub(
        r"(Bearer\s+)([A-Za-z0-9\-\._]+)",
        lambda m: m.group(1) + mask_credential(m.group(2), show_last),
        masked,
        flags=re.IGNORECASE,
    )

    # 3. key=value or key: value patterns
    for key in API_KEY_ENV_VARS:
        pattern = rf"({re.escape(key)}\s*[:=]\s*)([A-Za-z0-9\-\._]+)"
        masked = re.sub(
            pattern,
            lambda m: m.group(1) + mask_credential(m.group(2), show_last),
            masked,
            flags=re.IGNORECASE,
        )

    return masked


def mask_dict(data: dict, keys_to_mask: Optional[Iterable[str]] = None) -> dict:
    """
    Recursively mask sensitive values in dictionaries.
    """
    if keys_to_mask is None:
        keys_to_mask = API_KEY_ENV_VARS

    normalized_keys = {k.lower() for k in keys_to_mask}
    masked = {}

    for key, value in data.items():
        key_lower = str(key).lower()

        if key_lower in normalized_keys and isinstance(value, str):
            masked[key] = mask_credential(value)
        elif isinstance(value, dict):
            masked[key] = mask_dict(value, keys_to_mask)
        else:
            masked[key] = value

    return masked


def safe_log_message(message: str, *args, **kwargs) -> str:
    """
    Format a log message and safely mask any credentials.
    """
    try:
        formatted = message % args if args else message
        if kwargs:
            formatted = formatted.format(**kwargs)
    except Exception:
        formatted = str(message)

    return mask_string(formatted)


def mask_exception_message(exception: Exception) -> str:
    """
    Mask credentials inside exception messages.
    """
    return mask_string(str(exception))
