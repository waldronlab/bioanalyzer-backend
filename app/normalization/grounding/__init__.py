"""Ontology-grounding subsystem: classifies a NormalizedTerm's ontology
mapping into auto/review/none by running metacurator's four-step grounding
discipline (lookup -> round-trip -> branch check -> obsolete check) against
a pluggable `GroundingBackend`.

Public surface (unchanged from the pre-package single-file `grounding.py` -
this package IS the module as far as any importer is concerned):

    from app.normalization.grounding import tier_for, TIER_AUTO, TIER_REVIEW, TIER_NONE

New, additive surface for callers that want the richer architecture:

    from app.normalization.grounding import (
        ground, GroundingDecision, GroundingCheck, GroundedTerm,
        GroundingBackend, OLSBackend, LocalOntologyBackend, ChainedBackend,
        ROOTS,
    )

Submodules, each independently testable:
    backend.py       - the GroundingBackend Protocol + value objects (GroundedTerm,
                        GroundingCheck, GroundingDecision) + rank_candidates()
    ols_backend.py    - OLSBackend: thin adapter over app.normalization.ols (live EBI OLS4)
    local_backend.py  - LocalOntologyBackend: offline SQLite/DuckDB-backed store
    seed.py           - populates a LocalOntologyBackend from BioAnalyzer's verified
                        static lookup dicts, plus a real (unexercised-here) semantic-sql
                        ontology-dump fetcher for full-ontology coverage
    chain.py          - ChainedBackend: composes several backends
    roots.py          - ROOTS: schema-declared branch root per ontology
    tiering.py        - tier_for()/ground(): the orchestration itself

`get_cached_grounding`/`store_cached_grounding` re-exported here (not
changed - still `app.normalization.ontology_cache`'s functions) because
`tiering.py` looks them up through this package's namespace at call time
(`import app.normalization.grounding as _pkg; _pkg.get_cached_grounding(...)`)
rather than importing them directly, so tests can monkeypatch
`app.normalization.grounding.get_cached_grounding` and have it take effect -
the same "_pkg self-import" pattern app.services.bugsigdb_analyzer uses, for
the identical reason (see that package's docstring).
"""

from __future__ import annotations

from app.normalization.ontology_cache import (
    get_cached_grounding,
    store_cached_grounding,
)

from app.normalization.grounding.backend import (
    SCOPE_BROAD,
    SCOPE_EXACT,
    SCOPE_NARROW,
    SCOPE_RELATED,
    GroundedTerm,
    GroundingBackend,
    GroundingCheck,
    GroundingDecision,
    rank_candidates,
)
from app.normalization.grounding.chain import ChainedBackend
from app.normalization.grounding.local_backend import LocalOntologyBackend
from app.normalization.grounding.ols_backend import OLSBackend
from app.normalization.grounding.roots import ROOTS
from app.normalization.grounding.tiering import (
    TIER_AUTO,
    TIER_NONE,
    TIER_REVIEW,
    ground,
    tier_for,
)

__all__ = [
    # Unchanged public contract
    "tier_for",
    "TIER_AUTO",
    "TIER_REVIEW",
    "TIER_NONE",
    "ROOTS",
    # New, additive surface
    "ground",
    "GroundingDecision",
    "GroundingCheck",
    "GroundedTerm",
    "GroundingBackend",
    "OLSBackend",
    "LocalOntologyBackend",
    "ChainedBackend",
    "rank_candidates",
    "SCOPE_EXACT",
    "SCOPE_BROAD",
    "SCOPE_NARROW",
    "SCOPE_RELATED",
    # Cache accessors, re-exported for the _pkg self-import pattern
    "get_cached_grounding",
    "store_cached_grounding",
]
