"""Shared cache accessor for ontology term -> ID lookups.

Wraps CacheManager's ontology_term_cache table (NCBI Taxonomy, EBI OLS) so
host_species.py / body_site.py / condition.py don't each re-implement the
lazy-singleton + error-swallowing boilerplate. Caching is a performance
optimization only: any failure here degrades to "no cache" rather than
raising, so a sqlite hiccup never breaks an ontology lookup.
"""

from __future__ import annotations

import os
from typing import Any, Dict, Optional, Tuple

_cache_manager = None

GROUNDING_CACHE_VALIDITY_HOURS = int(os.getenv("GROUNDING_CACHE_VALIDITY_HOURS", "720"))


def _get_cache_manager():
    global _cache_manager
    if _cache_manager is None:
        from app.services.cache_manager import CacheManager

        _cache_manager = CacheManager()
    return _cache_manager


def get_cached_term(provider: str, term: str) -> Optional[Tuple[str, str, float]]:
    """Return a cached (label, ontology_id, confidence) for *term*, or None."""
    if not term:
        return None
    try:
        return _get_cache_manager().get_ontology_term(provider, term.strip().lower())
    except Exception:
        return None


def store_cached_term(
    provider: str, term: str, label: str, ontology_id: str, confidence: float
) -> None:
    """Persist a resolved mapping for *term*. Best-effort; never raises."""
    if not term:
        return
    try:
        _get_cache_manager().store_ontology_term(
            provider, term.strip().lower(), label, ontology_id, confidence
        )
    except Exception:
        pass


def get_cached_grounding(ontology_id: str) -> Optional[Dict[str, Any]]:
    """Return a cached grounding check for *ontology_id*, or None if absent/expired."""
    if not ontology_id:
        return None
    try:
        return _get_cache_manager().get_grounding_check(
            ontology_id, GROUNDING_CACHE_VALIDITY_HOURS
        )
    except Exception:
        return None


def store_cached_grounding(
    ontology_id: str,
    term_exists: bool,
    label: str,
    is_obsolete: bool,
    replaced_by: str,
    branch_ok: Optional[bool],
    root_id: str,
) -> None:
    """Persist a resolved grounding check for *ontology_id*. Best-effort; never raises."""
    if not ontology_id:
        return
    try:
        _get_cache_manager().store_grounding_check(
            ontology_id,
            term_exists,
            label,
            is_obsolete,
            replaced_by,
            branch_ok,
            root_id,
        )
    except Exception:
        pass
