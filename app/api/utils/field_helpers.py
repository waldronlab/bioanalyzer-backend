"""Helper functions for field endpoints."""

from fastapi import HTTPException
from app.api.utils.constants import ESSENTIAL_FIELDS_INFO, STATUS_VALUES


def get_fields_response(api_version: str = "v1") -> dict:
    """Get essential fields response."""
    response = {
        "essential_fields": ESSENTIAL_FIELDS_INFO,
        "status_values": STATUS_VALUES,
    }
    if api_version == "v2":
        response["api_version"] = "v2"
    return response


def get_field_details_response(field_name: str, api_version: str = "v1") -> dict:
    """Get field details response."""
    normalized_name = field_name.strip().lower()
    if normalized_name not in ESSENTIAL_FIELDS_INFO:
        raise HTTPException(
            status_code=404,
            detail=f"Field '{field_name}' is not one of the 6 essential BugSigDB fields",
        )

    field_details = ESSENTIAL_FIELDS_INFO[normalized_name].copy()
    field_details["field_key"] = normalized_name

    response = {"field": field_details, "status_values": STATUS_VALUES}
    if api_version == "v2":
        response["api_version"] = "v2"
    return response
