"""API router for BugSigDB field analysis."""
from fastapi import APIRouter, HTTPException
import logging

from app.services.bugsigdb_analyzer import analyze_paper_simple

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/v1", tags=["BugSigDB Analysis"])

ESSENTIAL_FIELDS_INFO = {
    "host_species": {
        "name": "Host Species",
        "description": "The host organism being studied (e.g., Human, Mouse, Rat)",
        "required": True
    },
    "body_site": {
        "name": "Body Site", 
        "description": "Where the microbiome sample was collected (e.g., Gut, Oral, Skin)",
        "required": True
    },
    "condition": {
        "name": "Condition",
        "description": "What disease, treatment, or exposure is being studied",
        "required": True
    },
    "sequencing_type": {
        "name": "Sequencing Type",
        "description": "What molecular method was used (e.g., 16S, metagenomics)",
        "required": True
    },
    "taxa_level": {
        "name": "Taxa Level",
        "description": "What taxonomic level was analyzed (e.g., phylum, genus, species)",
        "required": True
    },
    "sample_size": {
        "name": "Sample Size",
        "description": "Number of samples or participants analyzed",
        "required": True
    }
}

STATUS_VALUES = {
    "PRESENT": "Information is complete and clear",
    "PARTIALLY_PRESENT": "Some information available but incomplete", 
    "ABSENT": "Information is missing"
}


def _validate_pmid(pmid: str) -> str:
    """Validate and normalize PMID."""
    if not pmid:
        raise HTTPException(status_code=400, detail="PMID cannot be empty")
    
    # Remove whitespace
    pmid = pmid.strip()
    
    # Validate format (should be numeric)
    if not pmid.isdigit():
        raise HTTPException(
            status_code=400,
            detail=f"Invalid PMID format: '{pmid}'. PMID must be numeric."
        )
    
    # Validate length (PMID is typically 8 digits, but can vary)
    if len(pmid) < 1 or len(pmid) > 20:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid PMID length: '{pmid}'. PMID should be 1-20 digits."
        )
    
    return pmid


async def _run_analysis(pmid: str):
    """Run analysis with validated PMID."""
    # Validate PMID
    pmid = _validate_pmid(pmid)
    
    logger.info(f"Starting analysis for PMID: {pmid}")
    result = await analyze_paper_simple(pmid)
    if not result:
        raise HTTPException(status_code=404, detail=f"Analysis failed for PMID {pmid}")
    return result


@router.get("/analyze/{pmid}")
async def analyze_paper(pmid: str):
    """Analyze paper for BugSigDB fields."""
    try:
        return await _run_analysis(pmid)
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error in analysis for PMID {pmid}: {e}")
        raise HTTPException(status_code=500, detail=f"Analysis error: {str(e)}")


@router.post("/analyze/{pmid}")
async def analyze_paper_post(pmid: str):
    """Analyze paper for BugSigDB fields (POST method)."""
    try:
        return await _run_analysis(pmid)
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error in analysis for PMID {pmid}: {e}")
        raise HTTPException(status_code=500, detail=f"Analysis error: {str(e)}")


@router.get("/fields")
async def get_essential_fields():
    """Get information about BugSigDB fields."""
    return {
        "essential_fields": ESSENTIAL_FIELDS_INFO,
        "status_values": STATUS_VALUES
    }


@router.get("/fields/{field_name}")
async def get_field_details(field_name: str):
    """Get details for a specific BugSigDB field."""
    normalized_name = field_name.strip().lower()
    if normalized_name not in ESSENTIAL_FIELDS_INFO:
        raise HTTPException(
            status_code=404,
            detail=f"Field '{field_name}' is not one of the 6 essential BugSigDB fields"
        )
    
    field_details = ESSENTIAL_FIELDS_INFO[normalized_name].copy()
    field_details["field_key"] = normalized_name
    
    return {
        "field": field_details,
        "status_values": STATUS_VALUES
    }
