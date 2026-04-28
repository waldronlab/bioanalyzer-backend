"""Body site normalization aligned with UBERON-style labels."""

from __future__ import annotations

from typing import Tuple

import requests

BODY_SITE_LOOKUP = {
    "feces": "feces",
    "fecal": "feces",
    "stool": "feces",
    "gut": "feces",
    "intestine": "feces",
    "intestinal": "feces",
    "colon": "colon",
    "colonic": "colon",
    "rectal": "rectum",
    "rectum": "rectum",
    "saliva": "saliva",
    "salivary": "saliva",
    "oral": "saliva",
    "mouth": "saliva",
    "dental": "saliva",
    "tongue": "tongue",
    "buccal": "cheek",
    "vagina": "vagina",
    "vaginal": "vagina",
    "cervical": "uterine cervix",
    "uterine": "uterus",
    "skin": "skin",
    "cutaneous": "skin",
    "dermal": "skin",
    "lung": "lung",
    "pulmonary": "lung",
    "bronchial": "bronchus",
    "nasal": "nasal cavity",
    "nasopharyngeal": "nasopharynx",
    "sputum": "lung",
    "blood": "blood",
    "serum": "blood",
    "plasma": "blood",
    "urine": "urine",
    "urinary": "urinary bladder",
    "bladder": "urinary bladder",
}

OLS_SEARCH_URL = "https://www.ebi.ac.uk/ols4/api/search"


def normalize_body_site(raw_text: str) -> Tuple[str, str]:
    """Return normalized body site and extraction status."""
    if not raw_text or raw_text.strip() == "":
        return "", "ABSENT"

    lowered = raw_text.lower()
    matched_sites = [value for key, value in BODY_SITE_LOOKUP.items() if key in lowered]
    unique_sites = list(dict.fromkeys(matched_sites))

    if len(unique_sites) == 1:
        return unique_sites[0], "PRESENT"
    if len(unique_sites) > 1:
        return unique_sites[0], "PARTIALLY_PRESENT"

    try:
        params = {
            "q": raw_text.strip(),
            "ontology": "uberon",
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
