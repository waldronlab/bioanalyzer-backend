"""
BioAnalyzer Backend API - Standalone FastAPI Application
========================================================

This is the main FastAPI application for the BioAnalyzer Backend.
It provides REST API endpoints for BioAnaler without
frontend dependencies.
"""
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import logging
import os
import sys

# Add the project root to Python path
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

# Import routers
from app.api.routers import bugsigdb_analysis, system

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Create FastAPI application
app = FastAPI(
    title="BioAnalyzer Backend API",
    description="""
    **BioAnalyzer Backend** - A specialized AI-powered API for analyzing scientific papers for BugSigDB curation readiness.
    
    ## Core Functionality
    
    This API focuses on analyzing papers for **6 essential BugSigDB curation fields**:
    
    1. **Host Species** - What organism is being studied (e.g., Human, Mouse, Rat)
    2. **Body Site** - Where the microbiome sample was collected (e.g., Gut, Oral, Skin)
    3. **Condition** - What disease/treatment/exposure is being studied
    4. **Sequencing Type** - What molecular method was used (e.g., 16S, metagenomics)
    5. **Taxa Level** - What taxonomic level was analyzed (e.g., phylum, genus, species)
    6. **Sample Size** - Number of samples analyzed
    
    ## Analysis Results
    
    For each field, the AI provides:
    - **Status**: PRESENT, PARTIALLY_PRESENT, or ABSENT
    - **Value**: The extracted information
    - **Confidence**: AI confidence score (0.0-1.0)
    - **Reason if Missing**: Why the field is not present
    
    ## Endpoints
    
    - **Paper Analysis**: Analyze papers by PMID for the 6 essential fields
    - **Field Information**: Get details about the 6 essential fields
    - **System Health**: Health checks and system status
    
    ## Usage
    
    This is a standalone backend API. Use the CLI tool or integrate with your own frontend.
    """,
    version="1.0.0",
    contact={
        "name": "BioAnalyzer Team",
        "url": "https://github.com/your-repo/bioanalyzer-backend",
    },
    license_info={
        "name": "MIT",
        "url": "https://opensource.org/licenses/MIT",
    },
    tags_metadata=[
        {
            "name": "BugSigDB Analysis",
            "description": "Core endpoints for analyzing papers for the 6 essential BugSigDB fields."
        },
        {
            "name": "System",
            "description": "System endpoints for health checks, configuration, and metrics."
        }
    ]
)

# Configure CORS - Allow all origins for API usage
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Configure appropriately for production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include routers
app.include_router(bugsigdb_analysis.router)
app.include_router(system.router)

# Root endpoint
@app.get("/")
async def root():
    """API root endpoint with basic information."""
    return {
        "message": "BioAnalyzer Backend API",
        "version": "1.0.0",
        "description": "AI-powered Curatable Signature analysis API",
        "documentation": "/docs",
        "health_check": "/health",
        "metrics": "/metrics"
    }


# Health check endpoint (duplicate for backward compatibility)
@app.get("/health")
async def health_check():
    """Health check endpoint for backward compatibility."""
    from app.api.routers.system import health_check as system_health_check
    return await system_health_check()


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
