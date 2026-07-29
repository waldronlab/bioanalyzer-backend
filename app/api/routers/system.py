"""System endpoints for health checks, configuration, and metrics."""

import logging
import time
from typing import Any, Dict, Optional

import psutil
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import RedirectResponse

from app.api.dependencies import (
    get_pubmed_retriever,
    get_unified_qa,
    get_unified_qa_optional,
)
from app.api.models.api_models import ConfigResponse, HealthResponse, MetricsResponse
from app.api.utils.api_utils import get_current_timestamp
from app.core.exceptions import log_masked_exception
from app.models.unified_qa import UnifiedQA
from app.services.data_retrieval import PubMedRetriever
from app.services.system_service import SystemService, get_system_service
from app.utils.config import (
    ANALYSIS_TIMEOUT,
    API_TIMEOUT,
    AVAILABLE_MODELS,
    DEFAULT_MODEL,
    FRONTEND_TIMEOUT,
    GEMINI_TIMEOUT,
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/v1", tags=["System"])


def _serialize_model(obj: Any) -> Any:
    """Serialize a Pydantic v1/v2 model, dict, or plain object for a raw dict response."""
    if obj is None or isinstance(obj, dict):
        return obj
    if hasattr(obj, "model_dump"):
        return obj.model_dump()
    if hasattr(obj, "dict"):
        return obj.dict()
    return obj


# ---------------------------------------------------------------------
# Root Endpoint
# ---------------------------------------------------------------------


@router.get("/")
async def root() -> Any:
    """API root. Redirects to Swagger documentation."""
    return RedirectResponse(url="/docs")


# ---------------------------------------------------------------------
# Health Endpoint
# ---------------------------------------------------------------------


@router.get("/health")
async def health_check() -> HealthResponse:
    """Verify that the API is running."""
    try:
        return HealthResponse(
            status="healthy", timestamp=get_current_timestamp(), version="1.0.0"
        )
    except Exception as exc:
        log_masked_exception(exc, "Error in health check")
        return HealthResponse(
            status="unhealthy", timestamp=get_current_timestamp(), version="1.0.0"
        )


# ---------------------------------------------------------------------
# Configuration Endpoint
# ---------------------------------------------------------------------


@router.get("/config")
async def get_config() -> ConfigResponse:
    """Return public configuration values for API clients."""
    return ConfigResponse(
        available_models=AVAILABLE_MODELS,
        default_model=DEFAULT_MODEL,
        frontend_timeout=FRONTEND_TIMEOUT,
        gemini_timeout=GEMINI_TIMEOUT,
        analysis_timeout=ANALYSIS_TIMEOUT,
        api_timeout=API_TIMEOUT,
    )


# ---------------------------------------------------------------------
# Gemini Health Endpoint
# ---------------------------------------------------------------------


@router.get("/health/gemini")
async def gemini_health_check(
    qa_instance: Optional[UnifiedQA] = Depends(get_unified_qa_optional),
    service: SystemService = Depends(get_system_service),
) -> Dict[str, Any]:
    """Check Gemini API connectivity."""
    return await service.check_gemini_health(qa_instance)


# ---------------------------------------------------------------------
# NCBI Health Endpoint
# ---------------------------------------------------------------------


@router.get("/health/ncbi")
async def ncbi_health_check(
    pmid: str = "31452104",
    retriever: Optional[PubMedRetriever] = Depends(get_pubmed_retriever),
    service: SystemService = Depends(get_system_service),
) -> Dict[str, Any]:
    """Verify NCBI connectivity using a sample PMID."""
    return service.check_ncbi_health(retriever, pmid)


# ---------------------------------------------------------------------
# Metrics Endpoint
# ---------------------------------------------------------------------


@router.get("/metrics")
async def get_metrics(
    service: SystemService = Depends(get_system_service),
) -> MetricsResponse:
    """Return runtime performance metrics."""
    return service.get_metrics()


# ---------------------------------------------------------------------
# System Status Endpoint
# ---------------------------------------------------------------------


@router.get("/status")
async def get_system_status(
    qa_instance: Optional[UnifiedQA] = Depends(get_unified_qa_optional),
    service: SystemService = Depends(get_system_service),
) -> Dict[str, Any]:
    """Aggregate health, configuration, and metrics."""
    health = await health_check()
    config = await get_config()
    metrics = service.get_metrics()
    gemini = await service.check_gemini_health(qa_instance)

    uptime_seconds = time.time() - psutil.boot_time()
    overall_status = (
        health.status if hasattr(health, "status") else health.get("status", "unknown")
    )

    return {
        "overall_status": overall_status,
        "uptime_hours": round(uptime_seconds / 3600, 2),
        "health": _serialize_model(health),
        "config": _serialize_model(config),
        "metrics": _serialize_model(metrics),
        "gemini_api": gemini,
        "timestamp": get_current_timestamp(),
    }


# ---------------------------------------------------------------------
# Version Endpoint
# ---------------------------------------------------------------------


@router.get("/version")
async def get_version() -> Dict[str, Any]:
    """Return runtime version information."""
    import sys  # deferred: keeps the (slow) torch import off the app's startup path

    import torch

    return {
        "application_version": "1.0.0",
        "python_version": sys.version,
        "torch_version": torch.__version__,
        "fastapi_version": "0.104.1",
        "pydantic_version": "2.5.0",
        "timestamp": get_current_timestamp(),
    }


# ---------------------------------------------------------------------
# Ping Endpoint
# ---------------------------------------------------------------------


@router.get("/ping")
async def ping() -> Dict[str, Any]:
    """Lightweight connectivity endpoint."""
    return {"message": "pong", "timestamp": get_current_timestamp()}


# ---------------------------------------------------------------------
# Question & Answer Endpoint
# ---------------------------------------------------------------------


@router.post("/qa")
async def ask_question(
    request: Dict[str, Any],
    qa_instance: UnifiedQA = Depends(get_unified_qa),
) -> Dict[str, Any]:
    """
    Ask a question using the configured AI backend (Paper-QA / Gemini).

    Request body: {"question": "<text>"}
    Response: {"answer": "...", "confidence": 0.92, "timestamp": "..."}
    """
    question = request.get("question", "").strip()
    if not question:
        raise HTTPException(status_code=400, detail="Question is required")

    logger.info("Q&A request: %s...", question[:100])

    response = await qa_instance.chat(question)
    answer = response.get("text", "")
    confidence = response.get("confidence", 0.8)

    if not answer or answer.strip().startswith("Error:"):
        raise HTTPException(
            status_code=500,
            detail="No answer generated. Please check GEMINI_API_KEY and try again.",
        )

    return {
        "answer": answer,
        "confidence": confidence,
        "timestamp": get_current_timestamp(),
    }
