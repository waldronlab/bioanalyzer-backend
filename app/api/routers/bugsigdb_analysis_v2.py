"""BugSigDB Analysis API Router v2 with RAG support."""

from fastapi import APIRouter, HTTPException, Query
from typing import Optional, List
import logging
from app.utils.credential_masking import mask_exception_message
from app.api.utils.constants import ESSENTIAL_FIELDS_INFO, STATUS_VALUES
from app.services.bugsigdb_analyzer import analyze_paper_with_rag
from app.api.models.api_models import (
    AnalysisRequestV2,
    BatchAnalysisRequestV2,
    PaperAnalysisResultV2,
    RAGConfig,
    RAGConfigResponse,
)
from app.utils.config import (
    RAG_SUMMARY_PROVIDER,
    RAG_SUMMARY_MODEL,
    RAG_SUMMARY_LENGTH,
    RAG_SUMMARY_QUALITY,
    RAG_RERANK_METHOD,
    RAG_USE_SUMMARY_CACHE,
    RAG_TOP_K_CHUNKS,
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/v2", tags=["BugSigDB Analysis v2"])


def _get_default_rag_config() -> RAGConfig:
    """Get default RAG configuration from environment."""
    return RAGConfig(
        enabled=True,
        top_k_chunks=RAG_TOP_K_CHUNKS,
        evidence_k=None,  # No limit by default
        max_sources=RAG_TOP_K_CHUNKS,  # Default to same as top_k_chunks
        rerank_method=RAG_RERANK_METHOD,
        summary_length=RAG_SUMMARY_LENGTH,
        summary_quality=RAG_SUMMARY_QUALITY,
        summary_provider=RAG_SUMMARY_PROVIDER,
        summary_model=RAG_SUMMARY_MODEL,
        use_cache=RAG_USE_SUMMARY_CACHE,
        use_10_scale=True,  # Use 0-10 scale by default
    )


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
    Analyze a single paper for the 6 essential BugSigDB fields with RAG support (GET variant).

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
        # Build RAG config from query parameters
        rag_config = None
        if use_rag:
            default_config = _get_default_rag_config()
            rag_config = RAGConfig(
                enabled=True,
                top_k_chunks=top_k_chunks or default_config.top_k_chunks,
                evidence_k=(
                    evidence_k if evidence_k is not None else default_config.evidence_k
                ),
                max_sources=(
                    max_sources
                    if max_sources is not None
                    else default_config.max_sources
                ),
                rerank_method=rerank_method or default_config.rerank_method,
                summary_length=summary_length or default_config.summary_length,
                summary_quality=summary_quality or default_config.summary_quality,
                summary_provider=default_config.summary_provider,
                summary_model=default_config.summary_model,
                use_cache=default_config.use_cache,
                use_10_scale=default_config.use_10_scale,
            )

        result = await analyze_paper_with_rag(
            pmid, rag_config=rag_config, use_rag=use_rag
        )
        if not result:
            raise HTTPException(
                status_code=404, detail=f"Analysis failed for PMID {pmid}"
            )
        return result
    except HTTPException:
        raise
    except Exception as e:
        safe_error = mask_exception_message(e)
        logger.error(f"Error in v2 analysis for PMID {pmid}: {safe_error}")
        raise HTTPException(status_code=500, detail=f"Analysis error: {str(e)}")


@router.post("/analyze")
async def analyze_paper_post(request: AnalysisRequestV2) -> PaperAnalysisResultV2:
    """
    Analyze a single paper for the 6 essential BugSigDB fields with RAG support (POST variant).

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
            # Use default config if RAG enabled but no config provided
            rag_config = _get_default_rag_config()

        result = await analyze_paper_with_rag(
            request.pmid, rag_config=rag_config, use_rag=request.use_rag
        )
        if not result:
            raise HTTPException(
                status_code=404, detail=f"Analysis failed for PMID {request.pmid}"
            )
        return result
    except HTTPException:
        raise
    except Exception as e:
        safe_error = mask_exception_message(e)
        logger.error(f"Error in v2 POST analysis for PMID {request.pmid}: {safe_error}")
        raise HTTPException(status_code=500, detail=f"Analysis error: {str(e)}")


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
    import asyncio

    try:
        rag_config = request.rag_config
        if request.use_rag and not rag_config:
            rag_config = _get_default_rag_config()

        # Process in batches with concurrency limit
        semaphore = asyncio.Semaphore(request.max_concurrent)
        results = []

        async def analyze_with_semaphore(pmid: str):
            async with semaphore:
                try:
                    return await analyze_paper_with_rag(
                        pmid, rag_config=rag_config, use_rag=request.use_rag
                    )
                except Exception as e:
                    safe_error = mask_exception_message(e)
                    logger.error(f"Error analyzing PMID {pmid} in batch: {safe_error}")
                    return None

        tasks = [analyze_with_semaphore(pmid) for pmid in request.pmids]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        # Filter out None and exceptions
        valid_results = [
            r for r in results if r is not None and not isinstance(r, Exception)
        ]

        return valid_results

    except Exception as e:
        safe_error = mask_exception_message(e)
        logger.error(f"Error in batch analysis: {safe_error}")
        raise HTTPException(status_code=500, detail=f"Batch analysis error: {str(e)}")


@router.get("/rag/config")
async def get_rag_config() -> RAGConfigResponse:
    """
    Get RAG configuration information and available options.

    Returns default configuration and available options for RAG features.
    """
    try:
        from app.models.llm_provider import LLMProviderManager

        default_config = _get_default_rag_config()
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
        safe_error = mask_exception_message(e)
        logger.error(f"Error getting RAG config: {safe_error}")
        raise HTTPException(
            status_code=500, detail=f"Error getting RAG config: {str(e)}"
        )


@router.get("/fields")
async def get_essential_fields():
    """Get information about the 6 essential BugSigDB fields."""
    from app.api.utils.field_helpers import get_fields_response

    return get_fields_response("v2")


@router.get("/fields/{field_name}")
async def get_field_details(field_name: str):
    """Get information about a single BugSigDB field."""
    from app.api.utils.field_helpers import get_field_details_response

    return get_field_details_response(field_name, "v2")
