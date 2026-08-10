"""Composes multiple GroundingBackends into one - composition, not a shared
base class with backend-specific subclass overrides.

Tries each backend in order for a given call, returning the first answer
that isn't "unable to verify" (`None`); if every backend is inconclusive,
returns `None` itself so the caller's own fail-open handling applies.
Default composition for the redesigned system: local store first (instant,
deterministic, offline), live OLS second (broader coverage, catches
anything the local seed doesn't have yet) - cheapest and most reproducible
answer wins when it can answer at all.
"""

from __future__ import annotations

from typing import List, Optional, Tuple

from app.normalization.grounding.backend import (
    SCOPE_EXACT,
    GroundedTerm,
    GroundingCheck,
    rank_candidates_explained,
)


class ChainedBackend:
    def __init__(self, backends: List, *, name: str = "chain"):
        if not backends:
            raise ValueError("ChainedBackend needs at least one backend")
        self._backends = backends
        self.name = name

    def lookup(
        self, value: str, ontology: str, *, scopes: Tuple[str, ...] = (SCOPE_EXACT,)
    ) -> List[GroundedTerm]:
        """Unlike get()/reachable_from(), lookup results are merged (not
        first-wins) - different backends can legitimately hold different
        parts of the same ontology (e.g. seed data vs. a fuller import), and
        a caller wants every real candidate, not just the first backend's.
        The merged list is ranked (scope, then edit-distance to *value*,
        then branch validity against each candidate's declared ontology
        root - see `backend.rank_candidates_explained()`) before returning,
        so "which candidate answered first" (an accident of backend order)
        never determines result order - a candidate from a later backend
        that's a better match still sorts first. Passes `self` as the
        ranking function's branch-check backend, so the per-candidate
        `reachable_from()` calls it makes go through this same chain
        (local store first, live OLS fallback) rather than needing their
        own separate backend selection."""
        merged: List[GroundedTerm] = []
        seen_curies: set = set()
        for backend in self._backends:
            for term in backend.lookup(value, ontology, scopes=scopes):
                if term.curie not in seen_curies:
                    merged.append(term)
                    seen_curies.add(term.curie)
        return [
            rc.term
            for rc in rank_candidates_explained(merged, query=value, backend=self)
        ]

    def get(self, curie: str, ontology: str) -> Optional[GroundingCheck]:
        for backend in self._backends:
            result = backend.get(curie, ontology)
            if result is not None:
                return result
        return None

    def reachable_from(self, curie: str, root: str, ontology: str) -> Optional[bool]:
        for backend in self._backends:
            result = backend.reachable_from(curie, root, ontology)
            if result is not None:
                return result
        return None

    def get_xrefs(self, ontology: str, curie: str) -> List[str]:
        """Not part of the `GroundingBackend` Protocol - an optional,
        duck-typed capability only `LocalOntologyBackend` (and this
        passthrough) implement, since live OLS has no equivalent bulk-xref
        endpoint this codebase calls. `rank_candidates_explained()` checks
        for this via `getattr(..., "get_xrefs", None)` rather than requiring
        it, so a plain `OLSBackend` (no xrefs) still ranks correctly."""
        merged: List[str] = []
        for backend in self._backends:
            get_xrefs = getattr(backend, "get_xrefs", None)
            if get_xrefs is not None:
                for xref in get_xrefs(ontology, curie):
                    if xref not in merged:
                        merged.append(xref)
        return merged
