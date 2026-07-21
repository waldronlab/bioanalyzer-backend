"""OLS (Ontology Lookup Service) helpers for EFO and UBERON term resolution."""

from __future__ import annotations

import logging
import re
from typing import Optional, Tuple

import requests

from app.normalization.ontology_cache import get_cached_term, store_cached_term

logger = logging.getLogger(__name__)

OLS_SEARCH_URL = "https://www.ebi.ac.uk/ols4/api/search"
OLS_TERMS_URL = "https://www.ebi.ac.uk/ols4/api/terms"
PURL_BASE = "http://purl.obolibrary.org/obo"


def format_ontology_id(obo_id: str, default_prefix: str) -> str:
    """Convert OLS obo_id (e.g. EFO_0002508) to BugSigDB style (EFO:0002508)."""
    if not obo_id or not str(obo_id).strip():
        return ""
    raw = str(obo_id).strip()
    if raw.startswith("http"):
        # http://purl.obolibrary.org/obo/EFO_0002508
        m = re.search(r"/([^/]+)$", raw)
        raw = m.group(1) if m else raw
    if ":" in raw and "_" not in raw.split(":", 1)[-1]:
        return raw
    if "_" in raw:
        prefix, rest = raw.split("_", 1)
        numeric = rest.replace("_", "")
        return f"{prefix}:{numeric}"
    return f"{default_prefix}:{raw}"


def _curie_to_purl(curie: str) -> Optional[str]:
    """``EFO:0002508`` -> ``http://purl.obolibrary.org/obo/EFO_0002508``."""
    if ":" not in curie:
        return None
    prefix, numeric = curie.split(":", 1)
    if not prefix or not numeric:
        return None
    return f"{PURL_BASE}/{prefix}_{numeric}"


def _is_obsolete(curie: str) -> Optional[bool]:
    """Round-trip a CURIE against OLS and report whether it's obsolete.

    This is the "no-hallucination" check adopted from metacurator (see
    docs/METACURATOR_METAHARMONIZER_ANALYSIS.md): a search hit alone doesn't
    confirm a term is still current, only that it matched a query. Returns
    True/False when a real answer came back, or None when the round-trip
    itself couldn't be completed (network error, malformed response) - in
    that case the caller falls back to trusting the original search result
    rather than rejecting a possibly-fine term over a transient failure.
    """
    iri = _curie_to_purl(curie)
    if iri is None:
        return None
    try:
        response = requests.get(OLS_TERMS_URL, params={"iri": iri}, timeout=5)
        response.raise_for_status()
        terms = response.json().get("_embedded", {}).get("terms", [])
        if not terms:
            return None
        # Obsolete only if EVERY returned entry for this IRI says so - a term
        # can appear under multiple ontology views, and one stale view
        # marking it obsolete shouldn't override another confirming it live.
        return all(bool(t.get("is_obsolete")) for t in terms)
    except (requests.exceptions.RequestException, ValueError, KeyError):
        return None


def ols_search(
    query: str,
    ontology: str,
    id_prefix: str,
    *,
    mapping_confidence: float = 0.9,
) -> Optional[Tuple[str, str, float]]:
    """Return (label, ontology_id, confidence) for the top OLS hit, or None.

    Successful resolutions are cached by (ontology, term) — see
    app.normalization.ontology_cache — since the same disease/body-site term
    recurs often and a confirmed mapping doesn't go stale. A resolution is
    only cached (and returned) after confirming, via a second round-trip
    lookup, that it isn't obsolete - a search hit alone isn't proof the term
    is still current.
    """
    if not query or not query.strip():
        return None

    cached = get_cached_term(ontology, query)
    if cached is not None:
        return cached

    try:
        params = {
            "q": query.strip(),
            "ontology": ontology,
            "fieldList": "label,obo_id",
            "rows": 1,
            "exact": "false",
        }
        response = requests.get(OLS_SEARCH_URL, params=params, timeout=5)
        response.raise_for_status()
        docs = response.json().get("response", {}).get("docs", [])
        if not docs:
            return None
        label = (docs[0].get("label") or "").strip()
        obo_id = format_ontology_id(docs[0].get("obo_id", ""), id_prefix)
        if not label:
            return None

        obsolete = _is_obsolete(obo_id)
        if obsolete:
            logger.info(
                "ols_search: rejecting obsolete term %s (%s) for query %r",
                obo_id,
                label,
                query,
            )
            return None

        store_cached_term(ontology, query, label, obo_id, mapping_confidence)
        return label, obo_id, mapping_confidence
    except (requests.exceptions.RequestException, ValueError):
        return None
