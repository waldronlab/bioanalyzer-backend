"""Condition normalization aligned with EFO canonical labels and IDs."""

from __future__ import annotations

from typing import Dict, Tuple

from app.normalization.ols import ols_search
from app.normalization.types import NormalizedTerm

# keyword -> (canonical label, EFO ID)
CONDITION_LOOKUP: Dict[str, Tuple[str, str]] = {
    "parkinson disease": ("Parkinson disease", "EFO:0002508"),
    "parkinson's": ("Parkinson disease", "EFO:0002508"),
    "parkinson": ("Parkinson disease", "EFO:0002508"),
    "alzheimer disease": ("Alzheimer disease", "EFO:0000249"),
    "alzheimer's": ("Alzheimer disease", "EFO:0000249"),
    "alzheimer": ("Alzheimer disease", "EFO:0000249"),
    "inflammatory bowel": ("inflammatory bowel disease", "EFO:0003764"),
    "ibd": ("inflammatory bowel disease", "EFO:0003764"),
    "crohn's": ("Crohn disease", "EFO:0000384"),
    "crohn": ("Crohn disease", "EFO:0000384"),
    "ulcerative colitis": ("ulcerative colitis", "EFO:0000729"),
    "colorectal cancer": ("colorectal cancer", "EFO:0005842"),
    "colon cancer": ("colorectal cancer", "EFO:0005842"),
    "obesity": ("obesity", "EFO:0001073"),
    "obese": ("obesity", "EFO:0001073"),
    "overweight": ("obesity", "EFO:0001073"),
    "type 2 diabetes": ("type 2 diabetes mellitus", "EFO:0001360"),
    "t2d": ("type 2 diabetes mellitus", "EFO:0001360"),
    "type 1 diabetes": ("type 1 diabetes mellitus", "EFO:0001361"),
    "t1d": ("type 1 diabetes mellitus", "EFO:0001361"),
    "diabetes": ("diabetes mellitus", "EFO:0000400"),
    "autism": ("autism spectrum disorder", "EFO:0003756"),
    "asd": ("autism spectrum disorder", "EFO:0003756"),
    "multiple sclerosis": ("multiple sclerosis", "EFO:0003885"),
    "depression": ("major depressive disorder", "EFO:0003761"),
    "anxiety": ("anxiety disorder", "EFO:0009170"),
    "covid-19": ("COVID-19", "EFO:0003601"),
    "sars-cov-2": ("COVID-19", "EFO:0003601"),
    "covid": ("COVID-19", "EFO:0003601"),
    "hiv": ("HIV infection", "EFO:0000189"),
    "hepatitis": ("hepatitis", "EFO:0000702"),
    "liver cirrhosis": ("liver cirrhosis", "EFO:0001421"),
    "nonalcoholic fatty liver": ("non-alcoholic fatty liver disease", "EFO:0003102"),
    "nafld": ("non-alcoholic fatty liver disease", "EFO:0003102"),
    "celiac": ("celiac disease", "EFO:0001060"),
    "coeliac": ("celiac disease", "EFO:0001060"),
    "asthma": ("asthma", "EFO:0000276"),
    "allergy": ("allergy", "EFO:0000530"),
    "rheumatoid arthritis": ("rheumatoid arthritis", "EFO:0000686"),
    "lupus": ("systemic lupus erythematosus", "EFO:0000770"),
    "psoriasis": ("psoriasis", "EFO:0000676"),
    "antibiotic": ("antibiotic exposure", "EFO:0009226"),
    "healthy": ("healthy", "EFO:0000246"),
    "control": ("healthy", "EFO:0000246"),
    "normal": ("healthy", "EFO:0000246"),
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

    clean_term = _extract_clean_disease_name(raw_text)
    hit = ols_search(
        clean_term or raw_text.strip(), "efo", "EFO", mapping_confidence=0.9
    )
    if hit:
        label, efo_id, conf = hit
        return NormalizedTerm(label, efo_id, "PRESENT", conf)

    stripped = raw_text.strip()
    return NormalizedTerm(stripped, "", "PARTIALLY_PRESENT", 0.5)
