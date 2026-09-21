"""Local-ontology-store candidate generation - shared by
host_species.py/body_site.py/condition.py as a fallback between the static
lookup dicts and each module's live-network fallback (NCBI Taxonomy / EBI
OLS).

Why this exists: a 2026-08 adversarial review found that
`app.normalization.grounding.backend.GroundingBackend.lookup()` - real,
tested, offline, and backed by the complete local ontology store (2.8M+
real terms across EFO/MONDO/UBERON/NCBITaxon/DOID/HP/CHEBI/NCIT/MESH/ENVO,
see docs/GROUNDING_ARCHITECTURE.md) - had **zero production callers**.
Candidate generation was 100% the ~110-entry static dicts; anything not in
them fell straight to a live network call, even though the local store
already had real, complete, indexed, sub-millisecond-latency data for the
overwhelming majority of real biomedical terms. This module is what closes
that gap: it's tried after a static-dict miss and before the live-network
fallback, so most previously-network-dependent lookups now resolve
instantly, deterministically, and offline instead.

**Hard rule, not a suggestion: this can never produce an "auto" mapping.**
`local_lookup()`'s result is always `mapping_confidence <= 0.9` regardless
of match quality (even a perfect exact-label match) - "auto" tier stays
reserved for the small, hand-curated, individually-audited static dicts
(see tiering.py's module docstring for why that boundary matters: it's
what keeps the blast radius of any single grounding bug bounded to ~110
entries instead of millions). A real, distinct second candidate found
during ranking downgrades further to "review" with `candidates` populated,
never silently picked - the same ambiguity-preservation rule
`host_species.py`'s 2026-08-09 fix established for the static-dict path.

Ranking reuses `rank_candidates_explained()` (scope + edit-distance +
branch-validity, see backend.py) rather than picking the first `lookup()`
result arbitrarily - this is also that function's first real production
caller.
"""

from __future__ import annotations

from typing import Optional, Sequence, Tuple

from app.normalization.grounding.backend import (
    SCOPE_BROAD,
    SCOPE_EXACT,
    SCOPE_NARROW,
    SCOPE_RELATED,
    rank_candidates_explained,
)
from app.normalization.grounding.local_backend import LocalOntologyBackend
from app.normalization.types import NormalizedTerm

_ALL_SCOPES = (SCOPE_EXACT, SCOPE_BROAD, SCOPE_NARROW, SCOPE_RELATED)

_backend: Optional[LocalOntologyBackend] = None


def _get_backend() -> LocalOntologyBackend:
    global _backend
    if _backend is None:
        _backend = LocalOntologyBackend()
    return _backend


def local_lookup(query: str, ontology_slugs: Sequence[str]) -> Optional[NormalizedTerm]:
    """Try *query* against the local ontology store for each slug in
    *ontology_slugs*, in order (first ontology with any real match wins -
    same "try EFO then MONDO" precedence condition.py's live fallback
    already uses). Returns None if no ontology in the list has any match,
    so the caller can fall through to its own live-network fallback.

    Deterministic and offline: `LocalOntologyBackend.lookup()` is an
    indexed equality lookup against normalized label/synonym columns (see
    local_backend.py's module docstring) - no full-table scan, no network
    call, sub-millisecond even against NCBITaxon's 2.7M real terms.
    """
    normalized_query = query.strip() if query else ""
    if not normalized_query:
        return None

    backend = _get_backend()
    for slug in ontology_slugs:
        results = backend.lookup(normalized_query, slug, scopes=_ALL_SCOPES)
        if not results:
            continue

        ranked = rank_candidates_explained(
            results, query=normalized_query, backend=backend
        )
        winner = ranked[0]
        confidence = min(winner.confidence, 0.9)

        other_candidates: list[Tuple[str, str]] = []
        seen_curies = {winner.term.curie}
        for rc in ranked[1:]:
            if rc.term.curie in seen_curies:
                continue
            other_candidates.append((rc.term.label, rc.term.curie))
            seen_curies.add(rc.term.curie)
            if len(other_candidates) >= 2:
                break

        if other_candidates:
            return NormalizedTerm(
                winner.term.label,
                winner.term.curie,
                "PARTIALLY_PRESENT",
                confidence,
                candidates=tuple(other_candidates),
            )
        return NormalizedTerm(
            winner.term.label, winner.term.curie, "PRESENT", confidence
        )
    return None
