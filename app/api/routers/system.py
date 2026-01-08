"""System endpoints for health checks, configuration, and metrics."""

from fastapi import APIRouter, HTTPException
from typing import Dict, List, Optional, Any
import logging
import psutil
import asyncio
from datetime import datetime
import pytz
from app.utils.credential_masking import mask_exception_message

from app.utils.config import (
    AVAILABLE_MODELS,
    DEFAULT_MODEL,
    FRONTEND_TIMEOUT,
    GEMINI_TIMEOUT,
    ANALYSIS_TIMEOUT,
    API_TIMEOUT,
    GEMINI_API_KEY,
    NCBI_API_KEY,
)
from app.models.unified_qa import UnifiedQA
from app.services.data_retrieval import PubMedRetriever
from app.utils.performance_logger import perf_logger
from app.api.models.api_models import HealthResponse, ConfigResponse, MetricsResponse
from app.api.utils.api_utils import get_current_timestamp

# Export CacheManager for testing/mocking
try:
    from app.services.cache_manager import CacheManager
except ImportError:
    CacheManager = None

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/v1", tags=["System"])

_unified_qa: Optional[UnifiedQA] = None
_pubmed_retriever: Optional[PubMedRetriever] = None

def get_unified_qa() -> Optional[UnifiedQA]:
    """Get or initialize UnifiedQA instance."""
    global _unified_qa
    if _unified_qa is None:
        try:
            _unified_qa = UnifiedQA(use_gemini=True, gemini_api_key=GEMINI_API_KEY)
        except Exception as e:
            safe_error = mask_exception_message(e)
            logger.warning(f"Failed to initialize UnifiedQA: {safe_error}")
            _unified_qa = None
    return _unified_qa


# Export unified_qa for testing/mocking - allows @patch("app.api.routers.system.unified_qa")
# This is a simple module-level variable that can be mocked
unified_qa = None  # Will be initialized on first use via get_unified_qa()


def get_pubmed_retriever() -> Optional[PubMedRetriever]:
    """Get or initialize PubMedRetriever instance."""
    global _pubmed_retriever
    if _pubmed_retriever is None:
        try:
            _pubmed_retriever = PubMedRetriever(api_key=NCBI_API_KEY)
        except Exception as e:
            safe_error = mask_exception_message(e)
            logger.warning(f"Failed to initialize PubMedRetriever: {safe_error}")
            _pubmed_retriever = None
    return _pubmed_retriever


@router.get("/")
async def root() -> Any:
    """Redirect to the frontend application."""
    from fastapi.responses import RedirectResponse

    return RedirectResponse(url="/static/index.html")


@router.get("/health")
async def health_check() -> HealthResponse:
    """Health check endpoint to verify service is running."""
    try:
        current_time = get_current_timestamp()
        return HealthResponse(status="healthy", timestamp=current_time, version="1.0.0")

    except Exception as e:
        safe_error = mask_exception_message(e)
        logger.error(f"Error in health check: {safe_error}")
        return HealthResponse(
            status="unhealthy", timestamp=get_current_timestamp(), version="1.0.0"
        )


@router.get("/config")
async def get_config() -> ConfigResponse:
    """
    **Get configuration settings for the frontend.**

    This endpoint provides configuration information
    that the frontend needs to operate correctly.

    **Response:**
    Returns configuration settings including available models,
    timeouts, and other system parameters.
    """
    try:
        return ConfigResponse(
            available_models=AVAILABLE_MODELS,
            default_model=DEFAULT_MODEL,
            frontend_timeout=FRONTEND_TIMEOUT,
            gemini_timeout=GEMINI_TIMEOUT,
            analysis_timeout=ANALYSIS_TIMEOUT,
            api_timeout=API_TIMEOUT,
        )

    except Exception as e:
        safe_error = mask_exception_message(e)
        logger.error(f"Error getting config: {safe_error}")
        raise HTTPException(
            status_code=500, detail=f"Error getting configuration: {str(e)}"
        )


@router.get("/health/gemini")
async def gemini_health_check():
    """
    **Specific health check for Gemini API connectivity.**

    This endpoint tests the connection to the Gemini API
    to ensure it's available for analysis requests.

    **Response:**
    Returns Gemini API health status and response time.
    """
    try:
        # Use module-level unified_qa if available, otherwise get it
        if unified_qa is None:
            unified_qa = get_unified_qa()
        if unified_qa is None:
            return {
                "status": "unhealthy",
                "api_key_configured": bool(GEMINI_API_KEY),
                "error": "UnifiedQA service not initialized",
                "timestamp": get_current_timestamp(),
            }

        start_time = datetime.now()

        # Test Gemini API with a simple request
        test_response = await unified_qa.ask_question("Test question for health check")

        response_time = (datetime.now() - start_time).total_seconds()

        if test_response and test_response.get("answer"):
            return {
                "status": "healthy",
                "api_key_configured": bool(GEMINI_API_KEY),
                "response_time_seconds": response_time,
                "test_response": test_response.get("answer", "")[:100] + "...",
                "timestamp": get_current_timestamp(),
            }
        else:
            return {
                "status": "unhealthy",
                "api_key_configured": bool(GEMINI_API_KEY),
                "response_time_seconds": response_time,
                "error": "No response from Gemini API",
                "timestamp": get_current_timestamp(),
            }

    except Exception as e:
        safe_error = mask_exception_message(e)
        logger.error(f"Error in Gemini health check: {safe_error}")
        return {
            "status": "unhealthy",
            "api_key_configured": bool(GEMINI_API_KEY),
            "error": str(e),
            "timestamp": get_current_timestamp(),
        }


@router.get("/health/ncbi")
async def ncbi_health_check(pmid: str = "31452104"):
    """Check NCBI E-Utilities connectivity and basic metadata availability."""
    try:
        retriever = get_pubmed_retriever()
        if retriever is None:
            return {
                "status": "unhealthy",
                "error": "PubMedRetriever service not initialized",
                "timestamp": get_current_timestamp(),
                "pmid": pmid,
            }
        md = retriever.fetch_paper_metadata(pmid)
        ok = bool(md.get("title") or md.get("abstract"))
        return {
            "status": "healthy" if ok else "unhealthy",
            "title_present": bool(md.get("title")),
            "abstract_present": bool(md.get("abstract")),
            "timestamp": get_current_timestamp(),
            "pmid": pmid,
        }
    except Exception as e:
        safe_error = mask_exception_message(e)
        logger.error(
            f"NCBI health check error: {safe_error}", exc_info=False
        )  # Don't log full traceback to avoid credential exposure
        return {
            "status": "unhealthy",
            "error": "An internal error occurred. Please try again later.",
            "timestamp": get_current_timestamp(),
            "pmid": pmid,
        }


@router.get("/metrics")
async def get_metrics():
    """
    **Get system performance metrics.**

    This endpoint provides detailed performance metrics
    including request counts, response times, and system resources.

    **Response:**
    Returns comprehensive system metrics.
    """
    try:
        perf_metrics = perf_logger.get_metrics()

        memory_info = psutil.virtual_memory()
        cpu_percent = psutil.cpu_percent(interval=1)
        disk_usage = psutil.disk_usage("/")

        cache_hit_rate = 0.0
        try:
            from app.services.cache_manager import CacheManager

            cache_manager = CacheManager()
            cache_stats = cache_manager.get_cache_stats()
            if cache_stats.get("total_requests", 0) > 0:
                cache_hit_rate = cache_stats.get("cache_hits", 0) / cache_stats.get(
                    "total_requests", 1
                )
        except Exception:
            pass

        return MetricsResponse(
            total_requests=perf_metrics.get("total_requests", 0),
            successful_requests=perf_metrics.get("successful_requests", 0),
            failed_requests=perf_metrics.get("failed_requests", 0),
            average_response_time=perf_metrics.get("average_response_time", 0.0),
            cache_hit_rate=cache_hit_rate,
            memory_usage={
                "total_gb": round(memory_info.total / (1024**3), 2),
                "available_gb": round(memory_info.available / (1024**3), 2),
                "used_percent": memory_info.percent,
            },
        )

    except Exception as e:
        safe_error = mask_exception_message(e)
        logger.error(f"Error getting metrics: {safe_error}")
        raise HTTPException(status_code=500, detail=f"Error getting metrics: {str(e)}")


@router.get("/status")
async def get_system_status():
    """
    **Get comprehensive system status.**

    This endpoint provides a comprehensive overview of the system status,
    including all services, resources, and performance indicators.

    **Response:**
    Returns detailed system status information.
    """
    try:
        health_status = await health_check()

        config = await get_config()

        metrics = await get_metrics()

        gemini_health = await gemini_health_check()

        # System uptime (approximate)
        import time

        uptime_seconds = time.time() - psutil.boot_time()
        uptime_hours = uptime_seconds / 3600

        # Handle both Pydantic model and dict cases
        if isinstance(health_status, dict):
            overall_status = health_status.get("status", "unknown")
            health_dict = health_status
        else:
            overall_status = health_status.status
            health_dict = health_status.dict() if hasattr(health_status, "dict") else health_status.model_dump()

        return {
            "overall_status": overall_status,
            "uptime_hours": round(uptime_hours, 2),
            "health": health_dict,
            "config": config.dict() if hasattr(config, "dict") else (config.model_dump() if hasattr(config, "model_dump") else config),
            "metrics": metrics.dict() if hasattr(metrics, "dict") else (metrics.model_dump() if hasattr(metrics, "model_dump") else metrics),
            "gemini_api": gemini_health,
            "timestamp": get_current_timestamp(),
        }

    except Exception as e:
        safe_error = mask_exception_message(e)
        logger.error(f"Error getting system status: {safe_error}")
        raise HTTPException(
            status_code=500, detail=f"Error getting system status: {str(e)}"
        )


@router.get("/version")
async def get_version():
    """
    **Get application version information.**

    This endpoint returns version information for the application
    and its dependencies.

    **Response:**
    Returns version information.
    """
    try:
        import sys
        import torch

        return {
            "application_version": "1.0.0",
            "python_version": sys.version,
            "torch_version": torch.__version__,
            "fastapi_version": "0.104.1",  # Update as needed
            "pydantic_version": "2.5.0",  # Update as needed
            "timestamp": get_current_timestamp(),
        }

    except Exception as e:
        safe_error = mask_exception_message(e)
        logger.error(f"Error getting version: {safe_error}")
        raise HTTPException(status_code=500, detail=f"Error getting version: {str(e)}")


@router.get("/ping")
async def ping():
    """
    **Simple ping endpoint for basic connectivity testing.**

    This endpoint provides a simple response for basic connectivity tests.

    **Response:**
    Returns a simple pong response.
    """
    return {"message": "pong", "timestamp": get_current_timestamp()}


@router.post("/qa")
async def ask_question(request: Dict[str, Any]):
    """
    **Ask a question and get an AI-powered answer.**

    This endpoint uses Paper-QA agent (or GeminiQA fallback) to answer questions.
    Questions can be about anything - general knowledge, scientific concepts, etc.

    **Request Body:**
    - `question` (str): The question to ask

    **Response:**
    - `answer` (str): The answer text
    - `confidence` (float): Confidence score (0.0-1.0)
    - `timestamp` (str): Response timestamp

    **Example:**
    ```json
    {
        "question": "What is the microbiome?"
    }
    ```
    """
    try:
        question = request.get("question", "").strip()

        if not question:
            raise HTTPException(status_code=400, detail="Question is required")

        logger.info(f"Q&A request: {question[:100]}...")

        # Get unified_qa instance - use local variable to avoid scope issues
        qa_instance = get_unified_qa()
        if qa_instance is None:
            raise HTTPException(
                status_code=503,
                detail="QA service not available. Check GEMINI_API_KEY configuration.",
            )
        response = await qa_instance.chat(question)

        answer = response.get("text", "")
        confidence = response.get("confidence", 0.8)

        # Check if answer is an error message
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

    except HTTPException:
        raise
    except Exception as e:
        safe_error = mask_exception_message(e)
        logger.error(f"Error in Q&A endpoint: {safe_error}")
        raise HTTPException(
            status_code=500, detail=f"Error processing question: {str(e)}"
        )
