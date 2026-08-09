"""Host species normalization aligned with NCBI Taxonomy (NCBITaxon IDs)."""

from __future__ import annotations

import os
import time
from typing import Dict, Tuple

import requests

from app.normalization.local_lookup import local_lookup
from app.normalization.ontology_cache import get_cached_term, store_cached_term
from app.normalization.types import LookupMatcher, NormalizedTerm

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


_MATCHER = LookupMatcher(SPECIES_LOOKUP)


def normalize_host_species(raw_text: str) -> NormalizedTerm:
    """Return normalized host species label, NCBITaxon ID, status, and mapping confidence."""
    if not raw_text or raw_text.strip() == "":
        return NormalizedTerm.absent()

    lowered = raw_text.lower()
    hit = _MATCHER.match_longest(lowered)
    if hit:
        matched_key, (label, tax_id) = hit
        # Real, severe false-AUTO bug found in a 2026-08-09 adversarial
        # review: candidate/ambiguity detection used to run *only* when a
        # literal "and"/"&"/"/"/"or" substring was present anywhere in the
        # text - so "Germ-free C57BL 6 mice were colonized with fecal
        # microbiota from IBD patients" (no such substring) matched
        # "patients" (8 chars, -> Homo sapiens) over "mice" (4 chars, the
        # actual study animal - "patients" here refers to the human FMT
        # donor, not the host species) via plain longest-match, with the
        # second, real candidate ("mice") never even computed - confidence
        # 1.0, "auto" tier, completely wrong species, zero indication
        # anything was ambiguous. Fixed by *always* checking for other real
        # distinct candidates (not gating that check behind an indicator-
        # substring heuristic, which also both missed cases without one of
        # those four substrings and falsely triggered on unrelated slashes
        # in strain names like "C57BL/6"/"BALB/c" even with zero real
        # ambiguity) - genuine ambiguity is now determined by whether a
        # second, real, distinct species match exists, not by incidental
        # punctuation.
        candidates = _MATCHER.candidates(lowered, matched_key, (label, tax_id))
        if candidates:
            return NormalizedTerm(
                label, tax_id, "PARTIALLY_PRESENT", 0.9, candidates=candidates
            )
        return NormalizedTerm(label, tax_id, "PRESENT", 1.0)

    # Nothing in the static dict matched. Before checking for compound-
    # text ambiguity indicators or falling to the live NCBI API: try the
    # local ontology store - real, complete NCBITaxon data (2026-08
    # adversarial review found this had no production caller at all; see
    # app.normalization.local_lookup's module docstring). Offline,
    # sub-millisecond even against NCBITaxon's 2.7M real terms, and covers
    # real species far beyond this module's ~31-entry static dict (a
    # single species name like "Acrocephalus sechellensis" - a real
    # BugSigDB-curated host species - has no chance of being in that
    # dict, but resolves instantly from the real synced data).
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
