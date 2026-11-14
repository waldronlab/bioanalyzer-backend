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

# These are the keys used inside result["fields"]. The curator-desk CSV
# (scripts/cli_rendering.py::_render_curator_desk_csv, see
# docs/CURATOR_DESK_CSV_FORMAT.md) surfaces "host_species"/"body_site"/
# "condition"/"sequencing_type"/"sample_size" as plain value columns (plus an
# Ontology ID/Candidates pair for the first three).
FIELD_KEYS: Tuple[str, ...] = (
    "host_species",
    "body_site",
    "condition",
    "sequencing_type",
    "sample_size",
)

# STATUS_COLUMNS: the 5 fields' internal PRESENT/PARTIALLY_PRESENT/ABSENT
# status keys. No longer surfaced in the curator-desk CSV/curator_table_r/
# curator_table (which use VALUE_COLUMNS/ONTOLOGY_ID_COLUMNS instead) - still
# computed internally per field and used by the older, Status-inclusive
# `--format csv` export (see scripts/eval/confusion_matrix_analysis.py).
STATUS_COLUMNS: Tuple[str, ...] = (
    "Host Species Status",
    "Body Site Status",
    "Condition Status",
    "Sequencing Type Status",
    "Sample Size Status",
)

ESSENTIAL_FIELDS: Dict[str, str] = {
    "host_species": "What host species is being studied in this research?",
    "body_site": "What body site or anatomical location was sampled for microbiome analysis?",
    "condition": "What condition (a disease, or another factor such as an exposure, treatment, or measurement) distinguishes the groups being compared?",
    "sequencing_type": "What sequencing method or molecular technique was used?",
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
  "condition_comparison":            "<one line: '<group A> vs <group B>'>",
  "conditions":                      ["<factor the compared groups differ by, most important first>", "..."],
  "condition_raw":                   "<conditions[0], or null if the paper compares no groups>",
  "condition_evidence":              "<SECTION: one verbatim sentence (max 200 characters) from the paper that defines the compared groups>",
  "condition_confidence":            <float 0.0–1.0, see Rules>,
  "sequencing_type_raw":             "<sequencing or molecular method name only>",
  "sample_size_raw":                 <integer total participants/samples, or null if not stated>,
  "has_differential_abundance":      <true if specific microbial taxa are reported as statistically more/less abundant between groups>,
  "differential_abundance_confidence": <float 0.0–1.0 confidence in the above>
}}

Rules:
- host_species_raw   : Give the species name(s) as written. Prefer METHODS or ABSTRACT if sections are present, otherwise extract from any available text. If multiple species, join with " and ".
  If no species is named anywhere in the text, return null — do NOT default to "Homo sapiens" just because the study concerns a human disease or clinical condition.
- body_site_raw      : Give the anatomical sample site(s) as written. Prefer METHODS or ABSTRACT if sections are present, otherwise extract from any available text. If multiple sites, join with " and ".
  If no sample site is stated, return null — do NOT guess a typical site (e.g. "gut") just because the paper is about microbiome research.
- condition_comparison / conditions / condition_raw / condition_evidence / condition_confidence:
  BugSigDB records the CONDITION that distinguishes the groups whose microbiomes are compared (cases vs
  controls, exposed vs unexposed, before vs after, responders vs non-responders) - an experimental factor
  in the style of the EFO ontology.
  Take this field from ABSTRACT and METHODS (study population, inclusion criteria, group definitions).
  Do NOT take it from INTRODUCTION or DISCUSSION: they name background diseases the study is not about.
  If the text has no section labels, use the sentences that say who or what was sampled and how the
  groups were formed.
  Step 1 - "condition_comparison": state the main comparison in one line as "<group A> vs <group B>",
    e.g. "celiac disease patients vs healthy controls",
         "melanoma patients responding vs not responding to anti-PD-1 therapy",
         "mice on standard chow vs chow plus metformin".
  Step 2 - "conditions": list every factor the compared groups differ by, most important first.
    * A disease/disorder that a compared group has: give the standard disease entity, as a disease
      ontology would name it. Drop severity, stage, subtype, treatment-resistance and activity qualifiers:
      "refractory celiac disease" -> "celiac disease", "stage IV melanoma" -> "melanoma",
      "drug-resistant epilepsy" -> "epilepsy", "early-onset preeclampsia" -> "preeclampsia".
      Keep names that are distinct disease entities rather than qualified versions of one:
      "primary sclerosing cholangitis" and "primary biliary cholangitis" stay as they are (not
      "cholangitis"); "systemic lupus erythematosus" stays (not "lupus"). Never broaden a named
      disease to its parent category.
    * A non-disease factor the groups differ by, as ONE short EFO-style term (1-4 words, never a list
      joined by "and" or commas): an exposure or treatment ("metformin", "probiotic", "exercise",
      "vitamin D"), a measurement ("blood pressure measurement"), a design factor ("season",
      "geographic location"), or a response to an intervention ("response to probiotic").
    * When EVERY participant has the same disease and the groups differ by treatment, response or
      outcome (responders vs non-responders, before vs after a drug, relapse vs remission), list that
      distinguishing factor FIRST (e.g. "response to anti-PD-1 therapy") and the shared disease second.
    * Animal models: give the modelled disease if one is induced (e.g. "pulmonary fibrosis") AND the
      inducing exposure (e.g. "bleomycin"); for models defined only by a feed or a drug, give that exposure.
    * Healthy-only cohorts: give the non-disease factor(s) the groups differ by.
    Never return "healthy", "control", "controls" or "patients" as a condition: when a disease group is
    compared with healthy controls, the condition is the disease, even though the word "healthy"
    appears in the text. Do NOT include phrases like "patients with" or "diagnosed with" - give the
    condition name only.
  Step 3 - "condition_raw" = conditions[0]. Return null for condition_raw (and [] for conditions) ONLY
    if the paper compares no groups at all - do NOT invent a condition; then "condition_evidence" is the
    sentence showing the study is purely descriptive.
  "condition_evidence": ONE sentence copied verbatim from the paper (max 200 characters, do not
    paraphrase) that defines the compared groups, prefixed with its section, e.g.
    "METHODS: We enrolled 40 patients with celiac disease and 38 healthy controls."
    Use null if no such sentence exists.
  "condition_confidence": 1.0 = groups explicitly defined in METHODS or ABSTRACT;
    0.7 = inferred from RESULTS; 0.4 = ambiguous (several comparisons, none clearly primary);
    0.2 = guessed.
- sequencing_type_raw: Give the sequencing or molecular method name only. Prefer METHODS if sections are present, otherwise extract from any available text. Give the method name exactly as written
  (e.g. "16S rRNA gene sequencing of the V4 region", "shotgun metagenomic sequencing", "ITS2 amplicon sequencing", "qPCR").
  BugSigDB records one of: 16S (16S rRNA amplicon), 18S (18S rRNA amplicon), WMS (whole-metagenome shotgun),
  ITS / ITS2 (fungal ITS amplicon), PCR (targeted qPCR/PCR of specific taxa) — so always include the marker gene or
  approach that tells these apart. If the text only says "amplicon sequencing" or "high-throughput sequencing", look in
  METHODS for the target gene (16S, 18S, ITS) and include it. If several methods were used (e.g. 16S and shotgun), give
  all of them joined with " and ". If no sequencing/molecular method is stated, return null.
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
