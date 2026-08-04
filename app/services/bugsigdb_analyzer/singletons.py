"""
Singleton service instances for the BugSigDB analyzer.
"""

import logging
from typing import Optional

from app.models.unified_qa import UnifiedQA
from app.services.cache_manager import CacheManager
from app.services.data_retrieval import PubMedRetriever
from app.utils.credential_masking import mask_exception_message
from app.utils.config import (
    DEFAULT_MODEL,
    GEMINI_API_KEY,
    NCBI_API_KEY,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Singleton service instances
# ---------------------------------------------------------------------------

_unified_qa: Optional[UnifiedQA] = None
_pubmed_retriever: Optional[PubMedRetriever] = None
_cache_manager: Optional[CacheManager] = None


def get_unified_qa() -> Optional[UnifiedQA]:
    global _unified_qa
    if _unified_qa is None:
        try:
            _unified_qa = UnifiedQA(
                provider="gemini",
                model=DEFAULT_MODEL,
                gemini_api_key=GEMINI_API_KEY,
                use_paperqa=False,
            )
            logger.info("UnifiedQA initialised successfully")
        except Exception as e:
            logger.error("UnifiedQA init failed: %s", mask_exception_message(e))
            try:
                from app.models.gemini_qa import GeminiQA

                _unified_qa = GeminiQA(api_key=GEMINI_API_KEY)
                logger.info("Fallback to GeminiQA successful")
            except Exception as e2:
                logger.error(
                    "GeminiQA fallback also failed: %s", mask_exception_message(e2)
                )
    return _unified_qa


def get_pubmed_retriever() -> Optional[PubMedRetriever]:
    global _pubmed_retriever
    if _pubmed_retriever is None:
        try:
            _pubmed_retriever = PubMedRetriever(api_key=NCBI_API_KEY)
        except Exception as e:
            logger.error("PubMedRetriever init failed: %s", mask_exception_message(e))
    return _pubmed_retriever


def get_cache_manager() -> CacheManager:
    global _cache_manager
    if _cache_manager is None:
        _cache_manager = CacheManager()
    return _cache_manager
