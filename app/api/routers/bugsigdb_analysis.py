from __future__ import annotations

import asyncio
import logging
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException, Query

from app.api.models.api_models import (
    AnalysisRequestV2,
    BatchAnalysisRequestV2,
    PaperAnalysisResultV2,
    RAGConfig,
    RAGConfigResponse,
)
from app.services.bugsigdb_analyzer import analyze_paper_simple, analyze_paper_with_rag
from app.utils.config import (
    RAG_RERANK_METHOD,
    RAG_SUMMARY_LENGTH,
    RAG_SUMMARY_MODEL,
    RAG_SUMMARY_PROVIDER,
    RAG_SUMMARY_QUALITY,
    RAG_TOP_K_CHUNKS,
    RAG_USE_SUMMARY_CACHE,
)
from app.utils.credential_masking import mask_exception_message

logger = logging.getLogger(__name__)

# Canonical router — every analysis request ends up running through here.
router = APIRouter(prefix="/api/v2", tags=["BugSigDB Analysis v2"])

# Legacy router kept for backward compatibility. No independent business
# logic lives here; every handler delegates to the same helpers as /api/v2.
v1_router = APIRouter(prefix="/api/v1", tags=["BugSigDB Analysis (legacy v1)"])

# Upper bound on client-supplied concurrency for batch analysis, so a bad
# request can't spawn unbounded concurrent LLM/PubMed calls.
MAX_BATCH_CONCURRENCY = 20


# --------------------------------------------------------------------------- #
# Shared helpers — RAG config, validation, single/batch analysis, errors
# --------------------------------------------------------------------------- #


def _default_rag_config() -> RAGConfig:
    """Build the default RAG configuration from environment settings."""
    return RAGConfig(
        enabled=True,
        top_k_chunks=RAG_TOP_K_CHUNKS,
        evidence_k=None,  # No limit by default
        max_sources=RAG_TOP_K_CHUNKS,
        rerank_method=RAG_RERANK_METHOD,
        summary_length=RAG_SUMMARY_LENGTH,
        summary_quality=RAG_SUMMARY_QUALITY,
        summary_provider=RAG_SUMMARY_PROVIDER,
        summary_model=RAG_SUMMARY_MODEL,
        use_cache=RAG_USE_SUMMARY_CACHE,
        use_10_scale=True,
    )


def _build_rag_config_from_overrides(
    *,
    use_rag: bool,
    top_k_chunks: Optional[int] = None,
    evidence_k: Optional[int] = None,
    max_sources: Optional[int] = None,
    rerank_method: Optional[str] = None,
    summary_length: Optional[str] = None,
    summary_quality: Optional[str] = None,
) -> Optional[RAGConfig]:
    """Merge query-parameter overrides onto the default RAG config.

    Returns None when RAG is disabled — analyze_paper_with_rag treats
    ``rag_config=None`` together with ``use_rag=False`` as "skip RAG
    entirely," which is also how the old non-RAG (v1) path is expressed now.
    """
    if not use_rag:
        return None

    defaults = _default_rag_config()
    return RAGConfig(
        enabled=True,
        top_k_chunks=top_k_chunks or defaults.top_k_chunks,
        evidence_k=evidence_k if evidence_k is not None else defaults.evidence_k,
        max_sources=max_sources if max_sources is not None else defaults.max_sources,
        rerank_method=rerank_method or defaults.rerank_method,
        summary_length=summary_length or defaults.summary_length,
        summary_quality=summary_quality or defaults.summary_quality,
        summary_provider=defaults.summary_provider,
        summary_model=defaults.summary_model,
        use_cache=defaults.use_cache,
        use_10_scale=defaults.use_10_scale,
    )


def _log_and_raise_500(context: str, pmid: Optional[str], e: Exception) -> None:
    """Consistent, credential-safe error logging + HTTP 500 translation."""
    safe_error = mask_exception_message(e)
    if pmid:
        logger.error(f"{context} (PMID {pmid}): {safe_error}")
    else:
        logger.error(f"{context}: {safe_error}")
    raise HTTPException(status_code=500, detail="Internal server error")


async def _analyze_single_rag(
    pmid: str,
    *,
    use_rag: bool,
    rag_config: Optional[RAGConfig],
) -> PaperAnalysisResultV2:
    """RAG-pipeline entry point for one-paper analysis — backs every /api/v2
    analysis endpoint (RAG on or off; use_rag=False already meant "run the
    RAG-pipeline function without RAG" before this merge, and that behavior
    is unchanged here).

    NOT used by the /api/v1 legacy routes — see _analyze_single_simple.
    """
    # Imported lazily to avoid the circular-import issues this codebase has
    # hit before between app.api.utils and app.api.routers.
    from app.api.utils.api_utils import validate_pmid

    pmid = validate_pmid(pmid)
    logger.info(f"Starting RAG-path analysis for PMID {pmid} (use_rag={use_rag})")

    # force_refresh is intentionally not threaded through here: unlike
    # analyze_paper_simple (confirmed via tests/test_bugsigdb_analyzer.py to
    # accept force_refresh), analyze_paper_with_rag's signature for a
    # cache-bypass option hasn't been confirmed. Guessing wrong here means a
    # hard TypeError on every request rather than a quiet no-op, so this is
    # left out until the RAG service confirms/adds support for it.
    result = await analyze_paper_with_rag(pmid, rag_config=rag_config, use_rag=use_rag)
    if not result:
        raise HTTPException(status_code=404, detail=f"Analysis failed for PMID {pmid}")
    return result


async def _analyze_single_simple(
    pmid: str, *, force_refresh: bool = False
) -> Dict[str, Any]:
    """Legacy v1 entry point — calls the real, single-LLM-call simple analyzer.

    Deliberately not routed through analyze_paper_with_rag(use_rag=False):
    analyze_paper_simple is a distinct algorithm whose output shape is a
    documented contract elsewhere (app/models/extraction_schemas.py,
    app/services/agent_orchestrator.py) and is exercised directly by the
    existing test suite. force_refresh is confirmed supported here (see
    tests/test_bugsigdb_analyzer.py's force_refresh=True case).
    """
    from app.api.utils.api_utils import validate_pmid

    pmid = validate_pmid(pmid)
    logger.info(
        f"Starting simple analysis for PMID {pmid} (force_refresh={force_refresh})"
    )

    result = await analyze_paper_simple(pmid, force_refresh=force_refresh)
    if not result:
        raise HTTPException(status_code=404, detail=f"Analysis failed for PMID {pmid}")
    return result


async def _analyze_batch(
    pmids: List[str],
    *,
    use_rag: bool,
    rag_config: Optional[RAGConfig],
    max_concurrent: int,
) -> List[PaperAnalysisResultV2]:
    """Bounded-concurrency batch analysis over the RAG path.

    Batch has always been a /api/v2-only feature (BatchAnalysisRequestV2
    has no v1 equivalent), so this only ever needs the RAG-pipeline helper.
    """
    if not pmids:
        raise HTTPException(status_code=422, detail="pmids must not be empty")

    max_concurrent = max(1, min(max_concurrent, MAX_BATCH_CONCURRENCY))
    semaphore = asyncio.Semaphore(max_concurrent)

    async def _guarded(pmid: str) -> Optional[PaperAnalysisResultV2]:
        async with semaphore:
            try:
                return await _analyze_single_rag(
                    pmid, use_rag=use_rag, rag_config=rag_config
                )
            except Exception as e:
                # Keep the batch resilient: one bad PMID shouldn't fail the
                # whole request. Failures are logged and dropped from the
                # result list, matching the previous behavior.
                safe_error = mask_exception_message(e)
                logger.error(f"Error analyzing PMID {pmid} in batch: {safe_error}")
                return None

    results = await asyncio.gather(*(_guarded(pmid) for pmid in pmids))
    return [r for r in results if r is not None]


# --------------------------------------------------------------------------- #
# v2 (canonical) routes
# --------------------------------------------------------------------------- #


@router.get("/analyze/{pmid}")
async def analyze_paper(
    pmid: str,
    use_rag: bool = Query(True, description="Enable RAG features"),
    top_k_chunks: Optional[int] = Query(
        None, description="Number of top chunks to use"
    ),
    evidence_k: Optional[int] = Query(
        None, description="Number of evidence chunks to retrieve before re-ranking"
    ),
    max_sources: Optional[int] = Query(
        None, description="Maximum number of sources to use for final answer"
    ),
    rerank_method: Optional[str] = Query(
        None, description="Re-ranking method: keyword, llm, hybrid"
    ),
    summary_length: Optional[str] = Query(
        None, description="Summary length: short, medium, long"
    ),
    summary_quality: Optional[str] = Query(
        None, description="Summary quality: fast, balanced, high"
    ),
) -> PaperAnalysisResultV2:
    """
    Analyze a single paper for the essential BugSigDB fields with RAG support (GET variant).

    **RAG Features:**
    - Contextual summarization of relevant chunks
    - Chunk re-ranking by relevance
    - Query-aware context generation

    **Parameters:**
    - `pmid`: PubMed ID of the paper to analyze
    - `use_rag`: Enable/disable RAG features (default: True)
    - `top_k_chunks`: Number of top chunks to use after re-ranking
    - `evidence_k`: Number of evidence chunks to retrieve before re-ranking
    - `max_sources`: Maximum number of sources to use for final answer
    - `rerank_method`: Method for re-ranking ("keyword", "llm", "hybrid")
    - `summary_length`: Length of summaries ("short", "medium", "long")
    - `summary_quality`: Quality setting ("fast", "balanced", "high")
    """
    try:
        rag_config = _build_rag_config_from_overrides(
            use_rag=use_rag,
            top_k_chunks=top_k_chunks,
            evidence_k=evidence_k,
            max_sources=max_sources,
            rerank_method=rerank_method,
            summary_length=summary_length,
            summary_quality=summary_quality,
        )
        return await _analyze_single_rag(pmid, use_rag=use_rag, rag_config=rag_config)
    except HTTPException:
        raise
    except Exception as e:
        _log_and_raise_500("Error in v2 analysis", pmid, e)


@router.post("/analyze")
async def analyze_paper_post(request: AnalysisRequestV2) -> PaperAnalysisResultV2:
    """
    Analyze a single paper for the essential BugSigDB fields with RAG support (POST variant).

    **Request Body:**
    ```json
    {
        "pmid": "12345678",
        "use_rag": true,
        "rag_config": {
            "enabled": true,
            "top_k_chunks": 10,
            "rerank_method": "hybrid",
            "summary_length": "medium",
            "summary_quality": "balanced"
        }
    }
    ```
    """
    try:
        rag_config = request.rag_config
        if request.use_rag and not rag_config:
            rag_config = _default_rag_config()
        return await _analyze_single_rag(
            request.pmid, use_rag=request.use_rag, rag_config=rag_config
        )
    except HTTPException:
        raise
    except Exception as e:
        _log_and_raise_500("Error in v2 POST analysis", request.pmid, e)


@router.post("/analyze/batch")
async def analyze_papers_batch(
    request: BatchAnalysisRequestV2,
) -> List[PaperAnalysisResultV2]:
    """
    Analyze multiple papers in batch with RAG support.

    **Request Body:**
    ```json
    {
        "pmids": ["12345678", "87654321"],
        "use_rag": true,
        "rag_config": {...},
        "max_concurrent": 5
    }
    ```
    """
    try:
        rag_config = request.rag_config
        if request.use_rag and not rag_config:
            rag_config = _default_rag_config()
        return await _analyze_batch(
            request.pmids,
            use_rag=request.use_rag,
            rag_config=rag_config,
            max_concurrent=request.max_concurrent,
        )
    except HTTPException:
        raise
    except Exception as e:
        _log_and_raise_500("Error in batch analysis", None, e)


@router.get("/rag/config")
async def get_rag_config() -> RAGConfigResponse:
    """
    Get RAG configuration information and available options.

    Returns default configuration and available options for RAG features.
    """
    try:
        from app.models.llm_provider import LLMProviderManager

        default_config = _default_rag_config()
        available_providers = (
            LLMProviderManager.get_available_providers()
            if hasattr(LLMProviderManager, "get_available_providers")
            else []
        )
        return RAGConfigResponse(
            default_config=default_config,
            available_rerank_methods=["keyword", "llm", "hybrid"],
            available_summary_lengths=["short", "medium", "long"],
            available_summary_qualities=["fast", "balanced", "high"],
            available_providers=available_providers
            or ["gemini", "openai", "anthropic"],
        )
    except Exception as e:
        _log_and_raise_500("Error getting RAG config", None, e)


@router.get("/fields")
async def get_essential_fields_v2():
    """Get information about the configured essential BugSigDB fields."""
    from app.api.utils.field_helpers import get_fields_response

    return get_fields_response("v2")


@router.get("/fields/{field_name}")
async def get_field_details_v2(field_name: str):
    """Get information about a single BugSigDB field."""
    from app.api.utils.field_helpers import get_field_details_response

    return get_field_details_response(field_name, "v2")


# --------------------------------------------------------------------------- #
# v1 (legacy) routes — thin wrappers around the real simple-analysis path
# --------------------------------------------------------------------------- #
#
# These preserve the old /api/v1 surface for existing clients. They call
# _analyze_single_simple(), which wraps analyze_paper_simple() directly —
# NOT the RAG pipeline with use_rag=False. analyze_paper_simple is its own
# algorithm with its own tested output contract (see the module docstring
# for why routing it through analyze_paper_with_rag would be a regression,
# not a deduplication).


@v1_router.get("/analyze/{pmid}")
async def analyze_paper_v1(pmid: str, refresh: bool = False) -> Dict[str, Any]:
    """Legacy simple-analysis endpoint. Delegates to analyze_paper_simple."""
    try:
        return await _analyze_single_simple(pmid, force_refresh=refresh)
    except HTTPException:
        raise
    except Exception as e:
        _log_and_raise_500("Error in v1 analysis", pmid, e)


@v1_router.post("/analyze/{pmid}")
async def analyze_paper_post_v1(pmid: str, refresh: bool = False) -> Dict[str, Any]:
    """Legacy non-RAG analysis endpoint (POST). Identical behavior to the GET variant."""
    return await analyze_paper_v1(pmid, refresh=refresh)


@v1_router.get("/fields")
async def get_essential_fields_v1():
    """Get information about BugSigDB fields (legacy v1 shape)."""
    from app.api.utils.field_helpers import get_fields_response

    return get_fields_response("v1")


@v1_router.get("/fields/{field_name}")
async def get_field_details_v1(field_name: str):
    """Get details for a specific BugSigDB field (legacy v1 shape)."""
    from app.api.utils.field_helpers import get_field_details_response

    return get_field_details_response(field_name, "v1")
