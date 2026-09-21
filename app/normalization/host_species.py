"""Host species normalization aligned with NCBI Taxonomy (NCBITaxon IDs)."""

from __future__ import annotations

import os
import time
from typing import Dict, Tuple

import requests

from app.normalization.local_lookup import local_lookup
from app.normalization.ontology_cache import get_cached_term, store_cached_term
from app.normalization.types import LookupMatcher, NormalizedTerm, is_null_like

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
    "children": ("Homo sapiens", "NCBITaxon:9606"),
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


_MATCHER = LookupMatcher(SPECIES_LOOKUP)


def normalize_host_species(raw_text: str) -> NormalizedTerm:
    """Return normalized host species label, NCBITaxon ID, status, and mapping confidence."""
    if is_null_like(raw_text):
        return NormalizedTerm.absent()

    lowered = raw_text.lower()
    hit = _MATCHER.match_longest(lowered)
    if hit:
        matched_key, (label, tax_id) = hit
        candidates = _MATCHER.candidates(lowered, matched_key, (label, tax_id))
        if candidates:
            return NormalizedTerm(
                label, tax_id, "PARTIALLY_PRESENT", 0.9, candidates=candidates
            )
        return NormalizedTerm(label, tax_id, "PRESENT", 1.0)

    local_hit = local_lookup(raw_text.strip(), ("ncbitaxon",))
    if local_hit:
        return local_hit

    multi_indicators = [" and ", " & ", "/", " or "]
    if any(ind in lowered for ind in multi_indicators):
        return NormalizedTerm(raw_text.strip(), "", "PARTIALLY_PRESENT", 0.5)

    cached = get_cached_term("ncbitaxon", raw_text)
    if cached is not None:
        label, tax_id, conf = cached
        return NormalizedTerm(label, tax_id, "PRESENT", conf)

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
                ncbi_id = f"NCBITaxon:{tax_id}"
                store_cached_term("ncbitaxon", raw_text, sci_name, ncbi_id, 0.9)
                return NormalizedTerm(
                    sci_name,
                    ncbi_id,
                    "PRESENT",
                    0.9,
                )
    except (requests.exceptions.RequestException, ValueError, KeyError):
        pass

    return NormalizedTerm(raw_text.strip(), "", "PARTIALLY_PRESENT", 0.5)
