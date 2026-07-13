"""Condition normalization aligned with EFO canonical labels and IDs."""

from __future__ import annotations

from typing import Dict, Tuple

from app.normalization.ols import ols_search
from app.normalization.types import NormalizedTerm

# keyword -> (canonical label, ontology ID)
#
# Every ID below was verified against the live EBI OLS API (the same source
# ols_search() below falls back to) on 2026-07-12, after an audit found most
# of a prior version of this dict pointed at wrong or obsolete EFO terms
# (fabricated-looking IDs that didn't survive a live lookup - see
# docs/PROJECT_AUDIT.md). EFO is used where a live EFO term exists; MONDO is
# used where EFO has retired the term in favor of MONDO (OLS reports this as
# the term's replacement). A handful of non-disease comparator-arm/exposure
# concepts ("healthy"/"control"/"normal", "antibiotic") have no clean
# disease-ontology equivalent and are intentionally left with ontology_id=""
# rather than force a fabricated ID - normalize_condition() still returns
# their label, just with mapping_tier="none" (see grounding.py).
CONDITION_LOOKUP: Dict[str, Tuple[str, str]] = {
    "parkinson disease": ("Parkinson disease", "MONDO:0005180"),
    "parkinson's": ("Parkinson disease", "MONDO:0005180"),
    "parkinson": ("Parkinson disease", "MONDO:0005180"),
    "alzheimer disease": ("Alzheimer disease", "MONDO:0004975"),
    "alzheimer's": ("Alzheimer disease", "MONDO:0004975"),
    "alzheimer": ("Alzheimer disease", "MONDO:0004975"),
    "inflammatory bowel": ("inflammatory bowel disease", "MONDO:0005265"),
    "ibd": ("inflammatory bowel disease", "MONDO:0005265"),
    "crohn's": ("Crohn disease", "MONDO:0005011"),
    "crohn": ("Crohn disease", "MONDO:0005011"),
    "ulcerative colitis": ("ulcerative colitis", "MONDO:0005101"),
    "colorectal cancer": ("colorectal cancer", "MONDO:0005575"),
    "colon cancer": ("colorectal cancer", "MONDO:0005575"),
    "obesity": ("obesity disorder", "MONDO:0011122"),
    "obese": ("obesity disorder", "MONDO:0011122"),
    "overweight": ("obesity disorder", "MONDO:0011122"),
    "type 2 diabetes": ("type 2 diabetes mellitus", "MONDO:0005148"),
    "t2d": ("type 2 diabetes mellitus", "MONDO:0005148"),
    "type 1 diabetes": ("type 1 diabetes mellitus", "MONDO:0005147"),
    "t1d": ("type 1 diabetes mellitus", "MONDO:0005147"),
    "diabetes": ("diabetes mellitus", "EFO:0000400"),
    "autism": ("autism spectrum disorder", "MONDO:0005258"),
    "asd": ("autism spectrum disorder", "MONDO:0005258"),
    "multiple sclerosis": ("multiple sclerosis", "MONDO:0005301"),
    "depression": ("major depressive disorder", "MONDO:0002009"),
    "anxiety": ("anxiety disorder", "MONDO:0005618"),
    "covid-19": ("COVID-19", "MONDO:0100096"),
    "sars-cov-2": ("COVID-19", "MONDO:0100096"),
    "covid": ("COVID-19", "MONDO:0100096"),
    "hiv": ("HIV infectious disease", "MONDO:0005109"),
    "hepatitis": ("hepatitis", "MONDO:0002251"),
    "liver cirrhosis": ("cirrhosis of liver", "MONDO:0005155"),
    "nonalcoholic fatty liver": (
        "metabolic dysfunction-associated steatotic liver disease",
        "MONDO:0013209",
    ),
    "nafld": (
        "metabolic dysfunction-associated steatotic liver disease",
        "MONDO:0013209",
    ),
    "celiac": ("celiac disease", "MONDO:0005130"),
    "coeliac": ("celiac disease", "MONDO:0005130"),
    "asthma": ("asthma", "MONDO:0004979"),
    "allergy": ("allergic disease", "MONDO:0005271"),
    "rheumatoid arthritis": ("rheumatoid arthritis", "MONDO:0008383"),
    "lupus": ("systemic lupus erythematosus", "MONDO:0007915"),
    "psoriasis": ("psoriasis", "MONDO:0005083"),
    "antibiotic": ("antibiotic exposure", ""),
    "healthy": ("healthy", ""),
    "control": ("healthy", ""),
    "normal": ("healthy", ""),
}


def _extract_clean_disease_name(raw_text: str) -> str:
    strip_phrases = [
        "patients with",
        "patient with",
        "subjects with",
        "individuals with",
        "diagnosis of",
        "diagnosed with",
        "suffering from",
        "history of",
        "associated with",
        "related to",
        "study of",
        "analysis of",
    ]
    text = raw_text.lower()
    for phrase in strip_phrases:
        text = text.replace(phrase, "")
    return text.strip()


# "control"/"normal"/"healthy" describe the comparator arm of a case-control
# study, not a diagnosis - and they're frequently *longer* than the disease
# abbreviation they're being contrasted with ("IBD patients vs healthy
# controls", "HIV patients compared to controls"). Plain longest-match-wins
# would pick "control(s)" over "IBD"/"HIV"/"ASD"/"T2D" and misreport the
# actual studied condition as "healthy". These three keys are only used as
# a last resort, never over a real disease-name match.
_HEALTHY_KEYS = {"healthy", "control", "normal"}


def _other_condition_candidates(
    lowered: str, match_key: str, exclude: Tuple[str, str], limit: int = 2
) -> Tuple[Tuple[str, str], ...]:
    """Other CONDITION_LOOKUP matches that are genuinely distinct conditions
    (not just a shorter/longer phrasing of the winning match, e.g. "diabetes"
    vs "type 2 diabetes") - surfaced so curators can pick when a paper
    mentions more than one condition. A key that's a substring of
    match_key (or vice versa) is the same underlying mention at a different
    specificity, not a separate candidate."""
    found: list[Tuple[str, str]] = []
    for key, pair in CONDITION_LOOKUP.items():
        if key not in lowered or key in _HEALTHY_KEYS or pair == exclude:
            continue
        if key in match_key or match_key in key:
            continue
        if pair not in found:
            found.append(pair)
        if len(found) >= limit:
            break
    return tuple(found)


def normalize_condition(raw_text: str) -> NormalizedTerm:
    """Return normalized condition label, EFO ID, status, and mapping confidence."""
    if not raw_text or raw_text.strip() == "":
        return NormalizedTerm.absent()

    lowered = raw_text.lower()
    match: Tuple[str, str] | None = None
    match_key = ""
    match_len = 0
    healthy_match: Tuple[str, str] | None = None
    for key, pair in CONDITION_LOOKUP.items():
        if key not in lowered:
            continue
        if key in _HEALTHY_KEYS:
            healthy_match = pair
            continue
        if len(key) > match_len:
            match = pair
            match_key = key
            match_len = len(key)
    if match:
        label, efo_id = match
        candidates = _other_condition_candidates(lowered, match_key, match)
        if candidates:
            return NormalizedTerm(
                label, efo_id, "PARTIALLY_PRESENT", 0.9, candidates=candidates
            )
        return NormalizedTerm(label, efo_id, "PRESENT", 1.0)
    if healthy_match:
        label, efo_id = healthy_match
        return NormalizedTerm(label, efo_id, "PRESENT", 1.0)

    # Live fallback for anything not in the static lookup above: try EFO
    # first (matches this module's documented convention), then MONDO -
    # EFO has retired most disease terms in favor of MONDO (see the dict's
    # docstring), so a term absent from EFO is often still live in MONDO.
    # Both providers go through ols_search()'s persistent cache (see
    # app.normalization.ontology_cache), so a term only needs a live lookup
    # once - subsequent calls for the same term are served from that cache.
    clean_term = _extract_clean_disease_name(raw_text)
    query = clean_term or raw_text.strip()
    hit = ols_search(query, "efo", "EFO", mapping_confidence=0.9)
    if not hit:
        hit = ols_search(query, "mondo", "MONDO", mapping_confidence=0.9)
    if hit:
        label, efo_id, conf = hit
        return NormalizedTerm(label, efo_id, "PRESENT", conf)

    stripped = raw_text.strip()
    return NormalizedTerm(stripped, "", "PARTIALLY_PRESENT", 0.5)
