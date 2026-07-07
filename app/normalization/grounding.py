"""Confidence-tier classification for ontology-mapped fields.

Inspired by metacurator's deterministic-first grounding discipline (see
docs/adr in metacurator-main): a mapping is only ever "auto"-applied when it
came from a static, curated lookup table; anything resolved via a live
external lookup (OLS/NCBI) or left ambiguous is downgraded to "review" so a
curator confirms it, and a bare miss is "none". This module classifies
NormalizedTerm results produced by host_species.py/body_site.py/condition.py
after the fact — it does not change how those modules resolve terms.
"""

from __future__ import annotations

from app.normalization.types import NormalizedTerm

TIER_AUTO = "auto"
TIER_REVIEW = "review"
TIER_NONE = "none"


def tier_for(term: NormalizedTerm) -> str:
    """Classify a NormalizedTerm's ontology mapping into auto/review/none.

    "auto" requires both a PRESENT status and mapping_confidence == 1.0,
    which today only static-dict exact matches produce (see
    SPECIES_LOOKUP/BODY_SITE_LOOKUP/CONDITION_LOOKUP) — live OLS/NCBI
    fallbacks and ambiguous multi-match cases cap confidence below 1.0.
    """
    if not term.ontology_id:
        return TIER_NONE
    if term.status == "PRESENT" and term.mapping_confidence >= 1.0:
        return TIER_AUTO
    return TIER_REVIEW
