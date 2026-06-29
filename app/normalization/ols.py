"""OLS (Ontology Lookup Service) helpers for EFO and UBERON term resolution."""

from __future__ import annotations

import re
from typing import Optional, Tuple

import requests

OLS_SEARCH_URL = "https://www.ebi.ac.uk/ols4/api/search"


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
    """Return (label, ontology_id, confidence) for the top OLS hit, or None."""
    if not query or not query.strip():
        return None
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
        return label, obo_id, mapping_confidence
    except (requests.exceptions.RequestException, ValueError):
        return None
