"""Extracts six BugSigDB fields from papers using LLMs.

This is the main analysis service. It orchestrates paper retrieval, text preparation,
and field extraction. Results are cached to avoid redundant API calls.
"""

import logging
from typing import Dict, Optional, List, Any, Tuple
import asyncio
import json
import re

from app.normalization.body_site import normalize_body_site
from app.normalization.condition import normalize_condition
from app.normalization.host_species import normalize_host_species
from app.normalization.sample_size import normalize_sample_size
from app.normalization.sequencing_type import normalize_sequencing_type
from app.models.unified_qa import UnifiedQA
from app.services.bugsigdb_check import is_in_bugsigdb
from app.services.cache_manager import CacheManager
from app.services.data_retrieval import PubMedRetriever
from app.utils.config import (
    DEFAULT_MODEL,
    GEMINI_API_KEY,
    NCBI_API_KEY,
    ANALYSIS_TIMEOUT,
    CACHE_VALIDITY_HOURS,
)
from app.api.utils.api_utils import get_current_timestamp

logger = logging.getLogger(__name__)

_unified_qa: Optional[UnifiedQA] = None
_pubmed_retriever: Optional[PubMedRetriever] = None
_cache_manager: Optional[CacheManager] = None


def get_unified_qa() -> Optional[UnifiedQA]:
    """Get or initialize UnifiedQA instance."""
    global _unified_qa
    if _unified_qa is None:
        try:
            _unified_qa = UnifiedQA(use_gemini=True, gemini_api_key=GEMINI_API_KEY)
            logger.info("UnifiedQA service initialized successfully")
        except Exception as e:
            logger.error(f"Failed to initialize UnifiedQA: {e}")
            # Try fallback to GeminiQA directly
            try:
                from app.models.gemini_qa import GeminiQA

                _unified_qa = GeminiQA(api_key=GEMINI_API_KEY)
                logger.info("Fallback to GeminiQA successful")
            except Exception as e2:
                logger.error(f"Fallback to GeminiQA also failed: {e2}")
                _unified_qa = None
    return _unified_qa


def get_pubmed_retriever() -> Optional[PubMedRetriever]:
    """Get or initialize PubMedRetriever instance."""
    global _pubmed_retriever
    if _pubmed_retriever is None:
        try:
            _pubmed_retriever = PubMedRetriever(api_key=NCBI_API_KEY)
        except Exception as e:
            logger.error(f"Failed to initialize PubMedRetriever: {e}")
            _pubmed_retriever = None
    return _pubmed_retriever


def get_cache_manager() -> CacheManager:
    """Get or initialize CacheManager instance."""
    global _cache_manager
    if _cache_manager is None:
        _cache_manager = CacheManager()
    return _cache_manager


ESSENTIAL_FIELDS: Dict[str, str] = {
    "host_species": "What host species is being studied in this research?",
    "body_site": "What body site or anatomical location was sampled for microbiome analysis?",
    "condition": "What disease, treatment, or condition is being studied?",
    "sequencing_type": "What sequencing method or molecular technique was used?",
    "taxa_level": "What taxonomic level was analyzed (phylum, genus, species, etc.)?",
    "sample_size": "How many samples or participants were included in the study?",
}

EXTRACTION_PROMPT = """
You are a biomedical literature analyst specializing in microbiome research.
Analyze the following PubMed abstract and extract structured metadata.
Return ONLY a valid JSON object with no markdown, no explanation, no extra text.

ABSTRACT:
{abstract}

METADATA:
Title: {title}
Journal: {journal}
Year: {year}

Extract the following fields and return as JSON:

{{
  "host_species_raw": "<species mentioned, e.g. 'Homo sapiens' or 'mice and rats'>",
  "body_site_raw": "<anatomical location of sample collection, e.g. 'feces' or 'gut and oral cavity'>",
  "condition_raw": "<disease or condition studied, e.g. 'Parkinson disease' or 'healthy volunteers'>",
  "sequencing_type_raw": "<sequencing method used, e.g. '16S rRNA gene sequencing' or 'shotgun metagenomics'>",
  "sample_size_raw": <integer total number of participants/samples, or null if not mentioned>,
  "has_differential_abundance": <true if paper reports taxa/features significantly more/less abundant between groups, else false>,
  "differential_abundance_confidence": <float 0.0-1.0 confidence in the above assessment>
}}

Rules:
- For host_species_raw: give the species name(s) as mentioned. If multiple species, list all separated by " and ".
- For body_site_raw: give the anatomical site(s) as mentioned. If multiple, list all separated by " and ".
- For condition_raw: give only the disease/condition name, stripped of clinical context words like "patients with" or "diagnosed with". If the study compares diseased vs healthy, give the disease name only.
- For sequencing_type_raw: give only the sequencing method name.
- For sample_size_raw: give ONLY an integer. If stated as words (e.g. "forty-two"), convert to number. If a range, give the total or larger number.
- For has_differential_abundance: true ONLY if the abstract explicitly states that specific microbial taxa or features differ statistically between groups.
- For differential_abundance_confidence: 1.0 if clearly stated, 0.7 if strongly implied, 0.5 if ambiguous, 0.2 if unlikely, 0.0 if clearly absent.
"""


def extract_year(pub_date_text: Any) -> int | None:
    """Extract year from publication date strings like MedlineDate values."""
    match = re.search(r"\b(19|20)\d{2}\b", str(pub_date_text))
    return int(match.group(0)) if match else None

EXTRACTION_PROMPT = """
You are a biomedical literature analyst specializing in microbiome research.
Analyze the following PubMed abstract and extract structured metadata.
Return ONLY a valid JSON object with no markdown, no explanation, no extra text.

ABSTRACT:
{abstract}

METADATA:
Title: {title}
Journal: {journal}
Year: {year}

Extract the following fields and return as JSON:

{{
  "host_species_raw": "<species mentioned, e.g. 'Homo sapiens' or 'mice and rats'>",
  "body_site_raw": "<anatomical location of sample collection, e.g. 'feces' or 'gut and oral cavity'>",
  "condition_raw": "<disease or condition studied, e.g. 'Parkinson disease' or 'healthy volunteers'>",
  "sequencing_type_raw": "<sequencing method used, e.g. '16S rRNA gene sequencing' or 'shotgun metagenomics'>",
  "sample_size_raw": <integer total number of participants/samples, or null if not mentioned>,
  "has_differential_abundance": <true if paper reports taxa/features significantly more/less abundant between groups, else false>,
  "differential_abundance_confidence": <float 0.0-1.0 confidence in the above assessment>
}}

Rules:
- For host_species_raw: give the species name(s) as mentioned. If multiple species, list all separated by " and ".
- For body_site_raw: give the anatomical site(s) as mentioned. If multiple, list all separated by " and ".
- For condition_raw: give only the disease/condition name, stripped of clinical context words like "patients with" or "diagnosed with". If the study compares diseased vs healthy, give the disease name only.
- For sequencing_type_raw: give only the sequencing method name.
- For sample_size_raw: give ONLY an integer. If stated as words (e.g. "forty-two"), convert to number. If a range, give the total or larger number.
- For has_differential_abundance: true ONLY if the abstract explicitly states that specific microbial taxa or features differ statistically between groups.
- For differential_abundance_confidence: 1.0 if clearly stated, 0.7 if strongly implied, 0.5 if ambiguous, 0.2 if unlikely, 0.0 if clearly absent.
"""


def extract_year(pub_date_text: Any) -> int | None:
    """Extract year from publication date strings like MedlineDate values."""
    match = re.search(r"\b(19|20)\d{2}\b", str(pub_date_text))
    return int(match.group(0)) if match else None


def _build_field_result(value: Any, status: str, confidence: float = 1.0) -> Dict[str, Any]:
    return {
        "value": "" if status == "ABSENT" else ("" if value is None else str(value)),
        "status": status,
        "confidence": float(confidence),
        "reason_if_missing": "" if status != "ABSENT" else "Information not found in the paper",
    }


def _parse_json_object(raw_text: str) -> Dict[str, Any]:
    if not raw_text:
        return {}
    try:
        return json.loads(raw_text)
    except Exception:
        start = raw_text.find("{")
        end = raw_text.rfind("}") + 1
        if start != -1 and end > start:
            try:
                return json.loads(raw_text[start:end])
            except Exception:
                return {}
    return {}


async def _extract_structured_metadata(
    *, context_text: str, title: str, journal: str, year: Any
) -> Dict[str, Any]:
    """Run one unified extraction call and return parsed JSON dict."""
    unified_qa = get_unified_qa()
    if unified_qa is None:
        return {}
    prompt = EXTRACTION_PROMPT.format(
        abstract=context_text or "",
        title=title or "",
        journal=journal or "",
        year=year if year is not None else "",
    )
    chat_call = unified_qa.chat(prompt)
    response = await asyncio.wait_for(chat_call, timeout=ANALYSIS_TIMEOUT) if asyncio.iscoroutine(chat_call) else chat_call
    answer = response.get("text", "")
    return _parse_json_object(answer)


def _field_results_from_unified_payload(payload: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
    """Map unified prompt JSON payload to internal field structure."""
    host_val, host_status = normalize_host_species(payload.get("host_species_raw"))
    body_val, body_status = normalize_body_site(payload.get("body_site_raw"))
    cond_val, cond_status = normalize_condition(payload.get("condition_raw"))
    seq_val, seq_status = normalize_sequencing_type(payload.get("sequencing_type_raw"))
    sample_val, sample_status = normalize_sample_size(payload.get("sample_size_raw"))

    return {
        "host_species": _build_field_result(host_val, host_status),
        "body_site": _build_field_result(body_val, body_status),
        "condition": _build_field_result(cond_val, cond_status),
        "sequencing_type": _build_field_result(seq_val, seq_status),
        "sample_size": _build_field_result(sample_val, sample_status),
        # Keep existing field for backward compatibility with API consumers.
        "taxa_level": create_empty_field_result("taxa_level"),
    }


def _normalize_extracted_fields(field_results: Dict[str, Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
    """Normalize raw extracted values to curator-desk canonical forms."""
    normalized = dict(field_results or {})

    def _field_value(name: str) -> Any:
        return (normalized.get(name) or {}).get("value")

    mappings = {
        "host_species": normalize_host_species,
        "body_site": normalize_body_site,
        "condition": normalize_condition,
        "sequencing_type": normalize_sequencing_type,
        "sample_size": normalize_sample_size,
    }

    for key, normalizer in mappings.items():
        current = dict(normalized.get(key) or {})
        value, status = normalizer(_field_value(key))
        current["value"] = value
        current["status"] = status
        current["confidence"] = float(current.get("confidence", 0.0) or 0.0)
        if status == "ABSENT":
            current["value"] = ""
        normalized[key] = current

    return normalized


def _build_field_result(value: Any, status: str, confidence: float = 1.0) -> Dict[str, Any]:
    return {
        "value": "" if status == "ABSENT" else ("" if value is None else str(value)),
        "status": status,
        "confidence": float(confidence),
        "reason_if_missing": "" if status != "ABSENT" else "Information not found in the paper",
    }


def _parse_json_object(raw_text: str) -> Dict[str, Any]:
    if not raw_text:
        return {}
    try:
        return json.loads(raw_text)
    except Exception:
        start = raw_text.find("{")
        end = raw_text.rfind("}") + 1
        if start != -1 and end > start:
            try:
                return json.loads(raw_text[start:end])
            except Exception:
                return {}
    return {}


async def _extract_structured_metadata(
    *, context_text: str, title: str, journal: str, year: Any
) -> Dict[str, Any]:
    """Run one unified extraction call and return parsed JSON dict."""
    unified_qa = get_unified_qa()
    if unified_qa is None:
        return {}

    prompt = EXTRACTION_PROMPT.format(
        abstract=context_text or "",
        title=title or "",
        journal=journal or "",
        year=year if year is not None else "",
    )
    chat_call = unified_qa.chat(prompt)
    response = (
        await asyncio.wait_for(chat_call, timeout=ANALYSIS_TIMEOUT)
        if asyncio.iscoroutine(chat_call)
        else chat_call
    )
    return _parse_json_object(response.get("text", ""))


def _field_results_from_unified_payload(payload: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
    """Map unified prompt JSON payload to internal field structure."""
    host_val, host_status = normalize_host_species(payload.get("host_species_raw"))
    body_val, body_status = normalize_body_site(payload.get("body_site_raw"))
    cond_val, cond_status = normalize_condition(payload.get("condition_raw"))
    seq_val, seq_status = normalize_sequencing_type(payload.get("sequencing_type_raw"))
    sample_val, sample_status = normalize_sample_size(payload.get("sample_size_raw"))

    return {
        "host_species": _build_field_result(host_val, host_status),
        "body_site": _build_field_result(body_val, body_status),
        "condition": _build_field_result(cond_val, cond_status),
        "sequencing_type": _build_field_result(seq_val, seq_status),
        "sample_size": _build_field_result(sample_val, sample_status),
        # Keep existing field for backward compatibility with API consumers.
        "taxa_level": create_empty_field_result("taxa_level"),
    }


async def analyze_paper_simple(pmid: str) -> Optional[Dict[str, Any]]:
    """Extract BugSigDB fields from a paper.

    Uses v1 API flow: direct LLM queries per field. Fast but less accurate than RAG.
    Checks cache first, then fetches from PubMed if needed.

    Returns:
        Dict with field results, or None if paper can't be retrieved.
    """
    try:
        cache_manager = get_cache_manager()
        pubmed_retriever = get_pubmed_retriever()

        if pubmed_retriever is None:
            logger.error(
                "PubMedRetriever not available. Check NCBI_API_KEY configuration."
            )
            return None

        cached = cache_manager.get_analysis_result(pmid)
        if cached and cache_manager.is_cache_valid(
            cached.get("timestamp", ""), max_age_hours=CACHE_VALIDITY_HOURS
        ):
            logger.info(f"Returning cached analysis for PMID: {pmid}")
            return cached.get("analysis_data")

        logger.info(f"Starting analysis for PMID: {pmid}")

        texts = await pubmed_retriever.get_texts_for_analysis_async(pmid)
        if not texts.get("title") and not texts.get("abstract"):
            logger.warning(f"No content found for PMID: {pmid}")
            return None

        # Prepare text for analysis
        title = texts.get("title", "")
        abstract = texts.get("abstract", "")
        full_text = texts.get("full_text", "")

        # Combine text (prioritize abstract, then full text)
        analysis_text = abstract
        if full_text and len(analysis_text) < 1000:
            analysis_text += f"\n\n{full_text[:2000]}"

        if not analysis_text.strip():
            logger.warning(f"No analyzable text found for PMID: {pmid}")
            return None

        year = extract_year(texts.get("publication_date", ""))
        payload = await _extract_structured_metadata(
            context_text=analysis_text,
            title=title,
            journal=texts.get("journal", ""),
            year=year if year is not None else "",
        )
        field_results = _field_results_from_unified_payload(payload)
        try:
            has_diff_abund = bool(payload.get("has_differential_abundance", False))
            diff_abund_conf = float(payload.get("differential_abundance_confidence", 0.0))
        except (TypeError, ValueError):
            has_diff_abund, diff_abund_conf = detect_differential_abundance(analysis_text)

        result = {
            "pmid": pmid,
            "title": title,
            "authors": texts.get("authors", []),
            "journal": texts.get("journal", ""),
            "publication_date": texts.get("publication_date", ""),
            "year": year if year is not None else "",
            "has_differential_abundance": has_diff_abund,
            "differential_abundance_confidence": diff_abund_conf,
            "in_bugsigdb": is_in_bugsigdb(pmid),
            "fields": field_results,
            "analysis_timestamp": get_current_timestamp(),
            "model_used": DEFAULT_MODEL,
        }

        logger.info(f"Analysis completed for PMID: {pmid}")

        try:
            avg_confidence = 0.0
            if field_results:
                confidences = [
                    float(field_data.get("confidence", 0.0))
                    for field_data in field_results.values()
                ]
                if confidences:
                    avg_confidence = sum(confidences) / len(confidences)

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
                confidence=avg_confidence,
            )
        except Exception as cache_error:
            logger.warning(f"Unable to cache analysis for PMID {pmid}: {cache_error}")

        return result

    except Exception as e:
        logger.error(f"Error in simple analysis for PMID {pmid}: {e}")
        return None


async def analyze_paper_with_rag(
    pmid: str, rag_config: Optional[Dict] = None, use_rag: bool = True
) -> Optional[Dict]:
    """Analyze paper with RAG features enabled."""
    import time
    from datetime import datetime

    start_time = time.time()

    try:
        cache_manager = get_cache_manager()
        pubmed_retriever = get_pubmed_retriever()

        if pubmed_retriever is None:
            logger.error(
                "PubMedRetriever not available. Check NCBI_API_KEY configuration."
            )
            return None

        rag_config_dict = None
        if rag_config:
            if hasattr(rag_config, "model_dump"):
                rag_config_dict = rag_config.model_dump(exclude_none=True)
            elif hasattr(rag_config, "dict"):
                rag_config_dict = rag_config.dict()
            elif isinstance(rag_config, dict):
                rag_config_dict = rag_config

        use_rag_final = use_rag and (
            rag_config_dict is None or rag_config_dict.get("enabled", True)
        )

        logger.info(
            f"Starting RAG-enabled analysis for PMID: {pmid} (RAG: {use_rag_final})"
        )

        texts = await pubmed_retriever.get_texts_for_analysis_async(pmid)
        if not texts.get("title") and not texts.get("abstract"):
            logger.warning(f"No content found for PMID: {pmid}")
            return None

        title = texts.get("title", "")
        abstract = texts.get("abstract", "")
        full_text = texts.get("full_text", "")

        analysis_text = abstract
        if full_text and len(analysis_text) < 1000:
            analysis_text += f"\n\n{full_text[:2000]}"

        if not analysis_text.strip():
            logger.warning(f"No analyzable text found for PMID: {pmid}")
            return None

        chunks = None
        if use_rag_final and full_text and len(full_text) > 1000:
            try:
                from app.utils.chunking import ChunkingService

                chunker = ChunkingService(chunk_chars=3000, overlap=100)
                chunks = await chunker.chunk_markdown(
                    markdown=full_text, doc_name=f"PMID_{pmid}", doc_key=pmid
                )
                logger.info(f"Created {len(chunks)} chunks for advanced RAG")
            except Exception as chunk_error:
                logger.warning(
                    f"Failed to create chunks for advanced RAG: {chunk_error}"
                )
                chunks = None

        processing_time = time.time() - start_time
        year = extract_year(texts.get("publication_date", ""))
        context_for_prompt = analysis_text
        if use_rag_final and chunks:
            try:
                from app.services.advanced_rag import AdvancedRAGService

                rag_service = AdvancedRAGService(
                    rerank_method=(
                        rag_config_dict.get("rerank_method", "hybrid")
                        if rag_config_dict
                        else "hybrid"
                    ),
                    evidence_k=(rag_config_dict.get("evidence_k") if rag_config_dict else None),
                    max_sources=(rag_config_dict.get("max_sources") if rag_config_dict else None),
                    use_10_scale=(rag_config_dict.get("use_10_scale", True) if rag_config_dict else True),
                )
                context_for_prompt = await rag_service.get_contextual_context(
                    chunks=chunks,
                    query="Extract host species, body site, condition, sequencing type, sample size and differential abundance metadata.",
                    top_k=(rag_config_dict.get("top_k_chunks") if rag_config_dict else None),
                    evidence_k=(rag_config_dict.get("evidence_k") if rag_config_dict else None),
                    max_sources=(rag_config_dict.get("max_sources") if rag_config_dict else None),
                )
            except Exception as rag_error:
                logger.warning("Unified prompt RAG context fallback: %s", rag_error)

        payload = await _extract_structured_metadata(
            context_text=context_for_prompt,
            title=title,
            journal=texts.get("journal", ""),
            year=year if year is not None else "",
        )
        field_results = _field_results_from_unified_payload(payload)
        try:
            has_diff_abund = bool(payload.get("has_differential_abundance", False))
            diff_abund_conf = float(payload.get("differential_abundance_confidence", 0.0))
        except (TypeError, ValueError):
            has_diff_abund, diff_abund_conf = detect_differential_abundance(analysis_text)

        result = {
            "pmid": pmid,
            "title": title,
            "authors": texts.get("authors", []),
            "journal": texts.get("journal", ""),
            "publication_date": texts.get("publication_date", ""),
            "year": year if year is not None else "",
            "has_differential_abundance": has_diff_abund,
            "differential_abundance_confidence": diff_abund_conf,
            "in_bugsigdb": is_in_bugsigdb(pmid),
            "fields": field_results,
            "analysis_timestamp": get_current_timestamp(),
            "model_used": DEFAULT_MODEL,
            "processing_time": processing_time,
            "rag_enabled": use_rag_final,
            "rag_stats": None,
            "rag_config_used": rag_config_dict if use_rag_final else None,
        }

        if use_rag_final and chunks:
            try:
                rag_metrics = {}
                try:
                    from app.services.advanced_rag import AdvancedRAGService

                    temp_service = AdvancedRAGService(
                        rerank_method=(
                            rag_config_dict.get("rerank_method", "hybrid")
                            if rag_config_dict
                            else "hybrid"
                        ),
                        evidence_k=(
                            rag_config_dict.get("evidence_k")
                            if rag_config_dict
                            else None
                        ),
                        max_sources=(
                            rag_config_dict.get("max_sources")
                            if rag_config_dict
                            else None
                        ),
                        use_10_scale=(
                            rag_config_dict.get("use_10_scale", True)
                            if rag_config_dict
                            else True
                        ),
                    )
                    rag_metrics = temp_service.get_rerank_metrics()
                except:
                    pass

                result["rag_stats"] = {
                    "chunks_processed": len(chunks),
                    "chunks_ranked": rag_metrics.get("chunks_reranked", len(chunks)),
                    "chunks_summarized": min(
                        (
                            rag_config_dict.get("top_k_chunks", 10)
                            if rag_config_dict
                            else 10
                        ),
                        len(chunks),
                    ),
                    "avg_relevance_score": rag_metrics.get("avg_relevance_score", 0.75),
                    "max_relevance_score": rag_metrics.get("max_relevance_score", 0.0),
                    "min_relevance_score": rag_metrics.get("min_relevance_score", 0.0),
                    "avg_confidence": (
                        sum(f.get("confidence", 0.0) for f in field_results.values())
                        / len(field_results)
                        if field_results
                        else 0.0
                    ),
                    "rerank_method": (
                        rag_config_dict.get("rerank_method", "hybrid")
                        if rag_config_dict
                        else "hybrid"
                    ),
                    "summary_length": (
                        rag_config_dict.get("summary_length", "medium")
                        if rag_config_dict
                        else "medium"
                    ),
                    "evidence_k": (
                        rag_config_dict.get("evidence_k") if rag_config_dict else None
                    ),
                    "max_sources": (
                        rag_config_dict.get("max_sources") if rag_config_dict else None
                    ),
                    "use_10_scale": (
                        rag_config_dict.get("use_10_scale", True)
                        if rag_config_dict
                        else True
                    ),
                    "rerank_processing_time": rag_metrics.get("processing_time", 0.0),
                    "avg_chunk_processing_time": rag_metrics.get(
                        "avg_chunk_processing_time", 0.0
                    ),
                    "processing_time": processing_time,
                }
            except Exception as e:
                logger.warning(f"Could not collect RAG stats: {e}")

        logger.info(
            f"RAG analysis completed for PMID: {pmid} in {processing_time:.2f}s"
        )

        try:
            avg_confidence = (
                sum(f.get("confidence", 0.0) for f in field_results.values())
                / len(field_results)
                if field_results
                else 0.0
            )
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
                confidence=avg_confidence,
            )
        except Exception as cache_error:
            logger.warning(f"Unable to cache analysis for PMID {pmid}: {cache_error}")

        return result

    except Exception as e:
        logger.error(f"Error in RAG-enabled analysis for PMID {pmid}: {e}")
        return None


async def analyze_single_field(
    text: str,
    field_name: str,
    question: str,
    pmid: str,
    chunks: Optional[List] = None,
    rag_config: Optional[Dict] = None,
) -> Dict:
    """Extract a single field value from text using LLM."""
    try:
        if chunks and rag_config and rag_config.get("enabled", True):
            try:
                from app.services.advanced_rag import AdvancedRAGService
                from app.services.contextual_summarization import SummarizationConfig

                summary_config = SummarizationConfig(
                    summary_length=rag_config.get("summary_length", "medium"),
                    quality=rag_config.get("summary_quality", "balanced"),
                    use_cache=rag_config.get("use_cache", True),
                )

                rag_service = AdvancedRAGService(
                    summary_provider=rag_config.get("summary_provider"),
                    summary_model=rag_config.get("summary_model"),
                    rerank_method=rag_config.get("rerank_method"),
                    cache_dir=None,  # Use default
                    evidence_k=rag_config.get("evidence_k"),
                    max_sources=rag_config.get("max_sources"),
                    use_10_scale=rag_config.get("use_10_scale", True),
                )

                if rag_config.get("summary_length") or rag_config.get(
                    "summary_quality"
                ):
                    rag_service.summarization_service.config = summary_config

                top_k = rag_config.get("top_k_chunks")
                evidence_k = rag_config.get("evidence_k")
                max_sources = rag_config.get("max_sources")
                contextual_context = await rag_service.get_contextual_context(
                    chunks=chunks,
                    query=question,
                    top_k=top_k,
                    evidence_k=evidence_k,
                    max_sources=max_sources,
                )

                logger.info(
                    f"Using advanced RAG for field {field_name} (context length: {len(contextual_context)}, top_k={top_k})"
                )
                context_text = contextual_context
            except Exception as rag_error:
                logger.warning(
                    f"Advanced RAG failed for field {field_name}, falling back to simple text: {rag_error}"
                )
                context_text = text[:2000]
        elif chunks:
            try:
                from app.services.advanced_rag import AdvancedRAGService

                rag_service = AdvancedRAGService()
                contextual_context = await rag_service.get_contextual_context(
                    chunks=chunks, query=question, top_k=None
                )
                logger.info(
                    f"Using advanced RAG (default config) for field {field_name}"
                )
                context_text = contextual_context
            except Exception as rag_error:
                logger.warning(
                    f"Advanced RAG failed for field {field_name}, falling back to simple text: {rag_error}"
                )
                context_text = text[:2000]
        else:
            context_text = text[:2000]

        prompt = f"""
        Context: {context_text}

        Question: {question}

        Please provide a specific answer based on the context. If the information is not available, clearly state that.

        Respond in this JSON format:
        {{
            "value": "specific answer or null if not found",
            "status": "PRESENT|PARTIALLY_PRESENT|ABSENT",
            "confidence": 0.0-1.0,
            "reason_if_missing": "explanation if absent"
        }}
        """

        unified_qa = get_unified_qa()
        if unified_qa is None:
            logger.error(
                "UnifiedQA service not available. Check GEMINI_API_KEY configuration."
            )
            return create_empty_field_result(field_name)

        chat_call = unified_qa.chat(prompt)
        # Support both async and mocked sync calls (for tests)
        if asyncio.iscoroutine(chat_call):
            response = await asyncio.wait_for(chat_call, timeout=ANALYSIS_TIMEOUT)
        else:
            response = chat_call

        if response.get("text", "").startswith("Error:"):
            logger.warning(
                f"UnifiedQA returned error for field {field_name}: {response.get('text')}"
            )
            if (
                "Paper-QA" in str(response.get("text", ""))
                or "router" in str(response.get("text", "")).lower()
            ):
                logger.info(
                    f"Attempting fallback to direct Gemini API for field {field_name}"
                )
                try:
                    from app.models.gemini_qa import GeminiQA

                    gemini_qa = GeminiQA(api_key=GEMINI_API_KEY)
                    response = await asyncio.wait_for(
                        gemini_qa.chat(prompt), timeout=ANALYSIS_TIMEOUT
                    )
                    logger.info(
                        f"Fallback to GeminiQA successful for field {field_name}"
                    )
                except Exception as fallback_error:
                    logger.error(f"Fallback to GeminiQA also failed: {fallback_error}")
                    return create_empty_field_result(field_name)

        answer = response.get("text", "")
        confidence = response.get("confidence", 0.0)

        try:
            json_start = answer.find("{")
            json_end = answer.rfind("}") + 1
            if json_start != -1 and json_end > json_start:
                json_str = answer[json_start:json_end]
                field_data = json.loads(json_str)
                return {
                    "value": field_data.get("value"),
                    "status": field_data.get("status", "ABSENT"),
                    "confidence": float(field_data.get("confidence", confidence)),
                    "reason_if_missing": field_data.get("reason_if_missing", ""),
                }
        except (json.JSONDecodeError, KeyError):
            pass

        if not answer or confidence < 0.3:
            return create_empty_field_result(field_name)

        if confidence >= 0.8 and answer.lower() not in [
            "not found",
            "not available",
            "none",
            "n/a",
        ]:
            status = "PRESENT"
        elif confidence >= 0.4:
            status = "PARTIALLY_PRESENT"
        else:
            status = "ABSENT"

        return {
            "value": answer if status != "ABSENT" else None,
            "status": status,
            "confidence": confidence,
            "reason_if_missing": (
                "" if status != "ABSENT" else "Information not found in the paper"
            ),
        }

    except asyncio.TimeoutError:
        logger.warning(f"Field {field_name} analysis timed out for PMID {pmid}")
        return create_empty_field_result(field_name)
    except Exception as e:
        logger.error(f"Error analyzing field {field_name} for PMID {pmid}: {e}")
        return create_empty_field_result(field_name)


def create_empty_field_result(field_name: str) -> Dict:
    """Return empty result when field extraction fails."""
    return {
        "value": None,
        "status": "ABSENT",
        "confidence": 0.0,
        "reason_if_missing": "Analysis failed or timed out",
    }


def detect_differential_abundance(text: str) -> Tuple[bool, float]:
    """Heuristic differential abundance detector.

    curator-desk uses this as a triage filter. We keep it lightweight (no extra LLM call).
    Returns:
      (has_differential_abundance, confidence[0..1])
    """
    if not text or not str(text).strip():
        return False, 0.0

    t = str(text).lower()

    # Strong signals (explicit)
    strong_patterns = [
        r"\bdifferential(?:ly)? abundant\b",
        r"\bdifferential abundance\b",
        r"\bsignificant(?:ly)? (?:different|difference)\b",
        r"\benriched\b",
        r"\bdepleted\b",
        r"\bup-?regulated\b",
        r"\bdown-?regulated\b",
        r"\bfdr\b",
        r"\badjusted p(?:-|\s*)value\b",
    ]

    # Medium signals (comparison language)
    medium_patterns = [
        r"\bcompared to\b",
        r"\bversus\b|\bvs\.\b|\bvs\b",
        r"\bdifference(?:s)? in\b",
        r"\bassociated with\b",
        r"\bincrease(?:d)?\b|\bdecrease(?:d)?\b",
    ]

    # Weak signals (general analysis language)
    weak_patterns = [
        r"\b(relative )?abundance\b",
        r"\bcomposition\b",
        r"\bdysbiosis\b",
        r"\b(beta|alpha) diversity\b",
        r"\bcommunity structure\b",
    ]

    def _count_any(patterns: List[str]) -> int:
        return sum(1 for p in patterns if re.search(p, t, flags=re.IGNORECASE))

    strong = _count_any(strong_patterns)
    medium = _count_any(medium_patterns)
    weak = _count_any(weak_patterns)

    # Score in [0, 1]. Strong evidence dominates; medium/weak nudge confidence upward.
    score = 0.0
    if strong:
        score = 0.75 + min(0.25, 0.08 * (strong - 1) + 0.05 * medium + 0.03 * weak)
    elif medium:
        score = 0.45 + min(0.35, 0.08 * (medium - 1) + 0.05 * weak)
    elif weak:
        score = min(0.35, 0.10 + 0.08 * weak)

    score = max(0.0, min(1.0, score))
    return score >= 0.6, float(score)
