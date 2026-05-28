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


def normalize_condition(raw_text: str) -> NormalizedTerm:
    """Return normalized condition label, EFO ID, status, and mapping confidence."""
    if not raw_text or raw_text.strip() == "":
        return NormalizedTerm.absent()

    lowered = raw_text.lower()
    match: Tuple[str, str] | None = None
    match_len = 0
    for key, pair in CONDITION_LOOKUP.items():
        if key in lowered and len(key) > match_len:
            match = pair
            match_len = len(key)
    if match:
        label, efo_id = match
        return NormalizedTerm(label, efo_id, "PRESENT", 1.0)

    clean_term = _extract_clean_disease_name(raw_text)
    hit = ols_search(clean_term or raw_text.strip(), "efo", "EFO", mapping_confidence=0.9)
    if hit:
        label, efo_id, conf = hit
        return NormalizedTerm(label, efo_id, "PRESENT", conf)

    stripped = raw_text.strip()
    return NormalizedTerm(stripped, "", "PARTIALLY_PRESENT", 0.5)
