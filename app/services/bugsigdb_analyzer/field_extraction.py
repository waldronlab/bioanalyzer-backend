"""
Turning raw LLM/heuristic payloads into normalized field results: FieldDict
builders, cache-quality checks, JSON/heuristic parsers, postprocessing
fixes, LLM-driven structured-metadata extraction, and differential
abundance detection.
"""

import asyncio
import json
import re
from typing import Any, Dict, List, Optional, Tuple

import app.services.bugsigdb_analyzer as _pkg
from app.normalization.body_site import normalize_body_site
from app.normalization.condition import normalize_condition
from app.normalization.host_species import normalize_host_species
from app.normalization.sample_size import normalize_sample_size
from app.normalization.sequencing_type import normalize_sequencing_type
from app.utils.config import ANALYSIS_TIMEOUT

from .constants import EXTRACTION_PROMPT

# ---------------------------------------------------------------------------
# FieldResult builders
# ---------------------------------------------------------------------------


def _build_field_result(
    value: Any,
    status: str,
    confidence: Optional[float] = None,
    *,
    ontology_id: str = "",
    mapping_confidence: Optional[float] = None,
) -> Dict[str, Any]:
    """
    Build the canonical FieldDict stored under result['fields'][key].

    Keys and semantics must never be renamed without updating data.R.
    """
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
        "mapping_tier": "none",
        "mapping_candidates": [],
    }


def _build_field_result_from_term(term: Any) -> Dict[str, Any]:
    """Build a FieldDict from a NormalizedTerm.

    Includes a `raw` key holding the pre-normalization text (currently
    populated only by normalize_sequencing_type, e.g. when it falls back
    to "other") so the side-by-side original wording isn't lost.
    """
    from app.normalization.grounding import TIER_AUTO, tier_for
    from app.normalization.types import NormalizedTerm

    if not isinstance(term, NormalizedTerm):
        raise TypeError("expected NormalizedTerm")
    conf = (
        0.85
        if term.status == "PRESENT"
        else (0.65 if term.status == "PARTIALLY_PRESENT" else 0.0)
    )
    result = _build_field_result(
        term.label,
        term.status,
        confidence=conf,
        ontology_id=term.ontology_id,
        mapping_confidence=term.mapping_confidence,
    )
    result["raw"] = term.raw
    tier = tier_for(term)
    result["mapping_tier"] = tier
    result["mapping_candidates"] = (
        [{"label": label, "ontology_id": oid} for label, oid in term.candidates]
        if tier != TIER_AUTO
        else []
    )
    return result


# ---------------------------------------------------------------------------
# Cache quality check
# ---------------------------------------------------------------------------


def _is_low_quality_cached_result(analysis_data: Dict[str, Any]) -> bool:
    """Return True when every essential field in a cached result is ABSENT."""
    fields = analysis_data.get("fields") if isinstance(analysis_data, dict) else None
    if not isinstance(fields, dict) or not fields:
        return True
    for key in (
        "host_species",
        "body_site",
        "condition",
        "sequencing_type",
        "sample_size",
    ):
        field = fields.get(key)
        if not isinstance(field, dict):
            return False
        if str(field.get("status", "")).upper() != "ABSENT":
            return False
    return True


# ---------------------------------------------------------------------------
# JSON / heuristic parsers
# ---------------------------------------------------------------------------


def _parse_json_object(raw_text: str) -> Dict[str, Any]:
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
    """Best-effort field extraction when the LLM returns invalid/empty JSON."""
    t = (text or "").strip()
    if not t:
        return {}
    lower = t.lower()

    # Check explicit animal mentions first: "controls"/"subjects"/etc. below
    # are weak, species-ambiguous cues (animal studies use "controls" too,
    # e.g. "wild-type controls") - checking them first via if/elif would let
    # them mask an explicit "mice"/"rats" mention elsewhere in the same text.
    host_species_raw = None
    if re.search(r"\b(mouse|mice)\b", lower):
        host_species_raw = "mouse"
    elif re.search(r"\b(rat|rats)\b", lower):
        host_species_raw = "rat"
    elif re.search(
        r"\b(human|humans|men|women|participants?|subjects?|volunteers?|patients?|athletes?|controls?)\b",
        lower,
    ):
        host_species_raw = "human"

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

    has_diff_abundance = bool(
        re.search(
            r"\b(significant(?:ly)?|differential(?:ly)?|enriched|depleted|p\s*[<=>]\s*0?\.\d+)\b",
            lower,
        )
    )
    return {
        "host_species_raw": host_species_raw,
        "body_site_raw": body_site_raw,
        "condition_raw": condition_raw,
        "sequencing_type_raw": sequencing_type_raw,
        "sample_size_raw": sample_size_raw,
        # Confidence must never be 0.0 while the boolean is True - both are
        # derived from the same match so they can't disagree (previously the
        # confidence regex lacked the boolean regex's "(?:ly)?"/enriched/
        # depleted alternatives, so e.g. "significantly enriched" set
        # has_differential_abundance=True with confidence=0.0).
        "has_differential_abundance": has_diff_abundance,
        "differential_abundance_confidence": 0.6 if has_diff_abundance else 0.0,
        "_source": "heuristic",
    }


def _build_curation_summary(field_results: Dict[str, Dict[str, Any]]) -> str:
    """Brief curator-facing summary from normalized field values."""
    parts: List[str] = []
    condition = field_results.get("condition", {})
    if condition.get("status") != "ABSENT" and condition.get("value"):
        parts.append(f"Condition: {condition['value']}.")
    host = field_results.get("host_species", {})
    body = field_results.get("body_site", {})
    if host.get("status") != "ABSENT" and host.get("value"):
        parts.append(f"Host: {host['value']}.")
    if body.get("status") != "ABSENT" and body.get("value"):
        parts.append(f"Body site: {body['value']}.")
    return " ".join(parts).strip()


def _postprocess_field_results(
    field_results: Dict[str, Dict[str, Any]],
    analysis_text: str,
) -> Dict[str, Dict[str, Any]]:
    """Apply deterministic fixes for obvious extraction misses."""
    text = (analysis_text or "").lower()
    out = dict(field_results or {})

    # --- host_species: if ABSENT but text clearly mentions humans, patch it ---
    # The human-cue regex includes weak, species-ambiguous words ("controls",
    # "subjects") that animal studies use too (e.g. "wild-type controls") -
    # require the absence of an explicit animal mention before assuming human,
    # so a mouse/rat study whose host_species the LLM missed doesn't get
    # force-corrected to "Homo sapiens".
    host = dict(out.get("host_species") or {})
    if (
        host.get("status") == "ABSENT"
        and re.search(
            r"\b(human|humans|men|women|participants?|subjects?|volunteers?|patients?|athletes?|controls?)\b",
            text,
        )
        and not re.search(r"\b(mouse|mice|rat|rats)\b", text)
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

    # --- condition: if text names a disease, normalise it ---
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


# ---------------------------------------------------------------------------
# LLM extraction
# ---------------------------------------------------------------------------


async def _extract_structured_metadata(
    *,
    context_text: str,
    title: str,
    journal: str,
    year: Any,
) -> Dict[str, Any]:
    unified_qa = _pkg.get_unified_qa()
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
    payload: Dict[str, Any],
) -> Dict[str, Dict[str, Any]]:
    """
    Map the unified-prompt JSON payload to the result['fields'] dict.

    Keys used here MUST match FIELD_KEYS and the column names expected by data.R.
    """
    host_term = normalize_host_species(payload.get("host_species_raw"))
    body_term = normalize_body_site(payload.get("body_site_raw"))
    cond_term = normalize_condition(payload.get("condition_raw"))
    seq_term = normalize_sequencing_type(payload.get("sequencing_type_raw"))
    samp_term = normalize_sample_size(payload.get("sample_size_raw"))

    field_results = {
        "host_species": _build_field_result_from_term(host_term),
        "body_site": _build_field_result_from_term(body_term),
        "condition": _build_field_result_from_term(cond_term),
        "sequencing_type": _build_field_result_from_term(seq_term),
        "sample_size": _build_field_result_from_term(samp_term),
    }

    # Heuristic payloads get a confidence cap — they are less reliable
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
                    float(field.get("confidence", 0.0) or 0.0), 0.60
                )

    return field_results


def _avg_confidence(field_results: Dict[str, Dict[str, Any]]) -> float:
    if not field_results:
        return 0.0
    values = [float(f.get("confidence", 0.0)) for f in field_results.values()]
    return sum(values) / len(values)


def _resolve_diff_abundance(
    payload: Dict[str, Any], fallback_text: str
) -> Tuple[bool, float]:
    try:
        has_da = bool(payload.get("has_differential_abundance", False))
        conf = max(
            0.0, min(1.0, float(payload.get("differential_abundance_confidence", 0.0)))
        )
        return has_da, conf
    except (TypeError, ValueError):
        return detect_differential_abundance(fallback_text)


def extract_year(pub_date_text: Any) -> Optional[int]:
    """Extract a 4-digit year from a publication-date string."""
    match = re.search(r"\b(19|20)\d{2}\b", str(pub_date_text))
    return int(match.group(0)) if match else None


# ---------------------------------------------------------------------------
# Utility functions
# ---------------------------------------------------------------------------


def create_empty_field_result(field_name: str) -> Dict:
    """Return a safe ABSENT FieldDict when extraction fails."""
    return {
        "value": None,
        "status": "ABSENT",
        "confidence": 0.0,
        "ontology_id": "",
        "mapping_confidence": 0.0,
        "reason_if_missing": "Analysis failed or timed out",
        "mapping_tier": "none",
        "mapping_candidates": [],
    }


def detect_differential_abundance(text: str) -> Tuple[bool, float]:
    """Heuristic detector for differential abundance signals in text."""
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
