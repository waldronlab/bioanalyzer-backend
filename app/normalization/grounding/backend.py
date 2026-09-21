"""The `GroundingBackend` protocol and the value objects every backend speaks.

BioAnalyzer's ontology-grounding requirement: a
backend answers exactly four questions about a CURIE within an ontology -
does it exist (round-trip), is it reachable from a declared root (branch
check), is it obsolete, and what's it a synonym/label match for (lookup).
`app.normalization.grounding.tiering` orchestrates the four-step discipline
against whichever backend it's given; it never talks to a backend's
underlying storage/transport directly, so a new backend (a different live
API, a different local store, eventually a vector-search index) is a new
class implementing this Protocol, not a change to the orchestration logic.
"""

from __future__ import annotations

import difflib
from dataclasses import dataclass, field
from typing import List, Optional, Protocol, Tuple, runtime_checkable

SCOPE_EXACT = "exact"
SCOPE_BROAD = "broad"
SCOPE_NARROW = "narrow"
SCOPE_RELATED = "related"

_SCOPE_RANK = {SCOPE_EXACT: 0, SCOPE_BROAD: 1, SCOPE_NARROW: 2, SCOPE_RELATED: 3}


@dataclass(frozen=True)
class GroundedTerm:
    """One candidate mapping of a free-text value to an ontology term.

    `scope` records *how* the value matched (exact label, exact synonym,
    broader/narrower/related synonym) - this is what candidate ranking and
    confidence-tier assignment key off, not just "did it match at all".
    `source` and `ontology_version` make the candidate's provenance
    explainable (which backend answered, against which ontology snapshot)
    without requiring a caller to already know which backend was asked.
    """

    curie: str
    label: str
    ontology: str
    scope: str = SCOPE_EXACT
    source: str = ""
    ontology_version: str = ""


@dataclass(frozen=True)
class GroundingCheck:
    """Result of running the round-trip + branch + obsolete steps against a
    single CURIE. This is the backend-agnostic replacement for
    `app.normalization.ols.TermVerification` plus the branch-check bool that
    `app.normalization.grounding` (old, single-file version) tracked
    separately - unified here so every backend returns one shape.

    ``exists=False`` is the strongest possible signal of a fabricated or
    since-deleted identifier. ``branch_ok=None`` means the branch check
    wasn't attempted (e.g. because the term doesn't exist, or no root is
    configured for this ontology) - distinct from ``False`` ("attempted and
    failed"), the same convention the original implementation used.
    """

    exists: bool
    label: str = ""
    is_obsolete: bool = False
    replaced_by: str = ""
    branch_ok: Optional[bool] = None
    checked_root: str = ""
    source: str = ""


@dataclass(frozen=True)
class GroundingDecision:
    """The full explainable trace behind a tier assignment - *why*, not just
    *what*. `tiering.tier_for()` (the unchanged public function 2 call sites
    depend on) only ever returns `.tier`; this richer object is what backs
    it internally and is available to anything that calls `ground()`
    directly (e.g. future curator-facing debug tooling), without touching
    the FieldResult/curator-desk CSV contract, which is unchanged."""

    tier: str
    reason: str
    check: Optional[GroundingCheck] = None
    candidates: Tuple[GroundedTerm, ...] = field(default_factory=tuple)


@runtime_checkable
class GroundingBackend(Protocol):
    """What a grounding backend must answer. Implementations: `OLSBackend`
    (live EBI OLS4 REST), `LocalOntologyBackend` (local SQLite/DuckDB store),
    `ChainedBackend` (composes several). None of these inherit from a shared
    base class - Protocol gives structural typing (duck typing checked by
    mypy/runtime_checkable) without an inheritance hierarchy to maintain."""

    def lookup(
        self, value: str, ontology: str, *, scopes: Tuple[str, ...] = (SCOPE_EXACT,)
    ) -> List[GroundedTerm]:
        """Free-text value -> candidate terms in *ontology*, restricted to
        the given synonym scopes. Empty list, never raises, on no match."""
        ...

    def get(self, curie: str, ontology: str) -> Optional[GroundingCheck]:
        """Round-trip: re-fetch *curie* and confirm it still resolves.
        Returns None (not a GroundingCheck) when the check itself couldn't
        be performed - callers must treat that as "unable to verify",
        distinct from a completed check reporting ``exists=False``."""
        ...

    def reachable_from(self, curie: str, root: str, ontology: str) -> Optional[bool]:
        """Branch check: is *curie* reachable from *root* via is_a/part_of
        ancestry? None when the check couldn't be performed (unverified,
        not failed) - same fail-open convention as `get()`."""
        ...


def rank_candidates(candidates: List[GroundedTerm]) -> List[GroundedTerm]:
    """Order candidates by match specificity (exact > broad > narrow >
    related) - the precedence used to decide which
    candidate(s) are even eligible for "auto" tier. Stable sort - candidates
    with the same scope keep whatever order the backend returned them in.

    Backward-compatible: no query text, no scoring, just the scope
    precedence this function has always provided. See
    `rank_candidates_explained()` for the richer, scored/explained version
    (multiple evidence sources, deterministic, calibrated confidence) added
    in the 2026-08 production-readiness pass - kept as a separate function
    rather than an overload so a caller that only wants "put these in order"
    isn't forced to reason about a RankedCandidate wrapper type."""
    return sorted(candidates, key=lambda c: _SCOPE_RANK.get(c.scope, 99))


_SCOPE_WEIGHT = {
    SCOPE_EXACT: 1.0,
    SCOPE_BROAD: 0.75,
    SCOPE_NARROW: 0.6,
    SCOPE_RELATED: 0.4,
}


@dataclass(frozen=True)
class RankedCandidate:
    """A GroundedTerm plus its computed rank, similarity score, calibrated
    confidence, and a plain-language reason - "explainable candidate
    ranking": a caller (or a curator-facing UI) can see *why* one candidate
    outranked another, not just the final order."""

    term: GroundedTerm
    similarity: float  # 0-1, edit-distance-based closeness to the query text
    confidence: float  # 0-1, scope-weighted and similarity-refined
    explanation: str


def _root_for_ols_slug(ols_slug: str) -> str:
    """Reverse-lookup: ontology slug (e.g. "efo") -> its declared branch
    root curie, from the same `ROOTS`/`EXTENDED_ONTOLOGY_ROOTS` tables
    `tiering.py`'s four-step discipline uses. Imported lazily (not at
    module top-level) to avoid a circular import - `roots.py` doesn't
    depend on this module, but keeping the import inside the function
    keeps this module's own import graph independent of `roots.py`'s
    existence, the same reasoning `tiering.py` uses for its own lazy
    `local_backend` import."""
    from app.normalization.grounding.roots import EXTENDED_ONTOLOGY_ROOTS, ROOTS

    for _prefix, (slug, root_id) in {**ROOTS, **EXTENDED_ONTOLOGY_ROOTS}.items():
        if slug == ols_slug:
            return root_id
    return ""


def rank_candidates_explained(
    candidates: List[GroundedTerm],
    *,
    query: str = "",
    backend: Optional[GroundingBackend] = None,
) -> List[RankedCandidate]:
    """Rank *candidates* using deterministic evidence sources:

    1. **Scope** (exact label/synonym > broad > narrow > related) - the
       primary signal, same precedence as `rank_candidates()`.
    2. **Edit distance** (`difflib.SequenceMatcher`, stdlib, no new
       dependency) between *query* and each candidate's label, when *query*
       is given - refines ordering *within* a scope tier (e.g. two exact-
       scope candidates, one an exact string match and one that only
       matched after normalization stripped punctuation, are no longer
       arbitrarily ordered).
    3. **Branch validity** (ontology graph structure/ancestor relationship),
       when *backend* is given: a candidate reachable from its ontology's
       declared root (`roots.ROOTS`/`EXTENDED_ONTOLOGY_ROOTS`) gets a
       confidence bonus; a candidate that round-trips but resolves *outside*
       its declared root - a real, observed case, e.g. an NCBITaxon hit
       under Bacteria when the field wants Eukaryota-rooted host species -
       gets a penalty, since that's a strong signal the match is technically
       real but semantically the wrong sense of the term. `branch_ok is
       None` (unverified/no root configured) leaves confidence unchanged -
       consistent with this whole subsystem's fail-open convention. This
       was previously a documented, honest gap ("branch validation is a
       separate check already gating tier, not folded into ranking score")
       left out specifically because a per-candidate branch check was too
       slow to run during ranking before the 2026-08-09 BFS rewrite fixed
       `reachable_from()`'s NCBITaxon performance (12s -> <1ms per call,
       see docs/GROUNDING_ARCHITECTURE.md) - now cheap enough to use here.

    Deliberately not implemented, with reasons: embedding/semantic
    similarity (would need a model - `sentence-transformers` is already a
    project dependency for the RAG pipeline, so technically available, but
    adds real latency and a non-auditable score to what is otherwise a
    fully inspectable, one-sentence-per-signal formula; this codebase has
    twice already explicitly declined speculative ontology-matching
    complexity beyond what a concrete need justifies - see
    docs/ONTOLOGY_AUDIT.md's "Scope decision" section - and no case in this
    codebase's real static-dict/local-store data has yet needed more than
    scope+edit-distance+branch-validity to disambiguate). A learned/fitted
    calibration curve is not implemented either - "deterministic and
    explainable" rules out anything that isn't a plain formula stated in
    this docstring; empirical calibration is validated instead via
    `scripts/eval/grounding_benchmark.py` (does "auto"-tier confidence
    actually track real correctness on known-good/known-bad cases), not by
    fitting a model.
    """
    ranked: List[RankedCandidate] = []
    normalized_query = query.strip().casefold() if query else ""
    for term in candidates:
        similarity = (
            difflib.SequenceMatcher(
                None, normalized_query, term.label.strip().casefold()
            ).ratio()
            if normalized_query
            else 1.0
        )
        scope_weight = _SCOPE_WEIGHT.get(term.scope, 0.2)
        raw_confidence = scope_weight * (0.5 + 0.5 * similarity)
        explanation = f"{term.scope} match on label {term.label!r} in {term.ontology}"
        if normalized_query:
            explanation += f" ({similarity:.0%} textual similarity to query {query!r})"

        if backend is not None:
            root_id = _root_for_ols_slug(term.ontology)
            if root_id and term.curie != root_id:
                branch_ok = backend.reachable_from(term.curie, root_id, term.ontology)
                if branch_ok is True:
                    raw_confidence = min(1.0, raw_confidence + 0.1)
                    explanation += f"; confirmed reachable from root {root_id}"
                elif branch_ok is False:
                    raw_confidence = max(0.0, raw_confidence - 0.3)
                    explanation += (
                        f"; NOT reachable from root {root_id} - likely the "
                        "wrong sense of this term"
                    )

            get_xrefs = getattr(backend, "get_xrefs", None)
            if get_xrefs is not None:
                try:
                    xrefs = get_xrefs(term.ontology, term.curie)
                except Exception:  # local-store-only op; never fail ranking over it
                    xrefs = []
                if xrefs:
                    shown = ", ".join(xrefs[:3])
                    more = f" (+{len(xrefs) - 3} more)" if len(xrefs) > 3 else ""
                    explanation += f"; cross-references on file: {shown}{more}"

        ranked.append(
            RankedCandidate(
                term=term,
                similarity=round(similarity, 4),
                confidence=round(raw_confidence, 4),
                explanation=explanation,
            )
        )
    ranked.sort(key=lambda rc: (_SCOPE_RANK.get(rc.term.scope, 99), -rc.confidence))
    return ranked
