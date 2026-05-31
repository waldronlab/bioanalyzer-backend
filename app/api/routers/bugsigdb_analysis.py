"""API router for BugSigDB field analysis."""

from fastapi import APIRouter, HTTPException
import logging
from typing import Dict, Any
from app.utils.credential_masking import mask_exception_message
from app.api.utils.constants import ESSENTIAL_FIELDS_INFO, STATUS_VALUES
from app.services.bugsigdb_analyzer import analyze_paper_simple

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/v1", tags=["BugSigDB Analysis"])


async def _run_analysis(pmid: str, refresh: bool = False) -> Dict[str, Any]:
    """Run analysis with validated PMID."""
    from app.api.utils.api_utils import validate_pmid

    pmid = validate_pmid(pmid)
    logger.info(f"Starting analysis for PMID: {pmid}")
    result = await analyze_paper_simple(pmid, force_refresh=refresh)
    if not result:
        raise HTTPException(status_code=404, detail=f"Analysis failed for PMID {pmid}")
    return result


def _handle_analysis_error(pmid: str, e: Exception) -> None:
    """Handle analysis errors consistently."""
    safe_error = mask_exception_message(e)
    logger.error(f"Error in analysis for PMID {pmid}: {safe_error}")
    raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/analyze/{pmid}")
async def analyze_paper(pmid: str, refresh: bool = False) -> Dict[str, Any]:
    """Analyze paper for BugSigDB fields."""
    try:
        return await _run_analysis(pmid, refresh=refresh)
    except HTTPException:
        raise
    except Exception as e:
        _handle_analysis_error(pmid, e)


@router.post("/analyze/{pmid}")
async def analyze_paper_post(pmid: str, refresh: bool = False) -> Dict[str, Any]:
    """Analyze paper for BugSigDB fields (POST method)."""
    try:
        return await _run_analysis(pmid, refresh=refresh)
    except HTTPException:
        raise
    except Exception as e:
        _handle_analysis_error(pmid, e)


@router.get("/fields")
async def get_essential_fields():
    """Get information about BugSigDB fields."""
    from app.api.utils.field_helpers import get_fields_response

    return get_fields_response("v1")


@router.get("/fields/{field_name}")
async def get_field_details(field_name: str):
    """Get details for a specific BugSigDB field."""
    from app.api.utils.field_helpers import get_field_details_response

    return get_field_details_response(field_name, "v1")
