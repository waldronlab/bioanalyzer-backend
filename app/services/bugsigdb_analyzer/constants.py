"""
Canonical field keys, status columns, essential-field questions, and the
unified extraction prompt used by the BugSigDB analyzer.
"""

from datetime import datetime
from typing import Dict, Tuple

import pytz

# ---------------------------------------------------------------------------
# Timestamp helper (local — avoids circular import with app.api.utils)
# ---------------------------------------------------------------------------


def _current_timestamp() -> str:
    """Return the current UTC time as an ISO-8601 string."""
    return datetime.now(pytz.UTC).isoformat()


# ---------------------------------------------------------------------------
# Canonical field keys — single source of truth
# ---------------------------------------------------------------------------

# These are the keys used inside result["fields"].
# data.R / normalize_dataset() maps them to display columns as follows:
#   snake_case key           → Title Case display name    / Title Case Status col
#   "host_species"           → "Host Species"             / "Host Species Status"
#   "body_site"              → "Body Site"                / "Body Site Status"
#   "condition"              → "Condition"                / "Condition Status"
#   "sequencing_type"        → "Sequencing Type"          / "Sequencing Type Status"
#   "sample_size"            → "Sample Size"              / "Sample Size Status"
#   "taxa_level"             → hidden in curator table, present in API response
FIELD_KEYS: Tuple[str, ...] = (
    "host_species",
    "body_site",
    "condition",
    "sequencing_type",
    "sample_size",
    "taxa_level",
)

# STATUS_COLUMNS (as used inside the R layer for colour-coding / filtering)
# Kept here for reference; the R layer defines its own equivalent.
STATUS_COLUMNS: Tuple[str, ...] = (
    "Host Species Status",
    "Body Site Status",
    "Condition Status",
    "Sequencing Type Status",
    "Sample Size Status",
    "Taxa Level Status",
)

ESSENTIAL_FIELDS: Dict[str, str] = {
    "host_species": "What host species is being studied in this research?",
    "body_site": "What body site or anatomical location was sampled for microbiome analysis?",
    "condition": "What disease, treatment, or condition is being studied?",
    "sequencing_type": "What sequencing method or molecular technique was used?",
    "taxa_level": "What taxonomic level was analysed (e.g. genus, species, OTU)?",
    "sample_size": "How many samples or participants were included in the study?",
}


# ---------------------------------------------------------------------------
# Extraction prompt
# ---------------------------------------------------------------------------

EXTRACTION_PROMPT = """\
You are a biomedical literature analyst specialising in microbiome research curation.

Analyse the following biomedical paper content and extract structured metadata.
The content may include labelled sections (ABSTRACT, METHODS, RESULTS, DISCUSSION, etc.).
When a section is present, prefer its information over unlabelled text for the
corresponding fields as described in the Rules below.

Return ONLY a valid JSON object. No markdown fences, no explanation, no extra text.

--- PAPER CONTENT BEGIN ---
Title:   {title}
Journal: {journal}
Year:    {year}

{paper_content}
--- PAPER CONTENT END ---

Extract the following fields and return as a single JSON object:

{{
  "host_species_raw":                "<species as written in the paper, e.g. 'Homo sapiens' or 'mice and rats'>",
  "body_site_raw":                   "<anatomical sample site(s) as written, e.g. 'faeces' or 'gut and oral cavity'>",
  "condition_raw":                   "<disease or condition name only, stripped of clinical preamble>",
  "sequencing_type_raw":             "<sequencing or molecular method name only>",
  "taxa_level_raw":                  "<taxonomic rank analysed, e.g. 'genus', 'species', 'OTU', 'ASV', or null if not stated>",
  "sample_size_raw":                 <integer total participants/samples, or null if not stated>,
  "has_differential_abundance":      <true if specific microbial taxa are reported as statistically more/less abundant between groups>,
  "differential_abundance_confidence": <float 0.0–1.0 confidence in the above>
}}

Rules:
- host_species_raw   : Give the species name(s) as written. Prefer METHODS or ABSTRACT if sections are present, otherwise extract from any available text. If multiple species, join with " and ".
- body_site_raw      : Give the anatomical sample site(s) as written. Prefer METHODS or ABSTRACT if sections are present, otherwise extract from any available text. If multiple sites, join with " and ".
- condition_raw      : Give the disease/condition name only. Prefer ABSTRACT or INTRODUCTION if sections are present, otherwise extract from any available text.
  Do NOT include phrases like "patients with" or "diagnosed with".
  If the study compares diseased vs. healthy controls, give the disease name only.
- sequencing_type_raw: Give the sequencing or molecular method name only. Prefer METHODS if sections are present, otherwise extract from any available text. Give the method name exactly as written
  (e.g. "16S rRNA gene sequencing", "shotgun metagenomics", "whole-genome sequencing").
- taxa_level_raw     : Give the taxonomic rank analysed (e.g. genus, species, phylum, OTU, ASV). Prefer METHODS or RESULTS if sections are present.
  If multiple ranks are reported, give the finest rank stated. If not stated, return null.
- sample_size_raw    : Give ONLY an integer. Prefer METHODS if sections are present, otherwise extract from any available text. Convert word-numbers
  (e.g. "forty-two" → 42). If a range or multiple cohorts, give the total or largest number.
  If completely absent from the paper, return null.
- has_differential_abundance: true ONLY when RESULTS or ABSTRACT explicitly states that
  specific microbial taxa or features differ statistically between groups (p-value, FDR,
  fold-change, or equivalent reported), or if this is clearly stated in the available text. Do NOT infer from study design alone.
- differential_abundance_confidence:
    1.0 = explicitly stated with statistics in RESULTS
    0.8 = clearly stated in ABSTRACT with statistical language
    0.6 = strongly implied (e.g. "significant differences in microbiota")
    0.4 = ambiguous
    0.2 = unlikely
    0.0 = clearly absent or not a differential abundance study
"""
