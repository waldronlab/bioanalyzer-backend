"""FastAPI application for BioAnalyzer Package API."""

import logging
from typing import Dict

from fastapi import FastAPI

from app.api.models.api_models import HealthResponse
from app.api.routers import (
    bugsigdb_analysis,
    bugsigdb_analysis_v2,
    system,
    study_analysis,
)
from app.api.middleware.rate_limit import RateLimitMiddleware
from app.api.middleware.request_id import RequestIDMiddleware

from app.core.lifespan import lifespan
from app.core.exceptions import register_exception_handlers

from app.utils.config import (
    CORS_ORIGINS,
    ENABLE_RATE_LIMITING,
    RATE_LIMIT_PER_MINUTE,
    ENABLE_REQUEST_ID,
    ENVIRONMENT,
    setup_logging,
)

from fastapi.middleware.cors import CORSMiddleware

setup_logging()

logger = logging.getLogger(__name__)

app = FastAPI(
    title="BioAnalyzer Package API",
    description="API for analyzing scientific papers and extracting BugSigDB curation fields.",
    version="1.0.0",
    lifespan=lifespan,
    contact={
        "name": "BioAnalyzer Team",
        "url": "https://github.com/your-repo/bioanalyzer-package",
    },
    license_info={
        "name": "MIT",
        "url": "https://opensource.org/licenses/MIT",
    },
    tags_metadata=[
        {
            "name": "BugSigDB Analysis",
            "description": "Core endpoints for analyzing papers for the essential BugSigDB curation fields.",
        },
        {
            "name": "System",
            "description": "System endpoints for health checks, configuration, and metrics.",
        },
    ],
)

# Register centralized exception handling
register_exception_handlers(app)

app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS if ENVIRONMENT == "production" else ["*"],
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["*"],
    expose_headers=[
        "X-Request-ID",
        "X-RateLimit-Limit",
        "X-RateLimit-Remaining",
    ],
)

if ENABLE_REQUEST_ID:
    app.add_middleware(RequestIDMiddleware)

if ENABLE_RATE_LIMITING:
    app.add_middleware(
        RateLimitMiddleware,
        requests_per_minute=RATE_LIMIT_PER_MINUTE,
        enabled=ENABLE_RATE_LIMITING,
    )
    logger.info(
        f"Rate limiting enabled: {RATE_LIMIT_PER_MINUTE} requests/minute"
    )


app.include_router(bugsigdb_analysis.router)
app.include_router(bugsigdb_analysis_v2.router)
app.include_router(study_analysis.router)
app.include_router(system.router)


@app.get("/")
async def root() -> Dict[str, str]:
    """API root endpoint."""
    return {
        "message": "BioAnalyzer Package API",
        "version": "1.0.0",
        "description": "AI-powered Curatable Signature analysis API",
        "documentation": "/docs",
        "health_check": "/health",
        "metrics": "/metrics",
    }


@app.get("/health")
async def health_check() -> HealthResponse:
    """Health check endpoint."""
    from app.api.routers.system import health_check as system_health_check

    return await system_health_check()


if __name__ == "__main__":
    import uvicorn

    # Binding to 0.0.0.0 is required for containerized deployment
    uvicorn.run(app, host="0.0.0.0", port=8000)  # nosec B104