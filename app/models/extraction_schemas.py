"""
Extraction Schemas for BioAnalyzer

Pydantic models for structured data extraction from scientific studies.
Compatible with BugSigDB schema requirements.
"""

from datetime import datetime
from typing import Optional, List
from pydantic import BaseModel, Field


class ExperimentMetadata(BaseModel):
    """Metadata about an experiment."""

    host_species: Optional[str] = Field(
        None, description="Host organism (e.g., Human, Mouse, Rat)"
    )
    body_site: Optional[str] = Field(
        None, description="Body site sampled (e.g., Gut, Oral, Skin)"
    )
    condition: Optional[str] = Field(
        None, description="Disease, treatment, or condition studied"
    )
    sequencing_type: Optional[str] = Field(
        None, description="Sequencing method (e.g., 16S, metagenomics)"
    )
    taxa_level: Optional[str] = Field(
        None, description="Taxonomic level analyzed (e.g., phylum, genus, species)"
    )
    sample_size: Optional[int] = Field(
        None, description="Number of samples or participants"
    )


class MicrobialSignature(BaseModel):
    """A microbial signature extracted from the study."""

    taxon_name: str = Field(description="Name of the microbial taxon")
    abundance_change: str = Field(
        description="Direction of change (increased/decreased/unchanged)"
    )
    statistical_significance: Optional[str] = Field(
        None, description="P-value or statistical test result"
    )
    comparison_group: Optional[str] = Field(
        None, description="What groups were compared"
    )
    evidence_text: str = Field(description="Text excerpt supporting this signature")
    confidence: float = Field(
        default=0.0, ge=0.0, le=1.0, description="Confidence score for this extraction"
    )


class ExtractedExperiment(BaseModel):
    """Complete experiment extraction."""

    experiment_id: str = Field(description="Unique identifier for this experiment")
    title: str = Field(description="Title or description of the experiment")
    metadata: ExperimentMetadata = Field(
        description="Experiment metadata (BugSigDB fields)"
    )
    signatures: List[MicrobialSignature] = Field(
        default_factory=list, description="Microbial signatures found"
    )
    methods_summary: Optional[str] = Field(
        None, description="Summary of experimental methods"
    )
    results_summary: Optional[str] = Field(None, description="Summary of key results")
    evidence_chunks: List[str] = Field(
        default_factory=list, description="Text chunks used as evidence"
    )
    extraction_timestamp: datetime = Field(
        default_factory=datetime.now, description="When this extraction was performed"
    )


class StudyAnalysisResult(BaseModel):
    """Complete analysis result for a study."""

    study_id: str = Field(description="Unique identifier for the study")
    source_url: str = Field(description="Original URL of the study")
    experiments: List[ExtractedExperiment] = Field(
        default_factory=list, description="Extracted experiments"
    )
    total_signatures: int = Field(
        default=0, description="Total number of signatures extracted"
    )
    curation_ready: bool = Field(
        default=False, description="Whether the study is ready for BugSigDB curation"
    )
    missing_fields: List[str] = Field(
        default_factory=list, description="Required fields that are missing"
    )
    confidence_score: float = Field(
        default=0.0, ge=0.0, le=1.0, description="Overall confidence in the extraction"
    )
    analysis_timestamp: datetime = Field(
        default_factory=datetime.now, description="When this analysis was performed"
    )


class ExtractionQuery(BaseModel):
    """Query for extraction."""

    query_type: str = Field(description="Type of query (experiment/signature/metadata)")
    query_text: str = Field(description="The actual query")
    context_chunks: List[str] = Field(
        default_factory=list, description="Relevant context chunks"
    )
