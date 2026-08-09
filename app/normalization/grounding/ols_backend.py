"""GroundingBackend adapter over the live EBI OLS4 REST API.

Deliberately a thin wrapper, not a reimplementation: all HTTP logic (URL
construction, IRI encoding, response parsing, timeout/exception handling)
stays in `app.normalization.ols`, which predates this package and is
directly unit-tested against mocked HTTP responses in
`tests/test_normalization.py`. This module's only job is to satisfy the
`GroundingBackend` Protocol shape by delegating to those functions.

Calls `ols.fetch_term`/`ols.is_in_branch`/`ols.ols_search` via the module
object (``ols.fetch_term(...)``), not a direct `from ... import fetch_term`,
so that ``monkeypatch.setattr(ols_module, "fetch_term", ...)`` in existing
tests keeps intercepting calls made through this adapter too - the same
late-binding reason `app.services.bugsigdb_analyzer` calls its own
submodules via `import ... as _pkg; _pkg.X()` instead of a direct import
(see that package's docstring).
"""

from __future__ import annotations

from typing import List, Optional, Tuple

from app.normalization import ols
from app.normalization.grounding.backend import (
    SCOPE_EXACT,
    GroundedTerm,
    GroundingCheck,
)


class OLSBackend:
    """Live EBI OLS4-backed GroundingBackend. No local state; every call is
    a network round-trip (through `ols.py`'s own persistent term-cache for
    `lookup()`, and the caller's grounding-check cache for `get()`/
    `reachable_from()` - this class itself caches nothing)."""

    name = "ols"

    def lookup(
        self, value: str, ontology: str, *, scopes: Tuple[str, ...] = (SCOPE_EXACT,)
    ) -> List[GroundedTerm]:
        """Free-text search via OLS's `/api/search`. OLS's search endpoint
        doesn't report which synonym scope matched, so every hit is
        reported as SCOPE_EXACT here at the *string-match* level - this is
        intentionally not the same claim as "auto-tier eligible"; tiering.py
        still requires round-trip+branch+obsolete to pass before anything
        from this backend can reach "auto" (see that module's docstring for
        why live-search results are pinned to "review" regardless of
        `scope`)."""
        default_prefix = ontology.upper()
        hit = ols.ols_search(value, ontology, default_prefix)
        if not hit:
            return []
        label, curie, _confidence = hit
        return [
            GroundedTerm(
                curie=curie,
                label=label,
                ontology=ontology,
                scope=SCOPE_EXACT,
                source=self.name,
            )
        ]

    def get(self, curie: str, ontology: str) -> Optional[GroundingCheck]:
        verification = ols.fetch_term(curie)
        if verification is None:
            return None
        return GroundingCheck(
            exists=verification.exists,
            label=verification.label,
            is_obsolete=verification.is_obsolete,
            replaced_by=verification.replaced_by,
            source=self.name,
        )

    def reachable_from(self, curie: str, root: str, ontology: str) -> Optional[bool]:
        return ols.is_in_branch(curie, ontology, root)
