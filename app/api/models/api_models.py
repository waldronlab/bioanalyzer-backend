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
