"""Utility functions for API endpoints."""

from datetime import datetime
import pytz


def get_current_timestamp() -> str:
    """Get current timestamp in ISO format."""
    return datetime.now(pytz.UTC).isoformat()


def validate_pmid(pmid: str) -> str:
    """Validate and normalize PMID."""
    from fastapi import HTTPException

    if not pmid:
        raise HTTPException(status_code=400, detail="PMID cannot be empty")
    pmid = pmid.strip()
    if not pmid.isdigit():
        raise HTTPException(
            status_code=400,
            detail=f"Invalid PMID format: '{pmid}'. PMID must be numeric.",
        )
    if len(pmid) < 1 or len(pmid) > 20:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid PMID length: '{pmid}'. PMID should be 1-20 digits.",
        )
    return pmid
