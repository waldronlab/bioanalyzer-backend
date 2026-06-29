"""
analyze_paper_simple — single-LLM-call BugSigDB field extraction (v1 API).
"""

import asyncio
import logging
import time
from typing import Any, Dict, Optional

import app.services.bugsigdb_analyzer as _pkg
from app.utils.credential_masking import mask_exception_message
from app.utils.config import DEFAULT_MODEL, CACHE_VALIDITY_HOURS

from .constants import _current_timestamp
from .field_extraction import (
    _avg_confidence,
    _build_curation_summary,
    _extract_structured_metadata,
    _field_results_from_unified_payload,
    _heuristic_payload_from_text,
    _is_low_quality_cached_result,
    _postprocess_field_results,
    _resolve_diff_abundance,
    extract_year,
)
from .parsing import prepare_analysis_context

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# analyze_paper_simple
# ---------------------------------------------------------------------------


async def analyze_paper_simple(
    pmid: str, force_refresh: bool = False
) -> Optional[Dict[str, Any]]:
    """
    Extract BugSigDB fields from a paper (single LLM call, cache-aware).

    Returns a result dict conforming to the Output contract at the top of
    this module, or None when no content can be retrieved.
    """
    try:
        cache_manager = _pkg.get_cache_manager()
        pubmed_retriever = _pkg.get_pubmed_retriever()

        if pubmed_retriever is None:
            logger.error("PubMedRetriever not available — check NCBI_API_KEY")
            return None

        # ── Cache check ────────────────────────────────────────────────────
        cached = cache_manager.get_analysis_result(pmid)
        low_quality_cached: Optional[Dict[str, Any]] = None

        if (
            not force_refresh
            and cached
            and cache_manager.is_cache_valid(
                cached.get("timestamp", ""), max_age_hours=CACHE_VALIDITY_HOURS
            )
        ):
            cached_analysis = cached.get("analysis_data") or {}
            if _is_low_quality_cached_result(cached_analysis):
                low_quality_cached = cached_analysis
                logger.info(
                    "Cached result for PMID %s has all essential fields ABSENT; recomputing",
                    pmid,
                )
            else:
                logger.info("Returning cached analysis for PMID %s", pmid)
                return cached_analysis
        elif force_refresh and cached:
            logger.info("Force-refresh for PMID %s; bypassing cache", pmid)

        # ── Retrieve content ───────────────────────────────────────────────
        start_time = time.time()
        logger.info("Starting simple analysis for PMID %s", pmid)
        texts = await pubmed_retriever.get_texts_for_analysis_async(pmid)

        if not texts.get("title") and not texts.get("abstract"):
            logger.warning("No content found for PMID %s", pmid)
            if low_quality_cached is not None:
                return low_quality_cached
            return None

        title = texts.get("title", "")
        abstract = texts.get("abstract", "")
        full_text = texts.get("full_text", "")
        year = extract_year(texts.get("publication_date", ""))

        analysis_text = prepare_analysis_context(abstract, full_text)
        if not analysis_text.strip():
            logger.warning("No analysable text for PMID %s", pmid)
            return None

        # ── LLM extraction ─────────────────────────────────────────────────
        payload = await _extract_structured_metadata(
            context_text=analysis_text,
            title=title,
            journal=texts.get("journal", ""),
            year=year if year is not None else "",
        )
        if not payload:
            logger.warning(
                "Empty LLM payload for PMID %s; using heuristic fallback", pmid
            )
            payload = _heuristic_payload_from_text(analysis_text)

        # Normalization can make blocking network calls (NCBI/OLS fallback
        # lookups) - run off the event loop so a slow lookup doesn't stall
        # other concurrent requests.
        field_results = await asyncio.to_thread(
            _field_results_from_unified_payload, payload
        )
        field_results = _postprocess_field_results(field_results, analysis_text)
        has_diff_abund, diff_abund_conf = _resolve_diff_abundance(
            payload, analysis_text
        )

        processing_time = time.time() - start_time

        # ── Assemble result dict ───────────────────────────────────────────
        # Key names here are the single source of truth — data.R reads these.
        result: Dict[str, Any] = {
            "pmid": pmid,
            "title": title,
            "authors": texts.get("authors", []),
            "journal": texts.get("journal", ""),
            "publication_date": texts.get("publication_date", ""),
            "year": year if year is not None else "",
            "has_differential_abundance": has_diff_abund,
            "differential_abundance_confidence": diff_abund_conf,
            "in_bugsigdb": _pkg.is_in_bugsigdb(pmid),
            "fields": field_results,
            "curation_summary": _build_curation_summary(field_results),
            "processing_time": processing_time,
            "analysis_timestamp": _current_timestamp(),
            "model_used": DEFAULT_MODEL,
        }

        logger.info(
            "Simple analysis completed for PMID %s in %.2fs", pmid, processing_time
        )

        # ── Cache result ───────────────────────────────────────────────────
        try:
            cache_manager.store_analysis_result(
                pmid=pmid,
                analysis_data=result,
                metadata={
                    "title": title,
                    "journal": texts.get("journal", ""),
                    "publication_date": texts.get("publication_date", ""),
                    "authors": texts.get("authors", []),
                },
                source=DEFAULT_MODEL,
                confidence=_avg_confidence(field_results),
            )
        except Exception as cache_error:
            logger.warning(
                "Unable to cache analysis for PMID %s: %s",
                pmid,
                mask_exception_message(cache_error),
            )

        return result

    except Exception as e:
        logger.error(
            "Error in simple analysis for PMID %s: %s",
            pmid,
            mask_exception_message(e),
        )
        if "low_quality_cached" in locals() and low_quality_cached is not None:
            return low_quality_cached
        return None
