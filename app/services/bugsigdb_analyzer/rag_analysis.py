"""
analyze_paper_with_rag — RAG-augmented BugSigDB field extraction (v2 API),
plus the backward-compat single-field analysis path
(analyze_single_field).
"""

import asyncio
import logging
import time
from typing import Any, Dict, List, Optional

import app.services.bugsigdb_analyzer as _pkg
from app.utils.credential_masking import mask_exception_message
from app.utils.config import ANALYSIS_TIMEOUT, DEFAULT_MODEL, GEMINI_API_KEY

from .constants import _current_timestamp
from .field_extraction import (
    _avg_confidence,
    _build_curation_summary,
    _extract_structured_metadata,
    _field_results_from_unified_payload,
    _heuristic_payload_from_text,
    _parse_json_object,
    _postprocess_field_results,
    _resolve_diff_abundance,
    create_empty_field_result,
    extract_year,
)
from .parsing import prepare_analysis_context

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# analyze_paper_with_rag
# ---------------------------------------------------------------------------


async def analyze_paper_with_rag(
    pmid: str,
    rag_config: Optional[Dict] = None,
    use_rag: bool = True,
) -> Optional[Dict]:
    """Analyse a paper with optional RAG augmentation."""
    start_time = time.time()

    try:
        cache_manager = _pkg.get_cache_manager()
        pubmed_retriever = _pkg.get_pubmed_retriever()

        if pubmed_retriever is None:
            logger.error("PubMedRetriever not available — check NCBI_API_KEY")
            return None

        # Normalise rag_config to a plain dict
        if hasattr(rag_config, "model_dump"):
            rag_config_dict = rag_config.model_dump(exclude_none=True)
        elif hasattr(rag_config, "dict"):
            rag_config_dict = rag_config.dict()
        elif isinstance(rag_config, dict):
            rag_config_dict = rag_config
        else:
            rag_config_dict = None

        use_rag_final = use_rag and (
            rag_config_dict is None or rag_config_dict.get("enabled", True)
        )
        logger.info("Starting RAG analysis for PMID %s (RAG=%s)", pmid, use_rag_final)

        texts = await pubmed_retriever.get_texts_for_analysis_async(pmid)
        if not texts.get("title") and not texts.get("abstract"):
            logger.warning("No content found for PMID %s", pmid)
            return None

        title = texts.get("title", "")
        abstract = texts.get("abstract", "")
        full_text = texts.get("full_text", "")
        year = extract_year(texts.get("publication_date", ""))

        analysis_text = prepare_analysis_context(abstract, full_text)
        if not analysis_text.strip():
            logger.warning("No analysable text for PMID %s", pmid)
            return None

        # ── Optional chunking ──────────────────────────────────────────────
        chunks = None
        if use_rag_final and full_text and len(full_text) > 1_000:
            try:
                from app.utils.chunking import ChunkingService

                chunker = ChunkingService(chunk_chars=3_000, overlap=100)
                chunks = await chunker.chunk_markdown(
                    markdown=analysis_text,
                    doc_name=f"PMID_{pmid}",
                    doc_key=pmid,
                )
                logger.info(
                    "Created %d section-aware chunks for PMID %s", len(chunks), pmid
                )
            except Exception as chunk_error:
                logger.warning(
                    "Chunking failed for PMID %s: %s",
                    pmid,
                    mask_exception_message(chunk_error),
                )
                chunks = None

        # ── Optional RAG context retrieval ─────────────────────────────────
        context_for_prompt = analysis_text
        rag_service = None
        if use_rag_final and chunks:
            try:
                from app.services.advanced_rag import AdvancedRAGService

                _rc = rag_config_dict or {}
                rag_service = AdvancedRAGService(
                    rerank_method=_rc.get("rerank_method", "hybrid"),
                    evidence_k=_rc.get("evidence_k"),
                    max_sources=_rc.get("max_sources"),
                    use_10_scale=_rc.get("use_10_scale", True),
                )
                context_for_prompt = await rag_service.get_contextual_context(
                    chunks=chunks,
                    query=(
                        "Extract host species, body site, condition, sequencing type, "
                        "sample size and differential abundance metadata."
                    ),
                    top_k=_rc.get("top_k_chunks"),
                    evidence_k=_rc.get("evidence_k"),
                    max_sources=_rc.get("max_sources"),
                )
            except Exception as rag_error:
                logger.warning(
                    "RAG context retrieval failed for PMID %s: %s",
                    pmid,
                    mask_exception_message(rag_error),
                )

        processing_time = time.time() - start_time

        # ── LLM extraction ─────────────────────────────────────────────────
        payload = await _extract_structured_metadata(
            context_text=context_for_prompt,
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

        # ── Assemble result dict ───────────────────────────────────────────
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
            "analysis_timestamp": _current_timestamp(),
            "model_used": DEFAULT_MODEL,
            # RAG-specific extras (not consumed by data.R; useful for debugging)
            "processing_time": processing_time,
            "rag_enabled": use_rag_final,
            "rag_stats": None,
            "rag_config_used": rag_config_dict if use_rag_final else None,
        }

        if use_rag_final and chunks:
            result["rag_stats"] = _collect_rag_stats(
                rag_service=rag_service,
                chunks=chunks,
                field_results=field_results,
                rag_config_dict=rag_config_dict,
                processing_time=processing_time,
            )

        logger.info(
            "RAG analysis completed for PMID %s in %.2fs", pmid, processing_time
        )

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
                "Unable to cache RAG analysis for PMID %s: %s",
                pmid,
                mask_exception_message(cache_error),
            )

        return result

    except Exception as e:
        logger.error(
            "Error in RAG analysis for PMID %s: %s", pmid, mask_exception_message(e)
        )
        return None


def _collect_rag_stats(
    *,
    rag_service: Optional[Any],
    chunks: List,
    field_results: Dict[str, Dict[str, Any]],
    rag_config_dict: Optional[Dict],
    processing_time: float,
) -> Dict[str, Any]:
    _rc = rag_config_dict or {}
    rag_metrics: Dict[str, Any] = {}
    if rag_service is not None:
        try:
            rag_metrics = rag_service.get_rerank_metrics()
        except Exception as e:
            logger.warning(
                "Failed to compute RAG rerank metrics: %s", mask_exception_message(e)
            )

    return {
        "chunks_processed": len(chunks),
        "chunks_ranked": rag_metrics.get("chunks_reranked", len(chunks)),
        "chunks_summarized": min(_rc.get("top_k_chunks", 10), len(chunks)),
        "avg_relevance_score": rag_metrics.get("avg_relevance_score", 0.75),
        "max_relevance_score": rag_metrics.get("max_relevance_score", 0.0),
        "min_relevance_score": rag_metrics.get("min_relevance_score", 0.0),
        "avg_confidence": _avg_confidence(field_results),
        "rerank_method": _rc.get("rerank_method", "hybrid"),
        "summary_length": _rc.get("summary_length", "medium"),
        "evidence_k": _rc.get("evidence_k"),
        "max_sources": _rc.get("max_sources"),
        "use_10_scale": _rc.get("use_10_scale", True),
        "rerank_processing_time": rag_metrics.get("processing_time", 0.0),
        "avg_chunk_processing_time": rag_metrics.get("avg_chunk_processing_time", 0.0),
        "processing_time": processing_time,
    }


# ---------------------------------------------------------------------------
# analyze_single_field  (backward compat)
# ---------------------------------------------------------------------------


async def analyze_single_field(
    text: str,
    field_name: str,
    question: str,
    pmid: str,
    chunks: Optional[List] = None,
    rag_config: Optional[Dict] = None,
) -> Dict:
    try:
        context_text = await _build_single_field_context(
            text, field_name, question, chunks, rag_config
        )
        return await _query_single_field(context_text, field_name, question, pmid)
    except asyncio.TimeoutError:
        logger.warning("Field %s timed out for PMID %s", field_name, pmid)
        return create_empty_field_result(field_name)
    except Exception as e:
        logger.error(
            "Error analysing field %s for PMID %s: %s",
            field_name,
            pmid,
            mask_exception_message(e),
        )
        return create_empty_field_result(field_name)


async def _build_single_field_context(
    text: str,
    field_name: str,
    question: str,
    chunks: Optional[List],
    rag_config: Optional[Dict],
) -> str:
    if not chunks:
        return text[:2_000]
    _rc = rag_config or {}
    try:
        from app.services.advanced_rag import AdvancedRAGService

        if _rc.get("enabled", True):
            from app.services.contextual_summarization import SummarizationConfig

            svc = AdvancedRAGService(
                summary_provider=_rc.get("summary_provider"),
                summary_model=_rc.get("summary_model"),
                rerank_method=_rc.get("rerank_method"),
                evidence_k=_rc.get("evidence_k"),
                max_sources=_rc.get("max_sources"),
                use_10_scale=_rc.get("use_10_scale", True),
            )
            if _rc.get("summary_length") or _rc.get("summary_quality"):
                svc.summarization_service.config = SummarizationConfig(
                    summary_length=_rc.get("summary_length", "medium"),
                    quality=_rc.get("summary_quality", "balanced"),
                    use_cache=_rc.get("use_cache", True),
                )
        else:
            svc = AdvancedRAGService()
        ctx = await svc.get_contextual_context(
            chunks=chunks,
            query=question,
            top_k=_rc.get("top_k_chunks"),
            evidence_k=_rc.get("evidence_k"),
            max_sources=_rc.get("max_sources"),
        )
        logger.info("RAG context for field %s: %d chars", field_name, len(ctx))
        return ctx
    except Exception as rag_error:
        logger.warning(
            "RAG failed for field %s; using plain text: %s",
            field_name,
            mask_exception_message(rag_error),
        )
        return text[:2_000]


async def _query_single_field(
    context_text: str, field_name: str, question: str, pmid: str
) -> Dict:
    prompt = (
        f"Context: {context_text}\n\n"
        f"Question: {question}\n\n"
        "Respond ONLY with a JSON object (no markdown):\n"
        "{\n"
        '    "value": "specific answer or null if not found",\n'
        '    "status": "PRESENT|PARTIALLY_PRESENT|ABSENT",\n'
        '    "confidence": 0.0-1.0,\n'
        '    "reason_if_missing": "explanation if absent"\n'
        "}"
    )
    unified_qa = _pkg.get_unified_qa()
    if unified_qa is None:
        logger.error("UnifiedQA not available — check GEMINI_API_KEY")
        return create_empty_field_result(field_name)

    chat_call = unified_qa.chat(prompt)
    response = (
        await asyncio.wait_for(chat_call, timeout=ANALYSIS_TIMEOUT)
        if asyncio.iscoroutine(chat_call)
        else chat_call
    )
    answer_text = response.get("text", "")

    if answer_text.startswith("Error:") and (
        "Paper-QA" in answer_text or "router" in answer_text.lower()
    ):
        logger.info("Falling back to GeminiQA for field %s", field_name)
        try:
            from app.models.gemini_qa import GeminiQA

            response = await asyncio.wait_for(
                GeminiQA(api_key=GEMINI_API_KEY).chat(prompt),
                timeout=ANALYSIS_TIMEOUT,
            )
            answer_text = response.get("text", "")
        except Exception as fb_err:
            logger.error("GeminiQA fallback failed: %s", mask_exception_message(fb_err))
            return create_empty_field_result(field_name)

    parsed = _parse_json_object(answer_text)
    if parsed:
        return {
            "value": parsed.get("value"),
            "status": parsed.get("status", "ABSENT"),
            "confidence": float(
                parsed.get("confidence", response.get("confidence", 0.0))
            ),
            "reason_if_missing": parsed.get("reason_if_missing", ""),
        }

    confidence = response.get("confidence", 0.0)
    if not answer_text or confidence < 0.3:
        return create_empty_field_result(field_name)

    if confidence >= 0.8 and answer_text.lower() not in {
        "not found",
        "not available",
        "none",
        "n/a",
    }:
        status = "PRESENT"
    elif confidence >= 0.4:
        status = "PARTIALLY_PRESENT"
    else:
        status = "ABSENT"

    return {
        "value": answer_text if status != "ABSENT" else None,
        "status": status,
        "confidence": confidence,
        "reason_if_missing": (
            "" if status != "ABSENT" else "Information not found in the paper"
        ),
    }
