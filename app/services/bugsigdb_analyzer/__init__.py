"""
BugSigDB Analyzer — BioAnalyzer
=================================
Extracts BugSigDB-compatible fields from PubMed papers using a single
unified LLM call, with heuristic and post-processing fallbacks.

Output contract (result dict)
------------------------------
Every public entry-point (analyze_paper_simple, analyze_paper_with_rag)
returns a dict with EXACTLY the following top-level keys.  data.R /
normalize_dataset() and the curator desk depend on this shape.

    pmid                             str
    title                            str
    authors                          List[str]
    journal                          str
    publication_date                 str
    year                             int | ""
    has_differential_abundance       bool
    differential_abundance_confidence float
    in_bugsigdb                      bool
    fields                           Dict[str, FieldDict]   (see below)
    analysis_timestamp               str   (ISO-8601)
    model_used                       str

fields keys  →  curator table column pair
-----------------------------------------
  "host_species"    →  "Host Species"       /  "Host Species Status"
  "body_site"       →  "Body Site"          /  "Body Site Status"
  "condition"       →  "Condition"          /  "Condition Status"
  "sequencing_type" →  "Sequencing Type"    /  "Sequencing Type Status"
  "sample_size"     →  "Sample Size"        /  "Sample Size Status"
  "taxa_level"      →  (hidden in curator table, present in API)

Each FieldDict has:
    value               str
    status              "PRESENT" | "PARTIALLY_PRESENT" | "ABSENT"
    confidence          float
    ontology_id         str
    mapping_confidence  float
    reason_if_missing   str
"""

from app.models.unified_qa import UnifiedQA
from app.services.bugsigdb_check import is_in_bugsigdb
from app.services.cache_manager import CacheManager
from app.services.data_retrieval import PubMedRetriever

from .constants import (
    ESSENTIAL_FIELDS,
    EXTRACTION_PROMPT,
    FIELD_KEYS,
    STATUS_COLUMNS,
)
from .field_extraction import (
    _avg_confidence,
    _build_curation_summary,
    _build_field_result,
    _build_field_result_from_term,
    _field_results_from_unified_payload,
    _heuristic_payload_from_text,
    _is_low_quality_cached_result,
    _parse_json_object,
    _postprocess_field_results,
    _resolve_diff_abundance,
    create_empty_field_result,
    detect_differential_abundance,
    extract_year,
)
from .parsing import (
    _classify_section_title,
    _local_tag,
    _parse_pmc_sections,
    _truncate,
    prepare_analysis_context,
)
from .rag_analysis import analyze_paper_with_rag, analyze_single_field
from .simple_analysis import analyze_paper_simple
from .singletons import get_cache_manager, get_pubmed_retriever, get_unified_qa

__all__ = [
    "analyze_paper_simple",
    "analyze_paper_with_rag",
    "analyze_single_field",
    "is_in_bugsigdb",
    "get_unified_qa",
    "get_pubmed_retriever",
    "get_cache_manager",
    "UnifiedQA",
    "PubMedRetriever",
    "CacheManager",
    "FIELD_KEYS",
    "STATUS_COLUMNS",
    "ESSENTIAL_FIELDS",
    "EXTRACTION_PROMPT",
    "prepare_analysis_context",
    "_parse_pmc_sections",
    "_classify_section_title",
    "_local_tag",
    "_truncate",
    "_build_field_result",
    "_build_field_result_from_term",
    "_is_low_quality_cached_result",
    "_parse_json_object",
    "_heuristic_payload_from_text",
    "_build_curation_summary",
    "_postprocess_field_results",
    "_field_results_from_unified_payload",
    "_avg_confidence",
    "_resolve_diff_abundance",
    "extract_year",
    "create_empty_field_result",
    "detect_differential_abundance",
]
