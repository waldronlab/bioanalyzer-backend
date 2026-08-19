"""
Pydantic models for API requests and responses.
"""

from pydantic import BaseModel, Field
from typing import Dict, List, Optional, Union, Any


class HealthResponse(BaseModel):
    """Health check response model."""

    status: str
    timestamp: str
    version: str


class ConfigResponse(BaseModel):
    """Configuration response model."""

    available_models: List[str]
    default_model: str
    frontend_timeout: int
    gemini_timeout: int
    analysis_timeout: int
    api_timeout: int


class MetricsResponse(BaseModel):
    """Metrics response model."""

    total_requests: int
    successful_requests: int
    failed_requests: int
    average_response_time: float
    cache_hit_rate: float
    memory_usage: Dict[str, Any]


class FieldAnalysis(BaseModel):
    """Individual field analysis result.

    Mirrors app.models.extraction_schemas.FieldResult - the documented
    "Output contract" in app/services/bugsigdb_analyzer/__init__.py's module
    docstring states every FieldDict returned by BOTH analyze_paper_simple
    (v1) and analyze_paper_with_rag (v2) has these 9 keys (v1's route
    returns Dict[str, Any], so it was never schema-filtered and always
    exposed all 9; v2's route returns this model, so until this fix it
    silently dropped ontology_id/mapping_confidence/mapping_tier/
    mapping_candidates/raw - real data BioAnalyzer already produces, e.g.
    scripts/cli_rendering.py reads ontology_id/mapping_tier/
    mapping_candidates directly off this same dict shape to build the
    curator-desk CSV's ontology columns). Defaults below match
    FieldResult's own field-by-field defaults exactly, so an ungrounded
    field serializes identically to how FieldResult.absent() would - no
    value is fabricated for a field grounding didn't produce.
    """

    status: str  # PRESENT, PARTIALLY_PRESENT, ABSENT
    value: Optional[str]
    confidence: float
    reason_if_missing: Optional[str]
    # No default producer: _build_field_result() (the real field-extraction
    # code, see app/services/bugsigdb_analyzer/field_extraction.py) never
    # emits a "suggestions" key - only "reason_if_missing". Without a
    # default here, every genuine (non-hand-mocked) v2 analysis result
    # failed Pydantic response validation with a "Field required" error,
    # turning into an HTTP 500 regardless of the actual analysis outcome.
    # None is the correct default, not a fabricated value - it faithfully
    # represents "not currently produced," and any future producer that
    # does supply a suggestion string still validates normally.
    suggestions: Optional[str] = None
    # --- Ontology-grounding metadata (was silently dropped by v2 responses
    # prior to this fix - see class docstring) ---
    ontology_id: str = ""
    mapping_confidence: float = 0.0
    mapping_tier: str = "none"  # "auto" | "review" | "none"
    mapping_candidates: List[Dict[str, str]] = Field(default_factory=list)
    raw: str = ""


class PaperAnalysisResult(BaseModel):
    """Complete paper analysis result.

    Field set mirrors the "Output contract (result dict)" documented in
    app/services/bugsigdb_analyzer/__init__.py's module docstring - both
    analyze_paper_simple (v1) and analyze_paper_with_rag (v2) always
    populate year/has_differential_abundance/differential_abundance_confidence
    (simple_analysis.py and rag_analysis.py's result-dict assembly), but
    this model didn't declare them, so v2/batch silently dropped all three
    via response-model filtering (v1 returns Dict[str, Any], never
    filtered, so v1 was unaffected - same defect class as the in_bugsigdb
    gap fixed above, just not caught in that pass).
    """

    pmid: str
    title: Optional[str]
    authors: Optional[List[str]]
    journal: Optional[str]
    publication_date: Optional[str]
    # Real type is int (from extract_year()) or "" when no year was found
    # (see field_extraction.py::extract_year + simple_analysis.py/
    # rag_analysis.py's "year if year is not None else ''") - never
    # fabricated when absent.
    year: Union[int, str] = ""
    has_differential_abundance: bool = False
    differential_abundance_confidence: float = 0.0
    fields: Dict[str, FieldAnalysis]
    curation_summary: str
    analysis_timestamp: str
    processing_time: float
    model_used: str
    # True when this PMID is already present in BugSigDB (mirrors the
    # analyzer result dict's "in_bugsigdb" key - was missing here, which
    # silently dropped it from every /api/v2 response via response-model
    # filtering even though it was computed correctly upstream).
    in_bugsigdb: bool = False


# RAG-specific models for v2 API
class RAGConfig(BaseModel):
    """RAG configuration for analysis."""

    enabled: bool = True
    top_k_chunks: Optional[int] = None  # Number of top chunks to use
    evidence_k: Optional[int] = (
        None  # Number of evidence chunks to retrieve before re-ranking
    )
    max_sources: Optional[int] = (
        None  # Maximum number of sources to use for final answer
    )
    rerank_method: Optional[str] = None  # "keyword", "llm", "hybrid"
    summary_length: Optional[str] = None  # "short", "medium", "long"
    summary_quality: Optional[str] = None  # "fast", "balanced", "high"
    summary_provider: Optional[str] = None  # LLM provider for summarization
    summary_model: Optional[str] = None  # Model for summarization
    use_cache: Optional[bool] = None  # Enable/disable summary caching
    use_10_scale: Optional[bool] = True  # Use 0-10 scale for LLM-based re-ranking


class AnalysisRequestV2(BaseModel):
    """Enhanced request model for v2 API with RAG support."""

    pmid: str
    rag_config: Optional[RAGConfig] = None
    use_rag: bool = True  # Feature flag to enable/disable RAG


class BatchAnalysisRequestV2(BaseModel):
    """Enhanced batch analysis request with RAG support."""

    pmids: List[str]
    rag_config: Optional[RAGConfig] = None
    use_rag: bool = True
    max_concurrent: int = 5


class RAGStats(BaseModel):
    """RAG processing statistics."""

    chunks_processed: int
    chunks_ranked: int
    chunks_summarized: int
    avg_relevance_score: float
    max_relevance_score: float
    min_relevance_score: float
    avg_confidence: float
    rerank_method: str
    summary_length: str
    processing_time: float


class PaperAnalysisResultV2(PaperAnalysisResult):
    """Enhanced paper analysis result with RAG metadata."""

    rag_enabled: bool = False
    rag_stats: Optional[RAGStats] = None
    rag_config_used: Optional[RAGConfig] = None


class RAGConfigResponse(BaseModel):
    """RAG configuration information."""

    default_config: RAGConfig
    available_rerank_methods: List[str]
    available_summary_lengths: List[str]
    available_summary_qualities: List[str]
    available_providers: List[str]
