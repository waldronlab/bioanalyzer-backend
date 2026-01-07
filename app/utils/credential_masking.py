"""
Credential masking utility for secure logging.
"""

import re
from typing import Optional


API_KEY_ENV_VARS = {
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
    "password",
    "passwd",
    "pwd",
}


def mask_credential(value: Optional[str], show_last: int = 4) -> str:
    """
    Mask a credential value, showing only the last N characters.

    Short or empty values are fully masked as "****".
    """
    if not value:
        return "****"

    value = str(value).strip()

    if len(value) <= show_last:
        return "****"

    return "****" + value[-show_last:]


def mask_string(text: str, show_last: int = 4) -> str:
    """
    Mask common credential patterns inside free text.
    """
    if not isinstance(text, str):
        return str(text) if text is not None else ""

    patterns = [
        r"(AIza[0-9A-Za-z\-_]{15,})",
        r"(sk-[0-9A-Za-z]{10,})",
        r"(Bearer\s+[A-Za-z0-9\-\._]+)",
        r"([A-Za-z0-9_\-]{20,})",
    ]

    def replacer(match):
        return mask_credential(match.group(0), show_last)

    masked = text
    for pattern in patterns:
        masked = re.sub(pattern, replacer, masked, flags=re.IGNORECASE)

    return masked


def mask_dict(data: dict, keys_to_mask: Optional[list] = None) -> dict:
    """
    Mask sensitive values in a dictionary.
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
    Create a safe log message by masking credentials.
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
