"""Host species normalization aligned with NCBI Taxonomy (NCBITaxon IDs)."""

from __future__ import annotations

import os
import time
from typing import Dict, Tuple

import requests

from app.normalization.types import NormalizedTerm

# keyword -> (scientific name, NCBITaxon ID)
SPECIES_LOOKUP: Dict[str, Tuple[str, str]] = {
    "human": ("Homo sapiens", "NCBITaxon:9606"),
    "humans": ("Homo sapiens", "NCBITaxon:9606"),
    "patient": ("Homo sapiens", "NCBITaxon:9606"),
    "patients": ("Homo sapiens", "NCBITaxon:9606"),
    "participant": ("Homo sapiens", "NCBITaxon:9606"),
    "participants": ("Homo sapiens", "NCBITaxon:9606"),
    "volunteer": ("Homo sapiens", "NCBITaxon:9606"),
    "volunteers": ("Homo sapiens", "NCBITaxon:9606"),
    "subject": ("Homo sapiens", "NCBITaxon:9606"),
    "subjects": ("Homo sapiens", "NCBITaxon:9606"),
    "infant": ("Homo sapiens", "NCBITaxon:9606"),
    "infants": ("Homo sapiens", "NCBITaxon:9606"),
    "children": ("Homo sapiens", "NCBITaxon:9606"),
    "neonate": ("Homo sapiens", "NCBITaxon:9606"),
    "neonates": ("Homo sapiens", "NCBITaxon:9606"),
    "adult": ("Homo sapiens", "NCBITaxon:9606"),
    "adults": ("Homo sapiens", "NCBITaxon:9606"),
    "homo sapiens": ("Homo sapiens", "NCBITaxon:9606"),
    "mouse": ("Mus musculus", "NCBITaxon:10090"),
    "mice": ("Mus musculus", "NCBITaxon:10090"),
    "mus musculus": ("Mus musculus", "NCBITaxon:10090"),
    "rat": ("Rattus norvegicus", "NCBITaxon:10116"),
    "rats": ("Rattus norvegicus", "NCBITaxon:10116"),
    "rattus norvegicus": ("Rattus norvegicus", "NCBITaxon:10116"),
    "zebrafish": ("Danio rerio", "NCBITaxon:7955"),
    "danio rerio": ("Danio rerio", "NCBITaxon:7955"),
    "pig": ("Sus scrofa", "NCBITaxon:9823"),
    "pigs": ("Sus scrofa", "NCBITaxon:9823"),
    "swine": ("Sus scrofa", "NCBITaxon:9823"),
    "sus scrofa": ("Sus scrofa", "NCBITaxon:9823"),
    "chicken": ("Gallus gallus", "NCBITaxon:9031"),
    "gallus gallus": ("Gallus gallus", "NCBITaxon:9031"),
    "rabbit": ("Oryctolagus cuniculus", "NCBITaxon:9986"),
    "rabbits": ("Oryctolagus cuniculus", "NCBITaxon:9986"),
    "dog": ("Canis lupus familiaris", "NCBITaxon:9615"),
    "dogs": ("Canis lupus familiaris", "NCBITaxon:9615"),
    "canine": ("Canis lupus familiaris", "NCBITaxon:9615"),
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
    time.sleep(0.11 if api_key else 0.34)


def _lookup_species(lowered: str) -> Tuple[str, str] | None:
    best_key = ""
    best: Tuple[str, str] | None = None
    for key, pair in SPECIES_LOOKUP.items():
        if key in lowered and len(key) > len(best_key):
            best_key = key
            best = pair
    return best


def normalize_host_species(raw_text: str) -> NormalizedTerm:
    """Return normalized host species label, NCBITaxon ID, status, and mapping confidence."""
    if not raw_text or raw_text.strip() == "":
        return NormalizedTerm.absent()

    lowered = raw_text.lower()
    multi_indicators = [" and ", " & ", "/", " or "]
    if any(ind in lowered for ind in multi_indicators):
        hit = _lookup_species(lowered)
        if hit:
            label, tax_id = hit
            return NormalizedTerm(label, tax_id, "PARTIALLY_PRESENT", 0.9)
        return NormalizedTerm(raw_text.strip(), "", "PARTIALLY_PRESENT", 0.5)

    hit = _lookup_species(lowered)
    if hit:
        label, tax_id = hit
        return NormalizedTerm(label, tax_id, "PRESENT", 1.0)

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
            record = summary_resp.json()["result"][ids[0]]
            sci_name = record.get("scientificname", "")
            tax_id = record.get("taxid", ids[0])
            if sci_name:
                return NormalizedTerm(
                    sci_name,
                    f"NCBITaxon:{tax_id}",
                    "PRESENT",
                    0.9,
                )
    except (requests.exceptions.RequestException, ValueError, KeyError):
        pass

    return NormalizedTerm(raw_text.strip(), "", "PARTIALLY_PRESENT", 0.5)
