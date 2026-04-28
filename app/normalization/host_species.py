"""Host species normalization aligned with NCBI Taxonomy labels."""

from __future__ import annotations

import os
import time
from typing import Tuple

import requests

SPECIES_LOOKUP = {
    "human": "Homo sapiens",
    "humans": "Homo sapiens",
    "patient": "Homo sapiens",
    "patients": "Homo sapiens",
    "participant": "Homo sapiens",
    "participants": "Homo sapiens",
    "volunteer": "Homo sapiens",
    "volunteers": "Homo sapiens",
    "subject": "Homo sapiens",
    "subjects": "Homo sapiens",
    "infant": "Homo sapiens",
    "infants": "Homo sapiens",
    "children": "Homo sapiens",
    "neonate": "Homo sapiens",
    "neonates": "Homo sapiens",
    "adult": "Homo sapiens",
    "adults": "Homo sapiens",
    "homo sapiens": "Homo sapiens",
    "mouse": "Mus musculus",
    "mice": "Mus musculus",
    "mus musculus": "Mus musculus",
    "rat": "Rattus norvegicus",
    "rats": "Rattus norvegicus",
    "rattus norvegicus": "Rattus norvegicus",
    "zebrafish": "Danio rerio",
    "danio rerio": "Danio rerio",
    "pig": "Sus scrofa",
    "pigs": "Sus scrofa",
    "swine": "Sus scrofa",
    "sus scrofa": "Sus scrofa",
    "chicken": "Gallus gallus",
    "gallus gallus": "Gallus gallus",
    "rabbit": "Oryctolagus cuniculus",
    "rabbits": "Oryctolagus cuniculus",
    "dog": "Canis lupus familiaris",
    "dogs": "Canis lupus familiaris",
    "canine": "Canis lupus familiaris",
}

NCBI_TAX_SEARCH_URL = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi"
NCBI_TAX_SUMMARY_URL = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esummary.fcgi"


def _with_api_key(params: dict) -> dict:
    api_key = os.getenv("NCBI_API_KEY", "").strip()
    if api_key:
        params["api_key"] = api_key
    return params


def _rate_limit_delay() -> None:
    api_key = os.getenv("NCBI_API_KEY", "").strip()
    # NCBI permits up to 3 req/s without key, up to 10 req/s with key.
    time.sleep(0.11 if api_key else 0.34)


def normalize_host_species(raw_text: str) -> Tuple[str, str]:
    """Return normalized host species and extraction status."""
    if not raw_text or raw_text.strip() == "":
        return "", "ABSENT"

    lowered = raw_text.lower()
    multi_indicators = [" and ", " & ", "/", " or "]
    if any(ind in lowered for ind in multi_indicators):
        for key, value in SPECIES_LOOKUP.items():
            if key in lowered:
                return value, "PARTIALLY_PRESENT"
        return raw_text.strip(), "PARTIALLY_PRESENT"

    for key, value in SPECIES_LOOKUP.items():
        if key in lowered:
            return value, "PRESENT"

    try:
        search_params = _with_api_key(
            {
                "db": "taxonomy",
                "term": raw_text.strip(),
                "retmode": "json",
                "retmax": 1,
            }
        )
        search_resp = requests.get(NCBI_TAX_SEARCH_URL, params=search_params, timeout=5)
        search_resp.raise_for_status()
        ids = search_resp.json().get("esearchresult", {}).get("idlist", [])
        _rate_limit_delay()
        if ids:
            summary_params = _with_api_key(
                {"db": "taxonomy", "id": ids[0], "retmode": "json"}
            )
            summary_resp = requests.get(
                NCBI_TAX_SUMMARY_URL, params=summary_params, timeout=5
            )
            summary_resp.raise_for_status()
            sci_name = summary_resp.json()["result"][ids[0]].get("scientificname", "")
            if sci_name:
                return sci_name, "PRESENT"
    except Exception:
        pass

    return raw_text.strip(), "PARTIALLY_PRESENT"
