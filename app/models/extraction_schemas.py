"""
Extraction Schemas for BioAnalyzer
===================================
Pydantic models for structured data extraction from scientific studies.
Compatible with BugSigDB schema requirements AND the curator desk display
columns produced by bugsigdb_analyzer.py.

Field alignment contract
------------------------
bugsigdb_analyzer.py emits a result dict whose `fields` key holds exactly:

    {
        "host_species":     FieldResult,
        "body_site":        FieldResult,
        "condition":        FieldResult,
        "sequencing_type":  FieldResult,
        "sample_size":      FieldResult,
        "taxa_level":       FieldResult,   # present in API; hidden in curator table
    }

data.R / normalize_dataset() flattens those into the curator table columns:

    Host Species          <- fields.host_species.value
    Host Species Status   <- fields.host_species.status
    Body Site             <- fields.body_site.value
    Body Site Status      <- fields.body_site.status
    Condition             <- fields.condition.value
    Condition Status      <- fields.condition.status
    Sequencing Type       <- fields.sequencing_type.value
    Sequencing Type Status <- fields.sequencing_type.status
    Sample Size           <- fields.sample_size.value
    Sample Size Status    <- fields.sample_size.status
    has_differential_abundance
    differential_abundance_confidence
    in_bugsigdb
    Priority

Every model here mirrors that contract so that the agent orchestrator and
the simple analyzer produce structurally identical outputs.
"""

from datetime import datetime
from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# FieldResult — mirrors _build_field_result() in bugsigdb_analyzer.py
# ---------------------------------------------------------------------------

FieldStatus = Literal["PRESENT", "PARTIALLY_PRESENT", "ABSENT"]


class FieldResult(BaseModel):
    """
    Structured result for a single extracted field.

    Mirrors the dict produced by bugsigdb_analyzer._build_field_result() so
    that agent_orchestrator.py and the simple analyzer share an identical
    output shape that data.R can flatten without special-casing.
    """

    value: str = Field(
        default="",
        description="Extracted and normalised value; empty string when status is ABSENT.",
    )
    status: FieldStatus = Field(
        default="ABSENT",
        description="PRESENT | PARTIALLY_PRESENT | ABSENT",
    )
    confidence: float = Field(
        default=0.0,
        ge=0.0,
        le=1.0,
        description="Extraction confidence (0–1).",
    )
    ontology_id: str = Field(
        default="",
        description="Ontology identifier (e.g. NCBITaxon:9606, UBERON:0001155).",
    )
    mapping_confidence: float = Field(
        default=0.0,
        ge=0.0,
        le=1.0,
        description="Confidence that the raw value was correctly mapped to the ontology term.",
    )
    reason_if_missing: str = Field(
        default="",
        description="Human-readable explanation when status is ABSENT.",
    )
    raw: str = Field(
        default="",
        description="Pre-normalization text; populated only by normalizers "
        "that preserve it (e.g. sequencing_type's 'other' fallback).",
    )
    mapping_tier: str = Field(
        default="none",
        description="Ontology-mapping confidence tier: 'auto' (static "
        "lookup match, applied without review), 'review' (live OLS/NCBI "
        "fallback or ambiguous match, curator should confirm), or 'none' "
        "(no ontology_id). See app.normalization.grounding.tier_for().",
    )
    mapping_candidates: List[Dict[str, str]] = Field(
        default_factory=list,
        description="Up to 2 alternative {label, ontology_id} candidates "
        "for curator review; populated only when mapping_tier != 'auto'.",
    )

    @classmethod
    def absent(
        cls, reason: str = "Information not found in the paper"
    ) -> "FieldResult":
        """Convenience constructor for an ABSENT field."""
        return cls(
            value="",
            status="ABSENT",
            confidence=0.0,
            ontology_id="",
            mapping_confidence=0.0,
            reason_if_missing=reason,
        )

    def to_legacy_dict(self) -> Dict[str, Any]:
        """
        Return a plain dict that is byte-for-byte compatible with the dicts
        produced by bugsigdb_analyzer._build_field_result().  Use this when
        you need to merge orchestrator output back into the simple-analyzer
        result shape.
        """
        return {
            "value": self.value,
            "status": self.status,
            "confidence": self.confidence,
            "ontology_id": self.ontology_id,
            "mapping_confidence": self.mapping_confidence,
            "reason_if_missing": self.reason_if_missing,
            "raw": self.raw,
            "mapping_tier": self.mapping_tier,
            "mapping_candidates": self.mapping_candidates,
        }


# ---------------------------------------------------------------------------
# ExperimentFields — the six BugSigDB fields, each wrapped in FieldResult
# ---------------------------------------------------------------------------


class ExperimentFields(BaseModel):
    """
    The six BugSigDB extraction fields as FieldResult objects.

    Matches the keys inside bugsigdb_analyzer result["fields"] exactly.
    taxa_level is included here even though the curator table hides it,
    because the API contract requires it.
    """

    host_species: FieldResult = Field(
        default_factory=FieldResult.absent,
        description="Host organism (e.g. Homo sapiens, Mus musculus).",
    )
    body_site: FieldResult = Field(
        default_factory=FieldResult.absent,
        description="Anatomical sample site (e.g. gut, oral cavity, skin).",
    )
    condition: FieldResult = Field(
        default_factory=FieldResult.absent,
        description="Disease, treatment, or condition studied.",
    )
    sequencing_type: FieldResult = Field(
        default_factory=FieldResult.absent,
        description="Sequencing or molecular method (e.g. 16S rRNA gene sequencing).",
    )
    sample_size: FieldResult = Field(
        default_factory=FieldResult.absent,
        description="Total number of samples or participants as a string integer.",
    )
    taxa_level: FieldResult = Field(
        default_factory=FieldResult.absent,
        description="Taxonomic level analysed (e.g. genus, species, phylum).",
    )

    def to_legacy_dict(self) -> Dict[str, Dict[str, Any]]:
        """
        Return the nested dict that bugsigdb_analyzer stores under result['fields'].
        Use when merging orchestrator results with the simple-analyzer output shape.
        """
        return {
            "host_species": self.host_species.to_legacy_dict(),
            "body_site": self.body_site.to_legacy_dict(),
            "condition": self.condition.to_legacy_dict(),
            "sequencing_type": self.sequencing_type.to_legacy_dict(),
            "sample_size": self.sample_size.to_legacy_dict(),
            "taxa_level": self.taxa_level.to_legacy_dict(),
        }


# ---------------------------------------------------------------------------
# ExperimentMetadata — lightweight human-readable summary (kept for compat)
# ---------------------------------------------------------------------------


class ExperimentMetadata(BaseModel):
    """
    Plain-string metadata snapshot derived from ExperimentFields.
    Kept for backward compatibility with code that reads .metadata.host_species
    etc. directly.  For new code, prefer ExperimentFields (which carries status
    and ontology information).
    """

    host_species: Optional[str] = Field(None, description="Host organism string value.")
    body_site: Optional[str] = Field(None, description="Body site string value.")
    condition: Optional[str] = Field(None, description="Condition string value.")
    sequencing_type: Optional[str] = Field(
        None, description="Sequencing method string value."
    )
    taxa_level: Optional[str] = Field(None, description="Taxonomic level string value.")
    sample_size: Optional[int] = Field(None, description="Sample count.")

    @classmethod
    def from_fields(cls, fields: ExperimentFields) -> "ExperimentMetadata":
        """Build a metadata snapshot from a fully-resolved ExperimentFields."""

        def _val(f: FieldResult) -> Optional[str]:
            return f.value if f.status != "ABSENT" and f.value else None

        size_str = _val(fields.sample_size)
        size_int: Optional[int] = None
        if size_str:
            try:
                size_int = int(size_str)
            except ValueError:
                pass

        return cls(
            host_species=_val(fields.host_species),
            body_site=_val(fields.body_site),
            condition=_val(fields.condition),
            sequencing_type=_val(fields.sequencing_type),
            taxa_level=_val(fields.taxa_level),
            sample_size=size_int,
        )


# ---------------------------------------------------------------------------
# MicrobialSignature
# ---------------------------------------------------------------------------


class MicrobialSignature(BaseModel):
    """A microbial signature extracted from the study."""

    taxon_name: str = Field(description="Name of the microbial taxon.")
    abundance_change: str = Field(
        description="Direction of change: increased | decreased | unchanged."
    )
    statistical_significance: Optional[str] = Field(
        None, description="P-value or statistical test result."
    )
    comparison_group: Optional[str] = Field(
        None, description="Groups compared (e.g. 'disease vs. healthy')."
    )
    evidence_text: str = Field(description="Text excerpt supporting this signature.")
    confidence: float = Field(
        default=0.7,
        ge=0.0,
        le=1.0,
        description="Confidence score for this extraction.",
    )


# ---------------------------------------------------------------------------
# ExtractedExperiment
# ---------------------------------------------------------------------------


class ExtractedExperiment(BaseModel):
    """
    Complete experiment extraction.

    Carries both the rich ExperimentFields (with status / ontology data) and
    the legacy ExperimentMetadata snapshot so older call-sites keep working.
    """

    experiment_id: str = Field(description="Unique identifier for this experiment.")
    title: str = Field(description="Title or description of the experiment.")

    # Rich structured fields — use these in all new code
    fields: ExperimentFields = Field(
        default_factory=ExperimentFields,
        description="BugSigDB field extractions with status and ontology data.",
    )

    # Legacy plain-string snapshot — kept for backward compat
    metadata: ExperimentMetadata = Field(
        default_factory=ExperimentMetadata,
        description="Plain-string metadata snapshot (derived from fields).",
    )

    # Differential abundance — mirrors bugsigdb_analyzer top-level keys
    has_differential_abundance: bool = Field(
        default=False,
        description="True when specific taxa are reported as differentially abundant.",
    )
    differential_abundance_confidence: float = Field(
        default=0.0,
        ge=0.0,
        le=1.0,
        description="Confidence in the differential abundance assessment.",
    )

    signatures: List[MicrobialSignature] = Field(
        default_factory=list, description="Microbial signatures found."
    )
    methods_summary: Optional[str] = Field(
        None, description="Summary of experimental methods."
    )
    results_summary: Optional[str] = Field(None, description="Summary of key results.")
    evidence_chunks: List[str] = Field(
        default_factory=list, description="Text chunks used as evidence."
    )
    extraction_timestamp: datetime = Field(
        default_factory=datetime.now,
        description="When this extraction was performed.",
    )

    def sync_metadata(self) -> None:
        """Re-derive metadata from fields (call after fields are populated)."""
        self.metadata = ExperimentMetadata.from_fields(self.fields)

    def apply_signature_da_flags(self, signatures: List["MicrobialSignature"]) -> None:
        """Set differential-abundance flags from extracted microbial signatures."""
        if not signatures:
            return
        self.has_differential_abundance = True
        confidences = [float(s.confidence or 0.0) for s in signatures]
        has_stats = any(s.statistical_significance for s in signatures)
        base_conf = max(confidences) if confidences else 0.6
        self.differential_abundance_confidence = (
            min(1.0, base_conf + 0.15) if has_stats else base_conf
        )


# ---------------------------------------------------------------------------
# StudyAnalysisResult
# ---------------------------------------------------------------------------


class StudyAnalysisResult(BaseModel):
    """
    Complete analysis result for a study.

    Top-level keys mirror bugsigdb_analyzer.analyze_paper_simple() output so
    the same data.R / normalize_dataset() pipeline can consume either source.

    Key alignment:
        pmid                          <- bugsigdb_analyzer result["pmid"]
        title                         <- result["title"]
        authors                       <- result["authors"]
        journal                       <- result["journal"]
        publication_date              <- result["publication_date"]
        year                          <- result["year"]
        has_differential_abundance    <- result["has_differential_abundance"]
        differential_abundance_confidence <- result["differential_abundance_confidence"]
        in_bugsigdb                   <- result["in_bugsigdb"]
        fields                        <- result["fields"]  (via experiments[0].fields)
        analysis_timestamp            <- result["analysis_timestamp"]
        model_used                    <- result["model_used"]
    """

    # --- Identity (mirrors bugsigdb_analyzer result dict) ---
    pmid: str = Field(description="PubMed ID of the study.")
    study_id: str = Field(description="Internal unique identifier (may equal pmid).")
    source_url: str = Field(description="Original URL of the study.")

    # --- Bibliographic (mirrors bugsigdb_analyzer result dict) ---
    title: str = Field(default="", description="Paper title.")
    authors: List[str] = Field(default_factory=list, description="Author list.")
    journal: str = Field(default="", description="Journal name.")
    publication_date: str = Field(default="", description="Publication date string.")
    year: Optional[int] = Field(None, description="Publication year as integer.")

    # --- Differential abundance (mirrors bugsigdb_analyzer result dict) ---
    has_differential_abundance: bool = Field(
        default=False,
        description="True when specific taxa are reported as differentially abundant.",
    )
    differential_abundance_confidence: float = Field(
        default=0.0,
        ge=0.0,
        le=1.0,
        description="Confidence in the differential abundance assessment.",
    )

    # --- BugSigDB check (mirrors bugsigdb_analyzer result dict) ---
    in_bugsigdb: bool = Field(
        default=False,
        description="True when this PMID is already present in BugSigDB.",
    )

    # --- Experiments extracted by the agent ---
    experiments: List[ExtractedExperiment] = Field(
        default_factory=list, description="Extracted experiments."
    )

    # --- Aggregated quality indicators ---
    total_signatures: int = Field(
        default=0, description="Total number of microbial signatures extracted."
    )
    curation_ready: bool = Field(
        default=False,
        description="True when the study is ready for BugSigDB curation.",
    )
    missing_fields: List[str] = Field(
        default_factory=list, description="Required fields that are missing."
    )
    confidence_score: float = Field(
        default=0.0,
        ge=0.0,
        le=1.0,
        description="Overall confidence in the extraction.",
    )

    # --- Provenance (mirrors bugsigdb_analyzer result dict) ---
    analysis_timestamp: datetime = Field(
        default_factory=datetime.now,
        description="When this analysis was performed.",
    )
    model_used: str = Field(
        default="",
        description="LLM model identifier used for extraction.",
    )

    def to_analyzer_result(self) -> Dict[str, Any]:
        """
        Serialise to the flat dict shape produced by
        bugsigdb_analyzer.analyze_paper_simple().

        This allows the orchestrator result to be stored in the cache and
        consumed by data.R / normalize_dataset() without any adaptation layer.

        When multiple experiments exist, the first experiment's fields are
        used as the primary fields dict (consistent with how the simple
        analyzer handles single-experiment papers).
        """
        primary_fields: Dict[str, Dict[str, Any]]
        if self.experiments:
            primary_fields = self.experiments[0].fields.to_legacy_dict()
        else:
            primary_fields = ExperimentFields().to_legacy_dict()

        return {
            "pmid": self.pmid,
            "title": self.title,
            "authors": self.authors,
            "journal": self.journal,
            "publication_date": self.publication_date,
            "year": self.year if self.year is not None else "",
            "has_differential_abundance": self.has_differential_abundance,
            "differential_abundance_confidence": self.differential_abundance_confidence,
            "in_bugsigdb": self.in_bugsigdb,
            "fields": primary_fields,
            "analysis_timestamp": self.analysis_timestamp.isoformat(),
            "model_used": self.model_used,
        }


# ---------------------------------------------------------------------------
# ExtractionQuery
# ---------------------------------------------------------------------------


class ExtractionQuery(BaseModel):
    """Query for a single-field extraction pass."""

    query_type: str = Field(
        description="Type of query: experiment | signature | metadata."
    )
    query_text: str = Field(description="The actual query string sent to the LLM.")
    context_chunks: List[str] = Field(
        default_factory=list, description="Relevant context chunks."
    )
