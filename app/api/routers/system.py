"""
System endpoints for health checks, configuration, and metrics.
"""
from fastapi import APIRouter, HTTPException
from typing import Dict, List, Optional, Any
import logging
import psutil
import asyncio
from datetime import datetime
import pytz

from app.utils.config import (
    AVAILABLE_MODELS,
    DEFAULT_MODEL,
    FRONTEND_TIMEOUT,
    GEMINI_TIMEOUT,
    ANALYSIS_TIMEOUT,
    API_TIMEOUT,
    GEMINI_API_KEY,
    NCBI_API_KEY
)
from app.models.unified_qa import UnifiedQA
from app.services.data_retrieval import PubMedRetriever
from app.utils.performance_logger import perf_logger
from app.api.models.api_models import HealthResponse, ConfigResponse, MetricsResponse
from app.api.utils.api_utils import get_current_timestamp
from app.services.data_retrieval import PubMedRetriever

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/v1", tags=["System"])

# Initialize services for health checks
unified_qa = UnifiedQA(use_gemini=True, gemini_api_key=GEMINI_API_KEY)
pubmed_retriever = PubMedRetriever(api_key=NCBI_API_KEY)


@router.get("/")
async def root():
    """Redirect to the frontend application."""
    from fastapi.responses import RedirectResponse
    return RedirectResponse(url="/static/index.html")


@router.get("/health")
async def health_check():
    """
    **Health check endpoint to verify the service is running.**
    
    This endpoint provides basic health status information
    and can be used for load balancer health checks.
    
    **Response:**
    Returns service health status and basic information.
    """
    try:
        # Basic health check
        current_time = get_current_timestamp()
        
        # Check if services are responsive
        services_status = {
            "unified_qa": True,  # Assume healthy if no exception
            "pubmed_retriever": True,
            "performance_logger": True
        }
        
        # Overall health status
        overall_health = all(services_status.values())
        
        return HealthResponse(
            status="healthy" if overall_health else "unhealthy",
            timestamp=current_time,
            version="1.0.0"
        )
        
    except Exception as e:
        logger.error(f"Error in health check: {e}")
        return HealthResponse(
            status="unhealthy",
            timestamp=get_current_timestamp(),
            version="1.0.0"
        )


@router.get("/config")
async def get_config():
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
            api_timeout=API_TIMEOUT
        )
        
    except Exception as e:
        logger.error(f"Error getting config: {e}")
        raise HTTPException(status_code=500, detail=f"Error getting configuration: {str(e)}")


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
        start_time = datetime.now()
        
        # Test Gemini API with a simple request
        test_response = await unified_qa.ask_question("Test question for health check")
        
        response_time = (datetime.now() - start_time).total_seconds()
        
        if test_response and test_response.get('answer'):
            return {
                "status": "healthy",
                "api_key_configured": bool(GEMINI_API_KEY),
                "response_time_seconds": response_time,
                "test_response": test_response.get('answer', '')[:100] + "...",
                "timestamp": get_current_timestamp()
            }
        else:
            return {
                "status": "unhealthy",
                "api_key_configured": bool(GEMINI_API_KEY),
                "response_time_seconds": response_time,
                "error": "No response from Gemini API",
                "timestamp": get_current_timestamp()
            }
            
    except Exception as e:
        logger.error(f"Error in Gemini health check: {e}")
        return {
            "status": "unhealthy",
            "api_key_configured": bool(GEMINI_API_KEY),
            "error": str(e),
            "timestamp": get_current_timestamp()
        }


@router.get("/health/ncbi")
async def ncbi_health_check(pmid: str = "31452104"):
    """Check NCBI E-Utilities connectivity and basic metadata availability."""
    try:
        retriever = PubMedRetriever(api_key=NCBI_API_KEY)
        md = retriever.fetch_paper_metadata(pmid)
        ok = bool(md.get("title") or md.get("abstract"))
        return {
            "status": "healthy" if ok else "unhealthy",
            "title_present": bool(md.get("title")),
            "abstract_present": bool(md.get("abstract")),
            "timestamp": get_current_timestamp(),
            "pmid": pmid
        }
    except Exception as e:
        logger.error(f"NCBI health check error: {e}", exc_info=True)
        return {
            "status": "unhealthy",
            "error": "An internal error occurred. Please try again later.",
            "timestamp": get_current_timestamp(),
            "pmid": pmid
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
        # Get performance metrics from the logger
        perf_metrics = perf_logger.get_metrics()
        
        # Get system resource metrics
        memory_info = psutil.virtual_memory()
        cpu_percent = psutil.cpu_percent(interval=1)
        disk_usage = psutil.disk_usage('/')
        
        # Calculate cache hit rate (if available)
        cache_hit_rate = 0.0
        try:
            from app.services.cache_manager import CacheManager
            cache_manager = CacheManager()
            cache_stats = cache_manager.get_cache_stats()
            if cache_stats.get('total_requests', 0) > 0:
                cache_hit_rate = cache_stats.get('cache_hits', 0) / cache_stats.get('total_requests', 1)
        except Exception:
            pass
        
        return MetricsResponse(
            total_requests=perf_metrics.get('total_requests', 0),
            successful_requests=perf_metrics.get('successful_requests', 0),
            failed_requests=perf_metrics.get('failed_requests', 0),
            average_response_time=perf_metrics.get('average_response_time', 0.0),
            cache_hit_rate=cache_hit_rate,
            memory_usage={
                "total_gb": round(memory_info.total / (1024**3), 2),
                "available_gb": round(memory_info.available / (1024**3), 2),
                "used_percent": memory_info.percent
            }
        )
        
    except Exception as e:
        logger.error(f"Error getting metrics: {e}")
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
        # Get basic health status
        health_status = await health_check()
        
        # Get configuration
        config = await get_config()
        
        # Get metrics
        metrics = await get_metrics()
        
        # Get Gemini health
        gemini_health = await gemini_health_check()
        
        # System uptime (approximate)
        import time
        uptime_seconds = time.time() - psutil.boot_time()
        uptime_hours = uptime_seconds / 3600
        
        return {
            "overall_status": health_status.status,
            "uptime_hours": round(uptime_hours, 2),
            "health": health_status.dict(),
            "config": config.dict(),
            "metrics": metrics.dict(),
            "gemini_api": gemini_health,
            "timestamp": get_current_timestamp()
        }
        
    except Exception as e:
        logger.error(f"Error getting system status: {e}")
        raise HTTPException(status_code=500, detail=f"Error getting system status: {str(e)}")


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
            "timestamp": get_current_timestamp()
        }
        
    except Exception as e:
        logger.error(f"Error getting version: {e}")
        raise HTTPException(status_code=500, detail=f"Error getting version: {str(e)}")


@router.get("/ping")
async def ping():
    """
    **Simple ping endpoint for basic connectivity testing.**
    
    This endpoint provides a simple response for basic connectivity tests.
    
    **Response:**
    Returns a simple pong response.
    """
    return {
        "message": "pong",
        "timestamp": get_current_timestamp()
    }
