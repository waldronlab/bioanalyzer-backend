"""
Pydantic models for API requests and responses.
"""
from pydantic import BaseModel
from typing import Dict, List, Optional, Any


class Message(BaseModel):
    """WebSocket message model."""
    content: str
    role: str = "user"


class Question(BaseModel):
    """Question model for paper analysis."""
    question: str


class AnalysisRequest(BaseModel):
    """Request model for paper analysis."""
    pmid: str


class BatchAnalysisRequest(BaseModel):
    """Request model for batch analysis."""
    pmids: List[str]
    page: int = 1
    page_size: int = 20


class EnhancedBatchAnalysisRequest(BaseModel):
    """Request model for enhanced batch analysis."""
    pmids: List[str]
    max_concurrent: int = 5


class CacheSearchRequest(BaseModel):
    """Request model for cache search."""
    query: str
    search_type: str = "all"


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


class CacheStatsResponse(BaseModel):
    """Cache statistics response model."""
    total_entries: int
    analysis_cache_entries: int
    metadata_cache_entries: int
    fulltext_cache_entries: int
    cache_size_mb: float
    oldest_entry: Optional[str]
    newest_entry: Optional[str]


class FieldAnalysis(BaseModel):
    """Individual field analysis result."""
    status: str  # PRESENT, PARTIALLY_PRESENT, ABSENT
    value: Optional[str]
    confidence: float
    reason_if_missing: Optional[str]
    suggestions: Optional[str]


class PaperAnalysisResult(BaseModel):
    """Complete paper analysis result."""
    pmid: str
    title: Optional[str]
    authors: Optional[List[str]]
    journal: Optional[str]
    publication_date: Optional[str]
    fields: Dict[str, FieldAnalysis]
    curation_summary: str
    analysis_timestamp: str
    processing_time: float
    model_used: str


# RAG-specific models for v2 API
class RAGConfig(BaseModel):
    """RAG configuration for analysis."""
    enabled: bool = True
    top_k_chunks: Optional[int] = None  # Number of top chunks to use
    evidence_k: Optional[int] = None  # Number of evidence chunks to retrieve before re-ranking
    max_sources: Optional[int] = None  # Maximum number of sources to use for final answer
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
