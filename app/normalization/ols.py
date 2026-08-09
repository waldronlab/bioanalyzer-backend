"""OLS (Ontology Lookup Service) helpers for EFO and UBERON term resolution."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Optional, Tuple
from urllib.parse import quote

import requests

from app.normalization.ontology_cache import get_cached_term, store_cached_term

OLS_SEARCH_URL = "https://www.ebi.ac.uk/ols4/api/search"
OLS_TERMS_URL = "https://www.ebi.ac.uk/ols4/api/terms"
OLS_ANCESTORS_URL_TMPL = "https://www.ebi.ac.uk/ols4/api/ontologies/{ontology}/terms/{iri}/hierarchicalAncestors"


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
    recurs often and a confirmed mapping doesn't go stale.

    Validates that the returned term's own CURIE prefix actually matches
    *id_prefix* before accepting it - a real, live-observed gap found in
    the 2026-08-09 final maintainer sign-off pass: `format_ontology_id()`
    only ever uses *id_prefix* as a fallback default for a bare numeric
    obo_id with no embedded prefix - it does not validate a *real*
    embedded prefix against what the caller asked for. EBI OLS4's
    `ontology=` search parameter is a hint, not a hard filter, for fuzzy
    (`exact=false`) search - confirmed reproducible against the live API,
    not a hypothetical: `ols_search("sample", "uberon", "UBERON")`
    returned a real CHEBI term (`CHEBI:84087` "human urinary metabolite")
    formatted and cached as if it were a body-site-relevant result, purely
    because the query text happened to fuzzy-match a chemical entity
    better than any real UBERON term. Never reachable at "auto" tier
    either way (`mapping_confidence` here is always < 1.0), but a cross-
    ontology result is never a trustworthy answer for a field that only
    targets one ontology - rejecting it here means the caller's own
    further fallback (a different ontology, or the final untyped
    fallback) gets a chance instead of a confusing wrong-ontology
    "review" suggestion.
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
        if not label or not obo_id:
            return None
        if obo_id.split(":", 1)[0].upper() != id_prefix.upper():
            return None
        store_cached_term(ontology, query, label, obo_id, mapping_confidence)
        return label, obo_id, mapping_confidence
    except (requests.exceptions.RequestException, ValueError):
        return None


def _obo_iri(ontology_id: str) -> Optional[str]:
    """CURIE ('EFO:0000400') -> OBO Foundry PURL IRI, or None if malformed.

    All four ontologies this module deals with (EFO, MONDO, UBERON,
    NCBITaxon) publish OBO-compliant PURLs of this form, and OLS resolves
    terms by IRI regardless of which ontology originally minted the ID -
    this is the one IRI scheme that works for every prefix we handle.
    """
    if ":" not in ontology_id:
        return None
    prefix, local = ontology_id.split(":", 1)
    prefix, local = prefix.strip(), local.strip()
    if not prefix or not local:
        return None
    return f"http://purl.obolibrary.org/obo/{prefix}_{local}"


@dataclass(frozen=True)
class TermVerification:
    """Result of re-fetching an ontology_id directly from OLS by IRI (the
    "round-trip" step of the four-step grounding discipline - see
    app.normalization.grounding). ``exists=False`` means the ID doesn't
    resolve to anything at all, which is the strongest possible signal that
    a static-dict entry was fabricated or the ontology has since deleted it
    outright (as opposed to deprecating it, which ``is_obsolete`` covers)."""

    exists: bool
    label: str = ""
    is_obsolete: bool = False
    replaced_by: str = ""


def _extract_replaced_by(term: dict, default_prefix: str) -> str:
    """Best-effort extraction of an obsolete term's replacement ID.

    OLS has used a couple of different shapes for this across versions/
    ontologies (a top-level ``term_replaced_by`` string, or a
    ``replacedBy``/``replaced_by`` annotation list) - try the known ones and
    give up quietly rather than raise, consistent with the rest of this
    module's network-failure handling.
    """
    raw = term.get("term_replaced_by")
    if isinstance(raw, str) and raw.strip():
        return format_ontology_id(raw, default_prefix)
    annotation = term.get("annotation")
    if isinstance(annotation, dict):
        for key in ("replacedBy", "replaced_by", "term replaced by"):
            val = annotation.get(key)
            if isinstance(val, list) and val:
                val = val[0]
            if isinstance(val, str) and val.strip():
                return format_ontology_id(val, default_prefix)
    return ""


def fetch_term(
    ontology_id: str, default_prefix: str = ""
) -> Optional[TermVerification]:
    """Re-fetch *ontology_id* directly from OLS to confirm it still exists
    and check its obsolete status - the round-trip + obsolete-detection
    steps of the four-step grounding discipline.

    Returns None (not a ``TermVerification``) when the check itself
    couldn't be performed (network error, unexpected response shape) - the
    caller should treat that as "unable to verify", distinct from "verified
    and it doesn't exist" (``TermVerification(exists=False)``).
    """
    if not default_prefix and ":" in ontology_id:
        default_prefix = ontology_id.split(":", 1)[0]
    iri = _obo_iri(ontology_id)
    if not iri:
        return None
    try:
        response = requests.get(OLS_TERMS_URL, params={"iri": iri}, timeout=5)
        response.raise_for_status()
        terms = response.json().get("_embedded", {}).get("terms", [])
    except (requests.exceptions.RequestException, ValueError, KeyError, AttributeError):
        return None
    if not terms:
        return TermVerification(exists=False)
    term = terms[0]
    if not isinstance(term, dict):
        return None
    label = str(term.get("label") or "").strip()
    is_obsolete = bool(term.get("is_obsolete", False))
    replaced_by = _extract_replaced_by(term, default_prefix) if is_obsolete else ""
    return TermVerification(
        exists=True, label=label, is_obsolete=is_obsolete, replaced_by=replaced_by
    )


def is_in_branch(ontology_id: str, ontology: str, root_id: str) -> Optional[bool]:
    """Branch-check step: is *ontology_id* reachable from *root_id* via
    is_a/part_of ancestry within *ontology* (e.g. is this EFO term actually
    under the "disease" root, not some unrelated branch)?

    Returns True/False when the check completed, or None when it couldn't be
    performed (network error, unexpected response shape) - callers should
    treat None as "unverified", not "failed", the same convention as
    fetch_term().
    """
    if ontology_id == root_id:
        return True
    iri = _obo_iri(ontology_id)
    if not iri:
        return None
    default_prefix = ontology_id.split(":", 1)[0] if ":" in ontology_id else ""
    # OLS's path-segment IRI form requires double URL-encoding.
    encoded_iri = quote(quote(iri, safe=""), safe="")
    url = OLS_ANCESTORS_URL_TMPL.format(ontology=ontology, iri=encoded_iri)
    try:
        response = requests.get(url, timeout=5)
        if response.status_code == 404:
            return False
        response.raise_for_status()
        terms = response.json().get("_embedded", {}).get("terms", [])
    except (requests.exceptions.RequestException, ValueError, KeyError, AttributeError):
        return None
    ancestor_ids = set()
    for term in terms:
        if not isinstance(term, dict):
            continue
        obo_id = format_ontology_id(term.get("obo_id", ""), default_prefix)
        if obo_id:
            ancestor_ids.add(obo_id)
    return root_id in ancestor_ids
