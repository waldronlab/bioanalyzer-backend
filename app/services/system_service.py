import logging
from datetime import datetime
from typing import Any, Dict, Optional

import psutil

from app.api.models.api_models import MetricsResponse
from app.api.utils.api_utils import get_current_timestamp
from app.core.exceptions import log_masked_exception
from app.models.unified_qa import UnifiedQA
from app.services.data_retrieval import PubMedRetriever
from app.utils.config import GEMINI_API_KEY
from app.utils.performance_logger import perf_logger

try:
    from app.services.cache_manager import CacheManager
except ImportError:
    CacheManager = None

logger = logging.getLogger(__name__)


def _unhealthy(*, error: str, **extra: Any) -> Dict[str, Any]:
    """Standardized unhealthy response payload."""
    return {
        "status": "unhealthy",
        "error": error,
        "timestamp": get_current_timestamp(),
        **extra,
    }


class SystemService:
    """Diagnostics for Gemini/NCBI connectivity and runtime metrics."""

    async def check_gemini_health(self, qa: Optional[UnifiedQA]) -> Dict[str, Any]:
        if qa is None:
            return _unhealthy(
                error="UnifiedQA service not initialized",
                api_key_configured=bool(GEMINI_API_KEY),
            )

        start_time = datetime.now()
        try:
            test_response = await qa.ask_question("Test question for health check")
        except Exception as exc:
            log_masked_exception(exc, "Error in Gemini health check")
            return _unhealthy(
                error="An internal error occurred. Please try again later.",
                api_key_configured=bool(GEMINI_API_KEY),
            )
        response_time = (datetime.now() - start_time).total_seconds()

        if test_response and test_response.get("answer"):
            return {
                "status": "healthy",
                "api_key_configured": bool(GEMINI_API_KEY),
                "response_time_seconds": response_time,
                "test_response": test_response.get("answer", "")[:100] + "...",
                "timestamp": get_current_timestamp(),
            }

        return _unhealthy(
            error="No response from Gemini API",
            api_key_configured=bool(GEMINI_API_KEY),
            response_time_seconds=response_time,
        )

    def check_ncbi_health(
        self, retriever: Optional[PubMedRetriever], pmid: str
    ) -> Dict[str, Any]:
        if retriever is None:
            return _unhealthy(
                error="PubMedRetriever service not initialized", pmid=pmid
            )

        try:
            metadata = retriever.fetch_paper_metadata(pmid)
        except Exception as exc:
            log_masked_exception(exc, "NCBI health check error")
            return _unhealthy(
                error="An internal error occurred. Please try again later.", pmid=pmid
            )

        ok = bool(metadata.get("title") or metadata.get("abstract"))
        return {
            "status": "healthy" if ok else "unhealthy",
            "title_present": bool(metadata.get("title")),
            "abstract_present": bool(metadata.get("abstract")),
            "timestamp": get_current_timestamp(),
            "pmid": pmid,
        }

    def get_metrics(self) -> MetricsResponse:
        perf_metrics = perf_logger.get_metrics()
        memory = psutil.virtual_memory()

        return MetricsResponse(
            total_requests=perf_metrics.get("total_requests", 0),
            successful_requests=perf_metrics.get("successful_requests", 0),
            failed_requests=perf_metrics.get("failed_requests", 0),
            average_response_time=perf_metrics.get("average_response_time", 0.0),
            cache_hit_rate=self._cache_hit_rate(),
            memory_usage={
                "total_gb": round(memory.total / (1024**3), 2),
                "available_gb": round(memory.available / (1024**3), 2),
                "used_percent": memory.percent,
            },
        )

    def _cache_hit_rate(self) -> float:
        if CacheManager is None:
            return 0.0
        try:
            stats = CacheManager().get_cache_stats()
            total = stats.get("total_requests", 0)
            return (stats.get("cache_hits", 0) / total) if total else 0.0
        except Exception as exc:
            logger.warning("Failed to compute cache hit rate: %s", exc)
            return 0.0


def get_system_service() -> SystemService:
    """Dependency provider — stateless, injected so tests can override it."""
    return SystemService()
