"""
BioAnalyzer Backend API - Standalone FastAPI Application
========================================================

This is the main FastAPI application for the BioAnalyzer Backend.
It provides REST API endpoints for BioAnaler without
frontend dependencies.
"""
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.exceptions import RequestValidationError
import logging
import os
import sys
import traceback

# Add the project root to Python path
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

# Import routers
from app.api.routers import bugsigdb_analysis, bugsigdb_analysis_v2, system, study_analysis
from app.api.middleware.rate_limit import RateLimitMiddleware
from app.api.middleware.request_id import RequestIDMiddleware
from app.utils.config import (
    CORS_ORIGINS,
    ENABLE_RATE_LIMITING,
    RATE_LIMIT_PER_MINUTE,
    ENABLE_REQUEST_ID,
    ENVIRONMENT,
    setup_logging
)

# Setup logging
setup_logging()
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
    
    ## API Versions
    
    - **v1 API** (`/api/v1`): Original endpoints for backward compatibility
    - **v2 API** (`/api/v2`): Enhanced endpoints with RAG (Retrieval Augmented Generation) support
    
    ## Endpoints
    
    - **Paper Analysis**: Analyze papers by PMID for the 6 essential fields
      - v1: `/api/v1/analyze/{pmid}` - Basic analysis
      - v2: `/api/v2/analyze/{pmid}` - Analysis with RAG features (contextual summarization, chunk re-ranking)
    - **Field Information**: Get details about the 6 essential fields
    - **RAG Configuration**: Get and configure RAG settings (v2 only)
    - **System Health**: Health checks and system status
    
    ## RAG Features (v2 API)
    
    The v2 API includes advanced RAG features:
    - **Contextual Summarization**: Query-aware summaries of relevant text chunks
    - **Chunk Re-ranking**: Relevance-based ranking of chunks (keyword, LLM, or hybrid)
    - **Configurable Parameters**: Control summary length, quality, and re-ranking method
    
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

# Configure CORS - Production-ready with configurable origins
app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS if ENVIRONMENT == "production" else ["*"],
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["*"],
    expose_headers=["X-Request-ID", "X-RateLimit-Limit", "X-RateLimit-Remaining"],
)

# Add request ID middleware for request tracking
if ENABLE_REQUEST_ID:
    app.add_middleware(RequestIDMiddleware)

# Add rate limiting middleware
if ENABLE_RATE_LIMITING:
    app.add_middleware(
        RateLimitMiddleware,
        requests_per_minute=RATE_LIMIT_PER_MINUTE,
        enabled=ENABLE_RATE_LIMITING
    )
    logger.info(f"Rate limiting enabled: {RATE_LIMIT_PER_MINUTE} requests/minute")

# Include routers
app.include_router(bugsigdb_analysis.router)  # v1 API (backward compatibility)
app.include_router(bugsigdb_analysis_v2.router)  # v2 API (with RAG support)
app.include_router(study_analysis.router)
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


# Global exception handlers for production-ready error handling
@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    """Handle request validation errors."""
    logger.warning(f"Validation error: {exc.errors()}")
    return JSONResponse(
        status_code=422,
        content={
            "error": "Validation Error",
            "detail": exc.errors(),
            "request_id": getattr(request.state, "request_id", None)
        }
    )


@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    """Handle unexpected exceptions."""
    logger.error(
        f"Unhandled exception: {str(exc)}\n"
        f"Traceback: {traceback.format_exc()}\n"
        f"Request ID: {getattr(request.state, 'request_id', None)}"
    )
    
    # Don't expose internal errors in production
    if ENVIRONMENT == "production":
        detail = "An internal error occurred. Please try again later."
    else:
        detail = str(exc)
    
    return JSONResponse(
        status_code=500,
        content={
            "error": "Internal Server Error",
            "detail": detail,
            "request_id": getattr(request.state, "request_id", None)
        }
    )


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
