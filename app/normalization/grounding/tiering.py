"""Confidence-tier classification for ontology-mapped fields - the
orchestration layer that runs BioAnalyzer's four-step grounding discipline
against a `GroundingBackend` and reduces the result to `auto`/`review`/
`none`.

Source-based tiering, unchanged from the original design
-----------------------------------------------------------
A mapping is only ever "auto"-applied when it came from a static, curated
lookup table (`status == "PRESENT"` and `mapping_confidence == 1.0`, which
today only static-dict exact matches in host_species.py/body_site.py/
condition.py produce); anything resolved via a live external lookup
(OLS/NCBI) or left ambiguous is downgraded to "review" so a curator confirms
it, and a bare miss is "none". This module classifies `NormalizedTerm`
results produced by those normalizers after the fact - it does not change
how they resolve terms.

Why "auto" additionally requires passing a live grounding check
-------------------------------------------------------------------
The 2026-07-11/12 incident (see docs/PROJECT_AUDIT.md's "Ontology Mapping
Correctness" section) happened because CONDITION_LOOKUP's static EFO IDs
were never verified and shipped at "auto" tier. That specific incident was
fixed by a one-time manual re-verification of every static ID against live
OLS - but a one-time fix doesn't stop it recurring: if an ontology
deprecates a currently-correct static ID later, nothing would notice unless
something re-checks a static match after the fact. `ground()` closes that
gap by running the round-trip + branch + obsolete steps against
any match that would otherwise earn "auto", downgrading to "review" if any
step fails - and never touches live-lookup results (those are already
"review" and stay there; loosening that to a match-quality-based tiering
would reopen the original hole).

Backend selection
------------------
`tier_for()` (the function 2 production call sites import) defaults to
`GROUNDING_BACKEND_MODE=chain`: `LocalOntologyBackend` (real, complete
EFO/MONDO/UBERON/NCBITaxon/DOID/HP data as of the 2026-08 full sync - see
`scripts/ontology_sync.py --status`) checked first, `OLSBackend` as
fallback for anything the local store doesn't (yet) hold. This was
deliberately staged behind an env var and NOT flipped on until real data
existed - see docs/GROUNDING_ARCHITECTURE.md's production-readiness pass
for why an empty/partial local store would previously have been unsafe
(the completeness-tracking fix in `local_backend.py` is what makes a
partially-synced store fail open to OLS instead of returning false
negatives, which is what makes this default safe even in an environment
that has never run `ontology_sync.py` - an empty local store just means
every check falls through to OLS, identical to the old "ols"-only
default). Set `GROUNDING_BACKEND_MODE=ols` to force the old live-only
behavior, or `=local` for fully offline (only safe once every ontology you
rely on is synced to completeness - see the mode docs below).
"""

from __future__ import annotations

import difflib
import logging
import os
from typing import Optional

import app.normalization.grounding as _pkg
from app.normalization.grounding.backend import (
    GroundedTerm,
    GroundingBackend,
    GroundingCheck,
    GroundingDecision,
)
from app.normalization.grounding.ols_backend import OLSBackend
from app.normalization.grounding.roots import ROOTS, prefix_of
from app.normalization.types import NormalizedTerm

logger = logging.getLogger(__name__)

TIER_AUTO = "auto"
TIER_REVIEW = "review"
TIER_NONE = "none"


def _build_default_backend() -> GroundingBackend:
    mode = os.getenv("GROUNDING_BACKEND_MODE", "chain").strip().lower()
    if mode == "ols":
        return OLSBackend()
    if mode in ("local", "chain"):

        from app.normalization.grounding.local_backend import (
            DEFAULT_DB_PATH,
            LocalOntologyBackend,
        )

        db_path = os.getenv("LOCAL_ONTOLOGY_DB_PATH", DEFAULT_DB_PATH)
        local = LocalOntologyBackend(db_path=db_path)
        if mode == "local":
            return local
        from app.normalization.grounding.chain import ChainedBackend

        return ChainedBackend([local, OLSBackend()])
    logger.warning(
        "Unrecognized GROUNDING_BACKEND_MODE=%r, falling back to 'ols'", mode
    )
    return OLSBackend()


_DEFAULT_BACKEND = _build_default_backend()

_LABEL_MISMATCH_THRESHOLD = 0.4


def _label_similarity(claimed_label: str, real_label: str) -> float:
    if not claimed_label or not real_label:
        return 1.0  # nothing to compare - not this check's job to flag
    return difflib.SequenceMatcher(
        None, claimed_label.strip().casefold(), real_label.strip().casefold()
    ).ratio()


def _ground_static_match(
    ontology_id: str, backend: GroundingBackend
) -> Optional[GroundingCheck]:
    """Run (or read cached) round-trip + obsolete + branch checks for
    *ontology_id* against *backend*. Returns a `GroundingCheck` (with
    `.branch_ok` populated - the round-trip and branch-check results are
    always returned together here, not just a bare pass/fail bool, so
    `ground()` can attach the full evidence to its `GroundingDecision`
    rather than reducing it to a boolean before the caller ever sees it -
    an earlier version of this function did exactly that, which is why the
    original `GroundingDecision.check`/`.candidates` fields existed but were
    never actually populated). Returns None if grounding couldn't be
    attempted (unrecognized prefix) or completed (backend unreachable) -
    None means "fail open", not "fail closed" (see module docstring)."""
    root_info = ROOTS.get(prefix_of(ontology_id))
    if root_info is None:
        return None
    ontology, root_id = root_info

    cached = _pkg.get_cached_grounding(ontology_id)
    if cached is not None:
        return GroundingCheck(
            exists=cached["term_exists"],
            label=cached["label"],
            is_obsolete=cached["is_obsolete"],
            replaced_by=cached["replaced_by"],
            branch_ok=cached["branch_ok"] if cached["root_id"] == root_id else None,
            checked_root=root_id,
            source="cache",
        )

    check = backend.get(ontology_id, ontology)
    if check is None:
        return None  # backend unreachable / unparseable - unable to verify

    branch_ok: Optional[bool] = None
    if check.exists:
        branch_ok = backend.reachable_from(ontology_id, root_id, ontology)

    _pkg.store_cached_grounding(
        ontology_id,
        term_exists=check.exists,
        label=check.label,
        is_obsolete=check.is_obsolete,
        replaced_by=check.replaced_by,
        branch_ok=branch_ok,
        root_id=root_id,
    )
    return GroundingCheck(
        exists=check.exists,
        label=check.label,
        is_obsolete=check.is_obsolete,
        replaced_by=check.replaced_by,
        branch_ok=branch_ok,
        checked_root=root_id,
        source=check.source,
    )


def _as_grounded_terms(term: NormalizedTerm) -> tuple[GroundedTerm, ...]:
    """Convert a NormalizedTerm's (label, ontology_id) candidate pairs -
    populated by the static-dict normalizers (host_species.py/body_site.py/
    condition.py) when a match was ambiguous - into the GroundingDecision's
    `candidates` field, so "why competing candidates were rejected" has
    something to point at instead of always being empty."""
    return tuple(
        GroundedTerm(curie=ontology_id, label=label, ontology=prefix_of(ontology_id))
        for label, ontology_id in term.candidates
    )


def ground(
    term: NormalizedTerm, *, backend: Optional[GroundingBackend] = None
) -> GroundingDecision:
    """The full explainable decision behind a NormalizedTerm's mapping tier
    - what `tier_for()` reduces to just `.tier`. Exposed separately so a
    caller that wants to know *why* (e.g. future curator-facing debug
    tooling, or a caller using a non-default backend) doesn't have to
    reimplement this orchestration - it's the single place the four-step
    discipline actually runs, regardless of which backend answers it."""
    backend = backend or _DEFAULT_BACKEND
    candidates = _as_grounded_terms(term)

    if not term.ontology_id:
        return GroundingDecision(
            tier=TIER_NONE, reason="no ontology_id", candidates=candidates
        )
    if term.status != "PRESENT":
        return GroundingDecision(
            tier=TIER_REVIEW,
            reason=f"status is {term.status}, not PRESENT",
            candidates=candidates,
        )
    if term.mapping_confidence < 1.0:
        return GroundingDecision(
            tier=TIER_REVIEW,
            reason=f"mapping_confidence {term.mapping_confidence} < 1.0 "
            "(live lookup or ambiguous match)",
            candidates=candidates,
        )

    check = _ground_static_match(term.ontology_id, backend)
    if check is None:
        return GroundingDecision(
            tier=TIER_AUTO,
            reason="static match; grounding check unavailable (fail open)",
            candidates=candidates,
        )
    if not check.exists:
        return GroundingDecision(
            tier=TIER_REVIEW,
            reason=f"round-trip failed: {term.ontology_id!r} no longer resolves "
            f"in {check.source}",
            check=check,
            candidates=candidates,
        )
    label_similarity = _label_similarity(term.label, check.label)
    if label_similarity < _LABEL_MISMATCH_THRESHOLD:
        return GroundingDecision(
            tier=TIER_REVIEW,
            reason=(
                f"claimed label {term.label!r} does not match "
                f"{term.ontology_id!r}'s real label {check.label!r} in "
                f"{check.source} (similarity {label_similarity:.2f} < "
                f"{_LABEL_MISMATCH_THRESHOLD}) - likely a mis-mapped or "
                "transposed identifier, not the concept it's claimed to be"
            ),
            check=check,
            candidates=candidates,
        )
    if check.is_obsolete:
        reason = f"term is obsolete in {check.source}"
        if check.replaced_by:
            reason += f", replaced by {check.replaced_by}"
        return GroundingDecision(
            tier=TIER_REVIEW, reason=reason, check=check, candidates=candidates
        )
    if check.branch_ok is False:
        return GroundingDecision(
            tier=TIER_REVIEW,
            reason=f"not reachable from declared root {check.checked_root} "
            f"in {check.source} - likely resolves to an unrelated concept",
            check=check,
            candidates=candidates,
        )
    return GroundingDecision(
        tier=TIER_AUTO,
        reason=f"static match round-tripped, not obsolete, reachable from "
        f"{check.checked_root} in {check.source}",
        check=check,
        candidates=candidates,
    )


def tier_for(term: NormalizedTerm) -> str:
    """Classify a NormalizedTerm's ontology mapping into auto/review/none.

    "auto" requires a PRESENT status and mapping_confidence == 1.0, which
    today only static-dict exact matches produce (see
    SPECIES_LOOKUP/BODY_SITE_LOOKUP/CONDITION_LOOKUP) — live OLS/NCBI
    fallbacks and ambiguous multi-match cases cap confidence below 1.0 and
    always land on "review".

    A static match additionally has to pass the round-trip/obsolete/branch
    grounding check (see module docstring) to keep "auto" — this is what
    stops a static ID that's since gone obsolete or been mis-keyed from
    silently shipping at the tier that skips curator review, without
    re-litigating every static entry by hand the way the 2026-07 audit did.
    """
    return ground(term).tier
