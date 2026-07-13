"""Host species normalization aligned with NCBI Taxonomy (NCBITaxon IDs)."""

from __future__ import annotations

import os
import time
from typing import Dict, Tuple

import requests

from app.normalization.ontology_cache import get_cached_term, store_cached_term
from app.normalization.types import NormalizedTerm

# keyword -> (scientific name, NCBITaxon ID)
#
# All 8 distinct NCBITaxon IDs below were exhaustively checked against the
# live EBI OLS API on 2026-07-12 (see docs/PROJECT_AUDIT.md /
# ONTOLOGY_AUDIT.md) - every one resolves to the species claimed here.
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
    # Deliberately NOT mapped to Homo sapiens: "adult", "infant", "neonate"
    # (and plurals) are life-stage descriptors, not species-identifying -
    # they're used for animal cohorts just as often ("adult mice", "infant
    # rats", "neonate pigs"). Because _lookup_species() picks the longest
    # matching key, these (5-7 chars) used to outrank short animal nouns
    # like "mice"/"rat"/"pig" (3-4 chars), silently misclassifying animal
    # studies as human whenever both appeared in the same text.
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


def _lookup_species_candidates(
    lowered: str, exclude: Tuple[str, str] | None, limit: int = 2
) -> Tuple[Tuple[str, str], ...]:
    """Other distinct SPECIES_LOOKUP matches besides the winning one, for
    curators to choose from when the mapping isn't auto-applied. Doesn't
    affect which match wins (see _lookup_species's longest-match rule)."""
    found: list[Tuple[str, str]] = []
    for key, pair in SPECIES_LOOKUP.items():
        if key in lowered and pair != exclude and pair not in found:
            found.append(pair)
        if len(found) >= limit:
            break
    return tuple(found)


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
            candidates = _lookup_species_candidates(lowered, hit)
            return NormalizedTerm(
                label, tax_id, "PARTIALLY_PRESENT", 0.9, candidates=candidates
            )
        return NormalizedTerm(raw_text.strip(), "", "PARTIALLY_PRESENT", 0.5)

    hit = _lookup_species(lowered)
    if hit:
        label, tax_id = hit
        return NormalizedTerm(label, tax_id, "PRESENT", 1.0)

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
