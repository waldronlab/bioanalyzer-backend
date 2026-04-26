"""Condition normalization aligned with EFO canonical labels."""

from __future__ import annotations

from typing import Tuple

import requests

CONDITION_LOOKUP = {
    "parkinson disease": "Parkinson disease",
    "parkinson's": "Parkinson disease",
    "parkinson": "Parkinson disease",
    "alzheimer disease": "Alzheimer disease",
    "alzheimer's": "Alzheimer disease",
    "alzheimer": "Alzheimer disease",
    "inflammatory bowel": "inflammatory bowel disease",
    "ibd": "inflammatory bowel disease",
    "crohn's": "Crohn disease",
    "crohn": "Crohn disease",
    "ulcerative colitis": "ulcerative colitis",
    "colorectal cancer": "colorectal cancer",
    "colon cancer": "colorectal cancer",
    "obesity": "obesity",
    "obese": "obesity",
    "overweight": "obesity",
    "type 2 diabetes": "type 2 diabetes mellitus",
    "t2d": "type 2 diabetes mellitus",
    "type 1 diabetes": "type 1 diabetes mellitus",
    "t1d": "type 1 diabetes mellitus",
    "diabetes": "diabetes mellitus",
    "autism": "autism spectrum disorder",
    "asd": "autism spectrum disorder",
    "multiple sclerosis": "multiple sclerosis",
    "depression": "major depressive disorder",
    "anxiety": "anxiety disorder",
    "covid-19": "COVID-19",
    "sars-cov-2": "COVID-19",
    "covid": "COVID-19",
    "hiv": "HIV infection",
    "hepatitis": "hepatitis",
    "liver cirrhosis": "liver cirrhosis",
    "nonalcoholic fatty liver": "non-alcoholic fatty liver disease",
    "nafld": "non-alcoholic fatty liver disease",
    "celiac": "celiac disease",
    "coeliac": "celiac disease",
    "asthma": "asthma",
    "allergy": "allergy",
    "rheumatoid arthritis": "rheumatoid arthritis",
    "lupus": "systemic lupus erythematosus",
    "psoriasis": "psoriasis",
    "antibiotic": "antibiotic exposure",
    "healthy": "healthy",
    "control": "healthy",
    "normal": "healthy",
}

OLS_SEARCH_URL = "https://www.ebi.ac.uk/ols4/api/search"


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


def normalize_condition(raw_text: str) -> Tuple[str, str]:
    """Return normalized condition and extraction status."""
    if not raw_text or raw_text.strip() == "":
        return "", "ABSENT"

    lowered = raw_text.lower()
    match = None
    match_len = 0
    for key, value in CONDITION_LOOKUP.items():
        if key in lowered and len(key) > match_len:
            match = value
            match_len = len(key)
    if match:
        return match, "PRESENT"

    clean_term = _extract_clean_disease_name(raw_text)
    try:
        params = {
            "q": clean_term,
            "ontology": "efo",
            "fieldList": "label,obo_id",
            "rows": 1,
            "exact": "false",
        }
        response = requests.get(OLS_SEARCH_URL, params=params, timeout=5)
        response.raise_for_status()
        docs = response.json().get("response", {}).get("docs", [])
        if docs:
            label = docs[0].get("label", "")
            if label:
                return label, "PRESENT"
    except Exception:
        pass

    return raw_text.strip(), "PARTIALLY_PRESENT"

