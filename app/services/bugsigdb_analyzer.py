import logging
import re
import json
import asyncio
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

import pytz
from defusedxml import ElementTree
from xml.etree.ElementTree import Element as ETElement

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

# REMOVED: from app.api.utils.api_utils import get_current_timestamp
# Reason: caused a circular import chain:
#   bugsigdb_analyzer -> app.api.utils.api_utils
#   -> app.api.__init__ -> app.api.app -> app.api.routers.bugsigdb_analysis
#   -> bugsigdb_analyzer  (already being initialized)
# The function below (_current_timestamp) is the local equivalent and is used
# throughout this file — the api_utils import was dead code.

logger = logging.getLogger(__name__)


def _current_timestamp() -> str:
    """Get current timestamp in ISO format using UTC."""
    return datetime.now(pytz.UTC).isoformat()


# ---------------------------------------------------------------------------
# Singleton service instances
# ---------------------------------------------------------------------------

_unified_qa: Optional[UnifiedQA] = None
_pubmed_retriever: Optional[PubMedRetriever] = None
_cache_manager: Optional[CacheManager] = None


def get_unified_qa() -> Optional[UnifiedQA]:
    global _unified_qa
    if _unified_qa is None:
        try:
            # For structured field extraction, force direct model chat mode.
            # PaperQA agent mode is powerful for retrieval QA but can introduce
            # long tool runs/timeouts and non-JSON outputs for this endpoint.
            _unified_qa = UnifiedQA(
                provider="gemini",
                model=DEFAULT_MODEL,
                gemini_api_key=GEMINI_API_KEY,
                use_paperqa=False,
            )
            logger.info("UnifiedQA initialised successfully")
        except Exception as e:
            logger.error(f"UnifiedQA init failed: {e}")
            try:
                from app.models.gemini_qa import GeminiQA

                _unified_qa = GeminiQA(api_key=GEMINI_API_KEY)
                logger.info("Fallback to GeminiQA successful")
            except Exception as e2:
                logger.error(f"GeminiQA fallback also failed: {e2}")
    return _unified_qa


def get_pubmed_retriever() -> Optional[PubMedRetriever]:
    global _pubmed_retriever
    if _pubmed_retriever is None:
        try:
            _pubmed_retriever = PubMedRetriever(api_key=NCBI_API_KEY)
        except Exception as e:
            logger.error(f"PubMedRetriever init failed: {e}")
    return _pubmed_retriever


def get_cache_manager() -> CacheManager:
    global _cache_manager
    if _cache_manager is None:
        _cache_manager = CacheManager()
    return _cache_manager


# ---------------------------------------------------------------------------
# Field definitions (unchanged – kept for reference)
# ---------------------------------------------------------------------------

ESSENTIAL_FIELDS: Dict[str, str] = {
    "host_species": "What host species is being studied in this research?",
    "body_site": "What body site or anatomical location was sampled for microbiome analysis?",
    "condition": "What disease, treatment, or condition is being studied?",
    "sequencing_type": "What sequencing method or molecular technique was used?",
    "sample_size": "How many samples or participants were included in the study?",
}

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


# ---------------------------------------------------------------------------
# PMC XML section parser
# ---------------------------------------------------------------------------

_SECTION_PATTERNS: List[Tuple[str, re.Pattern]] = [
    ("ABSTRACT", re.compile(r"abstract", re.I)),
    ("INTRODUCTION", re.compile(r"intro(?:duction)?|background", re.I)),
    ("METHODS", re.compile(r"method|material|patient|protocol|statistical", re.I)),
    ("RESULTS", re.compile(r"result|finding", re.I)),
    ("DISCUSSION", re.compile(r"discussion|conclusion|summary", re.I)),
    ("SUPPLEMENTARY", re.compile(r"supplement|appendix", re.I)),
]


def _classify_section_title(title: str) -> str:
    """Map a raw section title to one of our canonical section names."""
    if not title:
        return "OTHER"

    title_upper = title.strip().upper()

    for canonical, pattern in _SECTION_PATTERNS:
        if pattern.search(title_upper):  # Search in uppercase
            return canonical
    return "OTHER"


def _parse_pmc_sections(xml_text: str) -> Dict[str, str]:
    """Parse PMC full-text XML into a dict of {canonical_section: joined_text}."""
    if not xml_text or not xml_text.strip():
        return {}

    if not xml_text.lstrip().startswith("<"):
        return {"FULL_TEXT": xml_text}

    try:
        root = ElementTree.fromstring(xml_text)
    except ElementTree.ParseError:
        start = xml_text.find("<")
        if start > 0:
            try:
                root = ElementTree.fromstring(xml_text[start:])
            except ElementTree.ParseError:
                return {"FULL_TEXT": xml_text}
        else:
            return {"FULL_TEXT": xml_text}

    sections: Dict[str, List[str]] = {}

    def _walk(node: ETElement, inherited_label: str = "OTHER") -> None:
        tag = node.tag.split("}")[-1] if "}" in node.tag else node.tag

        if tag == "sec":
            # === IMPROVED TITLE EXTRACTION ===
            raw_title = ""
            ns_prefix = ""
            if "}" in node.tag:
                ns_prefix = node.tag.split("}")[0] + "}"
            title_el = node.find(f".//{ns_prefix}title") or node.find(
                f"{ns_prefix}title"
            )

            if title_el is not None:
                # Try multiple ways to get title text
                if title_el.text:
                    raw_title = title_el.text.strip()
                else:
                    raw_title = "".join(title_el.itertext()).strip()

            label = _classify_section_title(raw_title) if raw_title else inherited_label

            # Collect paragraph text
            para_texts: List[str] = []
            for child in node:
                child_tag = child.tag.split("}")[-1] if "}" in child.tag else child.tag
                if child_tag == "p":
                    text = "".join(child.itertext()).strip()
                    if text:
                        para_texts.append(text)
                elif child_tag not in ("sec", "title"):
                    inline = "".join(child.itertext()).strip()
                    if inline:
                        para_texts.append(inline)

            if para_texts:
                sections.setdefault(label, []).extend(para_texts)

            # Recurse into nested sections
            for child in node:
                child_tag = child.tag.split("}")[-1] if "}" in child.tag else child.tag
                if child_tag == "sec":
                    _walk(child, label)

        else:
            for child in node:
                _walk(child, inherited_label)

    _walk(root)

    return {k: "\n\n".join(v) for k, v in sections.items() if v}


# ---------------------------------------------------------------------------
# Text preparation
# ---------------------------------------------------------------------------

_CONTEXT_CHAR_LIMIT = 8_000

_SECTION_BUDGETS: Dict[str, int] = {
    "ABSTRACT": 1_200,
    "METHODS": 3_000,
    "RESULTS": 2_000,
    "INTRODUCTION": 800,
    "DISCUSSION": 600,
    "OTHER": 400,
}


def _truncate(text: str, max_chars: int) -> str:
    """Truncate text to max_chars, breaking at a sentence boundary when possible."""
    if len(text) <= max_chars:
        return text
    suffix = " [truncated]"
    if max_chars <= len(suffix):
        return text[:max_chars]
    limit = max_chars - len(suffix)
    cut = text[:limit]
    last_period = cut.rfind(".")
    if last_period > limit * 0.7:
        cut = cut[: last_period + 1]
    return cut + suffix


def prepare_analysis_context(
    abstract: str,
    full_text: str,
    *,
    char_limit: int = _CONTEXT_CHAR_LIMIT,
) -> str:
    """Build analysis context with strict character limit."""
    abstract = (abstract or "").strip()
    full_text = (full_text or "").strip()

    if not full_text:
        if not abstract:
            return ""
        return f"ABSTRACT:\n{_truncate(abstract, char_limit)}"

    sections = _parse_pmc_sections(full_text)
    if not sections:
        sections = {"FULL_TEXT": full_text}

    # Always prefer the provided abstract in tests
    if abstract:
        sections["ABSTRACT"] = abstract

    ordered_keys = ["ABSTRACT", "METHODS", "RESULTS", "INTRODUCTION", "DISCUSSION"]
    remaining_keys = [k for k in sections if k not in ordered_keys]
    key_order = ordered_keys + remaining_keys

    parts: List[str] = []
    total_chars = 0

    for key in key_order:
        if key not in sections or not sections[key].strip():
            continue

        budget = _SECTION_BUDGETS.get(key, _SECTION_BUDGETS["OTHER"])
        remaining_budget = char_limit - total_chars
        if remaining_budget <= 15:
            break

        header = f"{key}:\n"
        separator = "\n\n" if parts else ""
        overhead = len(separator) + len(header)

        effective_budget = max(0, remaining_budget - overhead)
        effective_budget = min(budget, effective_budget)

        if effective_budget <= 0:
            break

        section_text = _truncate(sections[key], effective_budget)
        parts.append(f"{separator}{header}{section_text}")
        total_chars += overhead + len(section_text)

    return "".join(parts)


# ---------------------------------------------------------------------------
# Core LLM extraction helpers
# ---------------------------------------------------------------------------


def extract_year(pub_date_text: Any) -> Optional[int]:
    """Extract 4-digit year from a publication date string."""
    match = re.search(r"\b(19|20)\d{2}\b", str(pub_date_text))
    return int(match.group(0)) if match else None


def _build_field_result(
    value: Any,
    status: str,
    confidence: Optional[float] = None,
    *,
    ontology_id: str = "",
    mapping_confidence: Optional[float] = None,
) -> Dict[str, Any]:
    if confidence is None:
        confidence = (
            0.85
            if status == "PRESENT"
            else (0.65 if status == "PARTIALLY_PRESENT" else 0.0)
        )
    map_conf = (
        float(mapping_confidence)
        if mapping_confidence is not None
        else float(confidence)
    )
    return {
        "value": "" if status == "ABSENT" else ("" if value is None else str(value)),
        "status": status,
        "confidence": float(confidence),
        "ontology_id": ontology_id or "",
        "mapping_confidence": map_conf,
        "reason_if_missing": (
            "" if status != "ABSENT" else "Information not found in the paper"
        ),
    }


def _build_field_result_from_term(term: Any) -> Dict[str, Any]:
    """Build API field dict from a NormalizedTerm."""
    from app.normalization.types import NormalizedTerm

    if not isinstance(term, NormalizedTerm):
        raise TypeError("expected NormalizedTerm")
    conf = (
        0.85
        if term.status == "PRESENT"
        else (0.65 if term.status == "PARTIALLY_PRESENT" else 0.0)
    )
    return _build_field_result(
        term.label,
        term.status,
        confidence=conf,
        ontology_id=term.ontology_id,
        mapping_confidence=term.mapping_confidence,
    )


def _is_low_quality_cached_result(analysis_data: Dict[str, Any]) -> bool:
    """Treat cached rows with all essential fields ABSENT as stale/low-quality."""
    fields = analysis_data.get("fields") if isinstance(analysis_data, dict) else None
    if not isinstance(fields, dict) or not fields:
        return True

    essential_keys = [
        "host_species",
        "body_site",
        "condition",
        "sequencing_type",
        "sample_size",
    ]

    for key in essential_keys:
        field = fields.get(key)
        if not isinstance(field, dict):
            return False
        if str(field.get("status", "")).upper() != "ABSENT":
            return False

    return True


def _parse_json_object(raw_text: str) -> Dict[str, Any]:
    """Robustly extract a JSON object from an LLM response string."""
    if not raw_text:
        return {}
    try:
        return json.loads(raw_text)
    except json.JSONDecodeError:
        pass
    start = raw_text.find("{")
    end = raw_text.rfind("}") + 1
    if start != -1 and end > start:
        try:
            return json.loads(raw_text[start:end])
        except json.JSONDecodeError:
            pass
    fenced = re.search(r"```(?:json)?\s*(\{.*\})\s*```", raw_text, flags=re.S)
    if fenced:
        try:
            return json.loads(fenced.group(1))
        except json.JSONDecodeError:
            pass
    return {}


def _heuristic_payload_from_text(text: str) -> Dict[str, Any]:
    """Best-effort extraction when the LLM returns invalid/empty JSON."""
    t = (text or "").strip()
    if not t:
        return {}
    lower = t.lower()

    host_species_raw = None
    if re.search(
        r"\b(human|humans|men|women|participants?|subjects?|volunteers?|patients?|athletes?|controls?)\b",
        lower,
    ):
        host_species_raw = "human"
    elif re.search(r"\b(mouse|mice)\b", lower):
        host_species_raw = "mouse"
    elif re.search(r"\b(rat|rats)\b", lower):
        host_species_raw = "rat"

    body_site_raw = None
    if re.search(r"\b(fecal|faecal|feces|faeces|stool)\b", lower):
        body_site_raw = "fecal samples"
    elif re.search(r"\b(oral|saliva|salivary)\b", lower):
        body_site_raw = "oral"
    elif re.search(r"\b(skin|dermal|cutaneous)\b", lower):
        body_site_raw = "skin"

    condition_raw = None
    disease_phrase = re.search(
        r"\bpatients?\s+with\s+([a-z][a-z0-9\-\s]{2,80}?(?:syndrome|disease|disorder|infection|cancer|diabetes))\b",
        lower,
    )
    if disease_phrase:
        condition_raw = disease_phrase.group(1).strip()
    elif re.search(r"\b(healthy controls?|healthy sedentary)\b", lower):
        condition_raw = "healthy"
    else:
        for term in [
            "kostmann syndrome",
            "obesity",
            "diabetes",
            "cancer",
            "ibd",
            "crohn",
            "ulcerative colitis",
            "parkinson",
            "alzheimer",
        ]:
            if term in lower:
                condition_raw = term
                break

    sequencing_type_raw = None
    if "16s" in lower:
        sequencing_type_raw = "16S rRNA gene sequencing"
    elif "shotgun" in lower or "metagenomic" in lower:
        sequencing_type_raw = "shotgun metagenomics"
    elif "high-throughput sequencing" in lower:
        sequencing_type_raw = "high-throughput sequencing"
    elif "sequencing" in lower:
        sequencing_type_raw = "sequencing"

    sample_size_raw: Optional[int] = None
    n_match = re.search(r"\bn\s*=\s*(\d{1,5})\b", lower)
    if n_match:
        sample_size_raw = int(n_match.group(1))
    else:
        mentions = [
            int(m.group(1))
            for m in re.finditer(
                r"\b(\d{1,5})\s+(?:participants?|subjects?|patients?|controls?|samples?|men|women)\b",
                lower,
            )
        ]
        if mentions:
            sample_size_raw = max(mentions)

    return {
        "host_species_raw": host_species_raw,
        "body_site_raw": body_site_raw,
        "condition_raw": condition_raw,
        "sequencing_type_raw": sequencing_type_raw,
        "sample_size_raw": sample_size_raw,
        "has_differential_abundance": bool(
            re.search(
                r"\b(significant(?:ly)?|differential(?:ly)?|enriched|depleted|p\s*[<=>]\s*0?\.\d+)\b",
                lower,
            )
        ),
        "differential_abundance_confidence": (
            0.6
            if re.search(r"\b(significant|differential|p\s*[<=>]\s*0?\.\d+)\b", lower)
            else 0.0
        ),
        "_source": "heuristic",
    }


def _postprocess_field_results(
    field_results: Dict[str, Dict[str, Any]],
    analysis_text: str,
) -> Dict[str, Dict[str, Any]]:
    """Apply deterministic fixes for obvious extraction misses."""
    text = (analysis_text or "").lower()
    out = dict(field_results or {})

    host = dict(out.get("host_species") or {})
    if host.get("status") == "ABSENT" and re.search(
        r"\b(human|humans|men|women|participants?|subjects?|volunteers?|patients?|athletes?|controls?)\b",
        text,
    ):
        host.update(
            {
                "value": "Homo sapiens",
                "status": "PRESENT",
                "ontology_id": "NCBITaxon:9606",
                "mapping_confidence": 1.0,
                "confidence": max(float(host.get("confidence", 0.0) or 0.0), 0.75),
                "reason_if_missing": "",
            }
        )
        out["host_species"] = host

    condition = dict(out.get("condition") or {})
    disease_phrase = re.search(
        r"\bpatients?\s+with\s+([a-z][a-z0-9\-\s]{2,80}?(?:syndrome|disease|disorder|infection|cancer|diabetes))\b",
        text,
    )
    if disease_phrase:
        disease = disease_phrase.group(1).strip()
        if condition.get("status") in {"ABSENT", "PRESENT"}:
            cond_term = normalize_condition(disease)
            if cond_term.status != "ABSENT":
                condition.update(
                    {
                        "value": cond_term.label,
                        "status": cond_term.status,
                        "ontology_id": cond_term.ontology_id,
                        "mapping_confidence": cond_term.mapping_confidence,
                        "confidence": max(
                            float(condition.get("confidence", 0.0) or 0.0), 0.75
                        ),
                        "reason_if_missing": "",
                    }
                )
                out["condition"] = condition

    return out


async def _extract_structured_metadata(
    *,
    context_text: str,
    title: str,
    journal: str,
    year: Any,
) -> Dict[str, Any]:
    """Send one unified extraction call to the LLM and return parsed JSON."""
    unified_qa = get_unified_qa()
    if unified_qa is None:
        return {}

    prompt = EXTRACTION_PROMPT.format(
        title=title or "",
        journal=journal or "",
        year=year if year is not None else "",
        paper_content=context_text or "",
    )
    chat_call = unified_qa.chat(prompt)
    response = (
        await asyncio.wait_for(chat_call, timeout=ANALYSIS_TIMEOUT)
        if asyncio.iscoroutine(chat_call)
        else chat_call
    )
    return _parse_json_object(response.get("text", ""))


def _field_results_from_unified_payload(
    payload: Dict[str, Any]
) -> Dict[str, Dict[str, Any]]:
    """Map unified prompt JSON payload to internal field structure."""
    host_term = normalize_host_species(payload.get("host_species_raw"))
    body_term = normalize_body_site(payload.get("body_site_raw"))
    cond_term = normalize_condition(payload.get("condition_raw"))
    seq_term = normalize_sequencing_type(payload.get("sequencing_type_raw"))
    sample_term = normalize_sample_size(payload.get("sample_size_raw"))

    field_results = {
        "host_species": _build_field_result_from_term(host_term),
        "body_site": _build_field_result_from_term(body_term),
        "condition": _build_field_result_from_term(cond_term),
        "sequencing_type": _build_field_result_from_term(seq_term),
        "sample_size": _build_field_result_from_term(sample_term),
        "taxa_level": create_empty_field_result("taxa_level"),
    }
    if payload.get("_source") == "heuristic":
        for key in (
            "host_species",
            "body_site",
            "condition",
            "sequencing_type",
            "sample_size",
        ):
            field = field_results.get(key, {})
            status = field.get("status")
            if status == "PRESENT":
                field["confidence"] = min(
                    float(field.get("confidence", 0.0) or 0.0), 0.75
                )
            elif status == "PARTIALLY_PRESENT":
                field["confidence"] = min(
                    float(field.get("confidence", 0.0) or 0.0), 0.6
                )
    return field_results


def _normalize_extracted_fields(
    field_results: Dict[str, Dict[str, Any]]
) -> Dict[str, Dict[str, Any]]:
    """Re-normalise field values (idempotent pass for post-processing)."""
    normalized = dict(field_results or {})

    mappings = {
        "host_species": normalize_host_species,
        "body_site": normalize_body_site,
        "condition": normalize_condition,
        "sequencing_type": normalize_sequencing_type,
        "sample_size": normalize_sample_size,
    }
    for key, normalizer in mappings.items():
        current = dict(normalized.get(key) or {})
        term = normalizer(current.get("value") or "")
        current["value"] = term.label if term.status != "ABSENT" else ""
        current["status"] = term.status
        current["ontology_id"] = term.ontology_id
        current["mapping_confidence"] = term.mapping_confidence
        current["confidence"] = float(current.get("confidence", 0.0) or 0.0)
        normalized[key] = current

    return normalized


def _avg_confidence(field_results: Dict[str, Dict[str, Any]]) -> float:
    if not field_results:
        return 0.0
    values = [float(f.get("confidence", 0.0)) for f in field_results.values()]
    return sum(values) / len(values)


def _resolve_diff_abundance(
    payload: Dict[str, Any], fallback_text: str
) -> Tuple[bool, float]:
    """Extract differential abundance fields from LLM payload or use heuristic."""
    try:
        return (
            bool(payload.get("has_differential_abundance", False)),
            float(payload.get("differential_abundance_confidence", 0.0)),
        )
    except (TypeError, ValueError):
        return detect_differential_abundance(fallback_text)


# ---------------------------------------------------------------------------
# analyze_paper_simple
# ---------------------------------------------------------------------------


async def analyze_paper_simple(
    pmid: str, force_refresh: bool = False
) -> Optional[Dict[str, Any]]:
    """Extract BugSigDB fields from a paper.

    Uses the unified extraction flow (single LLM call per paper).
    Checks cache first; falls back gracefully when full text is unavailable.
    """
    try:
        cache_manager = get_cache_manager()
        pubmed_retriever = get_pubmed_retriever()

        if pubmed_retriever is None:
            logger.error("PubMedRetriever not available – check NCBI_API_KEY")
            return None

        cached = cache_manager.get_analysis_result(pmid)
        low_quality_cached: Optional[Dict[str, Any]] = None
        if (
            (not force_refresh)
            and cached
            and cache_manager.is_cache_valid(
                cached.get("timestamp", ""), max_age_hours=CACHE_VALIDITY_HOURS
            )
        ):
            cached_analysis = cached.get("analysis_data") or {}
            if _is_low_quality_cached_result(cached_analysis):
                low_quality_cached = cached_analysis
                logger.info(
                    "Cached analysis for PMID %s has all essential fields ABSENT; recomputing",
                    pmid,
                )
            else:
                logger.info(f"Returning cached analysis for PMID {pmid}")
                return cached_analysis
        elif force_refresh and cached:
            logger.info("Force refresh enabled for PMID %s; bypassing cache", pmid)

        logger.info(f"Starting simple analysis for PMID {pmid}")

        texts = await pubmed_retriever.get_texts_for_analysis_async(pmid)
        if not texts.get("title") and not texts.get("abstract"):
            logger.warning(f"No content found for PMID {pmid}")
            if low_quality_cached is not None:
                logger.info(
                    "Returning low-quality cached analysis for PMID %s because fresh retrieval failed",
                    pmid,
                )
                return low_quality_cached
            return None

        title = texts.get("title", "")
        abstract = texts.get("abstract", "")
        full_text = texts.get("full_text", "")
        year = extract_year(texts.get("publication_date", ""))

        analysis_text = prepare_analysis_context(abstract, full_text)

        if not analysis_text.strip():
            logger.warning(f"No analysable text found for PMID {pmid}")
            return None

        payload = await _extract_structured_metadata(
            context_text=analysis_text,
            title=title,
            journal=texts.get("journal", ""),
            year=year if year is not None else "",
        )
        if not payload:
            logger.warning(
                "Structured metadata extraction returned empty payload for PMID %s; using heuristic fallback",
                pmid,
            )
            payload = _heuristic_payload_from_text(analysis_text)
        field_results = _field_results_from_unified_payload(payload)
        field_results = _postprocess_field_results(field_results, analysis_text)
        has_diff_abund, diff_abund_conf = _resolve_diff_abundance(
            payload, analysis_text
        )

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
            "analysis_timestamp": _current_timestamp(),
            "model_used": DEFAULT_MODEL,
        }

        logger.info(f"Simple analysis completed for PMID {pmid}")

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
            logger.warning(f"Unable to cache analysis for PMID {pmid}: {cache_error}")

        return result

    except Exception as e:
        logger.error(f"Error in simple analysis for PMID {pmid}: {e}")
        if "low_quality_cached" in locals() and low_quality_cached is not None:
            logger.info(
                "Returning low-quality cached analysis for PMID %s after analysis exception",
                pmid,
            )
            return low_quality_cached
        return None


# ---------------------------------------------------------------------------
# analyze_paper_with_rag
# ---------------------------------------------------------------------------


async def analyze_paper_with_rag(
    pmid: str,
    rag_config: Optional[Dict] = None,
    use_rag: bool = True,
) -> Optional[Dict]:
    """Analyse a paper with optional RAG augmentation."""
    import time

    start_time = time.time()

    try:
        cache_manager = get_cache_manager()
        pubmed_retriever = get_pubmed_retriever()

        if pubmed_retriever is None:
            logger.error("PubMedRetriever not available – check NCBI_API_KEY")
            return None

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

        logger.info(f"Starting RAG analysis for PMID {pmid} (RAG={use_rag_final})")

        texts = await pubmed_retriever.get_texts_for_analysis_async(pmid)
        if not texts.get("title") and not texts.get("abstract"):
            logger.warning(f"No content found for PMID {pmid}")
            return None

        title = texts.get("title", "")
        abstract = texts.get("abstract", "")
        full_text = texts.get("full_text", "")
        year = extract_year(texts.get("publication_date", ""))

        analysis_text = prepare_analysis_context(abstract, full_text)

        if not analysis_text.strip():
            logger.warning(f"No analysable text found for PMID {pmid}")
            return None

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
                    f"Created {len(chunks)} section-aware chunks for PMID {pmid}"
                )
            except Exception as chunk_error:
                logger.warning(f"Chunking failed: {chunk_error}")
                chunks = None

        context_for_prompt = analysis_text
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
                    f"RAG context retrieval failed, using prepared context: {rag_error}"
                )

        processing_time = time.time() - start_time

        payload = await _extract_structured_metadata(
            context_text=context_for_prompt,
            title=title,
            journal=texts.get("journal", ""),
            year=year if year is not None else "",
        )
        if not payload:
            logger.warning(
                "Structured metadata extraction returned empty payload for PMID %s; using heuristic fallback",
                pmid,
            )
            payload = _heuristic_payload_from_text(analysis_text)
        field_results = _field_results_from_unified_payload(payload)
        field_results = _postprocess_field_results(field_results, analysis_text)
        has_diff_abund, diff_abund_conf = _resolve_diff_abundance(
            payload, analysis_text
        )

        result: Dict[str, Any] = {
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
            "analysis_timestamp": _current_timestamp(),
            "model_used": DEFAULT_MODEL,
            "processing_time": processing_time,
            "rag_enabled": use_rag_final,
            "rag_stats": None,
            "rag_config_used": rag_config_dict if use_rag_final else None,
        }

        if use_rag_final and chunks:
            result["rag_stats"] = _collect_rag_stats(
                chunks=chunks,
                field_results=field_results,
                rag_config_dict=rag_config_dict,
                processing_time=processing_time,
            )

        logger.info(f"RAG analysis completed for PMID {pmid} in {processing_time:.2f}s")

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
            logger.warning(f"Unable to cache analysis for PMID {pmid}: {cache_error}")

        return result

    except Exception as e:
        logger.error(f"Error in RAG analysis for PMID {pmid}: {e}")
        return None


def _collect_rag_stats(
    *,
    chunks: List,
    field_results: Dict[str, Dict[str, Any]],
    rag_config_dict: Optional[Dict],
    processing_time: float,
) -> Dict[str, Any]:
    """Collect RAG metrics into the rag_stats dict."""
    _rc = rag_config_dict or {}
    rag_metrics: Dict[str, Any] = {}

    try:
        from app.services.advanced_rag import AdvancedRAGService

        svc = AdvancedRAGService(
            rerank_method=_rc.get("rerank_method", "hybrid"),
            evidence_k=_rc.get("evidence_k"),
            max_sources=_rc.get("max_sources"),
            use_10_scale=_rc.get("use_10_scale", True),
        )
        rag_metrics = svc.get_rerank_metrics()
    except Exception:
        pass

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
# analyze_single_field  (kept for backward compatibility)
# ---------------------------------------------------------------------------


async def analyze_single_field(
    text: str,
    field_name: str,
    question: str,
    pmid: str,
    chunks: Optional[List] = None,
    rag_config: Optional[Dict] = None,
) -> Dict:
    """Extract a single field value from text using the LLM."""
    try:
        context_text = _build_single_field_context(
            text, field_name, question, chunks, rag_config
        )
        return await _query_single_field(context_text, field_name, question, pmid)
    except asyncio.TimeoutError:
        logger.warning(f"Field {field_name} timed out for PMID {pmid}")
        return create_empty_field_result(field_name)
    except Exception as e:
        logger.error(f"Error analysing field {field_name} for PMID {pmid}: {e}")
        return create_empty_field_result(field_name)


async def _build_single_field_context(
    text: str,
    field_name: str,
    question: str,
    chunks: Optional[List],
    rag_config: Optional[Dict],
) -> str:
    """Resolve the best context string for a single-field extraction."""
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
        logger.info(f"RAG context for field {field_name}: {len(ctx)} chars")
        return ctx
    except Exception as rag_error:
        logger.warning(
            f"RAG failed for field {field_name}, using plain text: {rag_error}"
        )
        return text[:2_000]


async def _query_single_field(
    context_text: str, field_name: str, question: str, pmid: str
) -> Dict:
    """Send a single-field prompt to the LLM and parse the response."""
    prompt = f"""Context: {context_text}

Question: {question}

Respond ONLY with a JSON object (no markdown):
{{
    "value": "specific answer or null if not found",
    "status": "PRESENT|PARTIALLY_PRESENT|ABSENT",
    "confidence": 0.0-1.0,
    "reason_if_missing": "explanation if absent"
}}"""

    unified_qa = get_unified_qa()
    if unified_qa is None:
        logger.error("UnifiedQA not available – check GEMINI_API_KEY")
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
        logger.info(f"Falling back to GeminiQA for field {field_name}")
        try:
            from app.models.gemini_qa import GeminiQA

            response = await asyncio.wait_for(
                GeminiQA(api_key=GEMINI_API_KEY).chat(prompt), timeout=ANALYSIS_TIMEOUT
            )
            answer_text = response.get("text", "")
        except Exception as fb_err:
            logger.error(f"GeminiQA fallback failed: {fb_err}")
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


# ---------------------------------------------------------------------------
# Utility functions
# ---------------------------------------------------------------------------


def create_empty_field_result(field_name: str) -> Dict:
    """Return a safe empty result when field extraction fails."""
    return {
        "value": None,
        "status": "ABSENT",
        "confidence": 0.0,
        "ontology_id": "",
        "mapping_confidence": 0.0,
        "reason_if_missing": "Analysis failed or timed out",
    }


def detect_differential_abundance(text: str) -> Tuple[bool, float]:
    """Heuristic differential abundance detector."""
    if not text or not str(text).strip():
        return False, 0.0

    t = str(text).lower()

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
    medium_patterns = [
        r"\bcompared to\b",
        r"\bversus\b|\bvs\.\b|\bvs\b",
        r"\bdifference(?:s)? in\b",
        r"\bassociated with\b",
        r"\bincrease(?:d)?\b|\bdecrease(?:d)?\b",
    ]
    weak_patterns = [
        r"\b(relative )?abundance\b",
        r"\bcomposition\b",
        r"\bdysbiosis\b",
        r"\b(beta|alpha) diversity\b",
        r"\bcommunity structure\b",
    ]

    def _count(patterns: List[str]) -> int:
        return sum(1 for p in patterns if re.search(p, t, re.IGNORECASE))

    strong = _count(strong_patterns)
    medium = _count(medium_patterns)
    weak = _count(weak_patterns)

    score = 0.0
    if strong:
        score = 0.75 + min(0.25, 0.08 * (strong - 1) + 0.05 * medium + 0.03 * weak)
    elif medium:
        score = 0.45 + min(0.35, 0.08 * (medium - 1) + 0.05 * weak)
    elif weak:
        score = min(0.35, 0.10 + 0.08 * weak)

    score = max(0.0, min(1.0, score))
    return score >= 0.6, float(score)
