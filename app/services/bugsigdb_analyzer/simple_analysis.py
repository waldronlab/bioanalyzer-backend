"""
analyze_paper_simple — single-LLM-call BugSigDB field extraction (v1 API).
"""

import asyncio
import logging
import time
from typing import Any, Dict, Optional

import app.services.bugsigdb_analyzer as _pkg
from app.utils.credential_masking import mask_exception_message
from app.utils.config import ANALYSIS_TIMEOUT, CACHE_VALIDITY_HOURS

from .condition_disambiguation import disambiguate_condition
from .constants import EXTRACTION_PROMPT, _current_timestamp
from .field_extraction import (
    _avg_confidence,
    _build_curation_summary,
    _field_results_from_unified_payload,
    _heuristic_payload_from_text,
    _is_low_quality_cached_result,
    _parse_json_object,
    _postprocess_field_results,
    _resolve_diff_abundance,
    extract_year,
)
from .parsing import prepare_analysis_context

logger = logging.getLogger(__name__)

# Payload provenance, surfaced as result["extraction_source"] so a curator
# (or a benchmark) can tell a real model answer from the regex fallback.
SOURCE_LLM = "llm"
SOURCE_HEURISTIC = "heuristic"

# One retry for an empty/unparseable LLM answer. At temperature 0 a second
# identical call is cheap insurance against a transient provider hiccup
# (truncated stream, safety-filtered reply, rate-limit error text), and
# far better than silently handing the paper to the regex heuristic.
_LLM_ATTEMPTS = 2


# ---------------------------------------------------------------------------
# LLM extraction with retry (shared by the v1 and v2 pipelines)
# ---------------------------------------------------------------------------


async def _extract_payload_with_retry(
    *,
    context_text: str,
    title: str,
    journal: str,
    year: Any,
    pmid: str = "",
) -> Dict[str, Any]:
    """Run the unified extraction prompt in JSON mode, retrying once when the
    model returns nothing parseable.

    Returns the parsed payload tagged ``_source="llm"``, or ``{}`` when both
    attempts fail (or the call times out) so the caller can fall back to the
    heuristic extractor. Never raises.
    """
    unified_qa = _pkg.get_unified_qa()
    if unified_qa is None:
        logger.error("UnifiedQA not available for PMID %s — check LLM API keys", pmid)
        return {}

    prompt = EXTRACTION_PROMPT.format(
        title=title or "",
        journal=journal or "",
        year=year if year is not None else "",
        paper_content=context_text or "",
    )

    for attempt in range(1, _LLM_ATTEMPTS + 1):
        response: Dict[str, Any] = {}
        try:
            chat_call = unified_qa.chat(prompt, json_mode=True)
            response = (
                await asyncio.wait_for(chat_call, timeout=ANALYSIS_TIMEOUT)
                if asyncio.iscoroutine(chat_call)
                else chat_call
            ) or {}
        except asyncio.TimeoutError:
            # Don't retry a timeout: a second ANALYSIS_TIMEOUT-long wait would
            # double the worst-case latency for a provider that is already
            # too slow. The heuristic fallback is the bounded answer.
            logger.warning(
                "LLM extraction timed out after %ss for PMID %s (attempt %d/%d)",
                ANALYSIS_TIMEOUT,
                pmid,
                attempt,
                _LLM_ATTEMPTS,
            )
            return {}
        except Exception as e:
            logger.warning(
                "LLM extraction failed for PMID %s (attempt %d/%d): %s",
                pmid,
                attempt,
                _LLM_ATTEMPTS,
                mask_exception_message(e),
            )

        payload = _parse_json_object((response or {}).get("text", "") or "")
        if payload:
            payload["_source"] = SOURCE_LLM
            return payload

        if attempt < _LLM_ATTEMPTS:
            logger.warning(
                "Empty or unparseable LLM payload for PMID %s (attempt %d/%d); retrying",
                pmid,
                attempt,
                _LLM_ATTEMPTS,
            )

    logger.warning(
        "No usable LLM payload for PMID %s after %d attempts", pmid, _LLM_ATTEMPTS
    )
    return {}


def _heuristic_payload(analysis_text: str) -> Dict[str, Any]:
    """Regex fallback payload, always tagged ``_source="heuristic"`` (the
    extractor tags it too, but an empty-text result would not be)."""
    payload = dict(_heuristic_payload_from_text(analysis_text) or {})
    payload["_source"] = SOURCE_HEURISTIC
    return payload


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

        # ── LLM extraction (JSON mode, one retry) ──────────────────────────
        payload = await _extract_payload_with_retry(
            context_text=analysis_text,
            title=title,
            journal=texts.get("journal", ""),
            year=year if year is not None else "",
            pmid=pmid,
        )
        if not payload:
            logger.warning(
                "No LLM payload for PMID %s after retry; using heuristic fallback",
                pmid,
            )
            payload = _heuristic_payload(analysis_text)
        extraction_source = payload.get("_source", SOURCE_HEURISTIC)

        # Normalization can make blocking network calls (NCBI/OLS fallback
        # lookups) - run off the event loop so a slow lookup doesn't stall
        # other concurrent requests.
        field_results = await asyncio.to_thread(
            _field_results_from_unified_payload, payload
        )
        field_results = _postprocess_field_results(field_results, analysis_text)
        if "condition" in field_results:
            field_results["condition"] = await disambiguate_condition(
                field_results["condition"],
                title=title,
                abstract=abstract,
                unified_qa=_pkg.get_unified_qa(),
                pmid=pmid,
                context=analysis_text,
            )
        has_diff_abund, diff_abund_conf = _resolve_diff_abundance(
            payload, analysis_text
        )

        processing_time = time.time() - start_time

        # Report what actually ran rather than the DEFAULT_MODEL label.
        model_label = _pkg.describe_active_model()

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
            "model_used": model_label,
            # "llm" or "heuristic": whether the fields came from the model
            # or from the regex fallback after the LLM returned nothing usable.
            "extraction_source": extraction_source,
        }

        logger.info(
            "Simple analysis completed for PMID %s in %.2fs (source=%s)",
            pmid,
            processing_time,
            extraction_source,
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
                source=model_label,
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
