"""
Simplified API router focused only on the 6 essential BugSigDB fields.
"""
from fastapi import APIRouter, HTTPException
import logging

from app.services.bugsigdb_analyzer import analyze_paper_simple

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/v1", tags=["BugSigDB Analysis"])


@router.get("/analyze/{pmid}")
async def analyze_paper(pmid: str):
    """
    Analyze a single paper for the 6 essential BugSigDB fields.
    
    **6 Essential Fields:**
    1. **host_species**: Host organism being studied
    2. **body_site**: Microbiome sample collection location  
    3. **condition**: Disease/treatment/exposure studied
    4. **sequencing_type**: Molecular method used
    5. **taxa_level**: Taxonomic level analyzed
    6. **sample_size**: Number of samples analyzed
    
    **Field Status Values:**
    - **PRESENT**: Information is complete and clear
    - **PARTIALLY_PRESENT**: Some information available but incomplete
    - **ABSENT**: Information is missing
    
    **Returns:**
    - Paper metadata (title, authors, journal, etc.)
    - Analysis results for each of the 6 fields
    - Status and confidence for each field
    """
    try:
        logger.info(f"Starting analysis for PMID: {pmid}")
        
        result = await analyze_paper_simple(pmid)
        if not result:
            raise HTTPException(status_code=404, detail=f"Analysis failed for PMID {pmid}")
        
        return result
        
    except Exception as e:
        logger.error(f"Error in analysis for PMID {pmid}: {e}")
        raise HTTPException(status_code=500, detail=f"Analysis error: {str(e)}")


@router.get("/fields")
async def get_essential_fields():
    """
    Get information about the 6 essential BugSigDB fields.
    """
    return {
        "essential_fields": {
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
        },
        "status_values": {
            "PRESENT": "Information is complete and clear",
            "PARTIALLY_PRESENT": "Some information available but incomplete", 
            "ABSENT": "Information is missing"
        }
    }
