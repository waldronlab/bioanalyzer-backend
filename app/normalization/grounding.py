"""Confidence-tier classification for ontology-mapped fields.

Inspired by metacurator's deterministic-first grounding discipline (see
docs/adr in metacurator-main): a mapping is only ever "auto"-applied when it
came from a static, curated lookup table; anything resolved via a live
external lookup (OLS/NCBI) or left ambiguous is downgraded to "review" so a
curator confirms it, and a bare miss is "none". This module classifies
NormalizedTerm results produced by host_species.py/body_site.py/condition.py
after the fact — it does not change how those modules resolve terms.

Four-step grounding on top of that source-based split
------------------------------------------------------
The 2026-07-11/12 incident (see docs/PROJECT_AUDIT.md's "Ontology Mapping
Correctness" section) happened because CONDITION_LOOKUP's static EFO IDs were
never verified and shipped at "auto" tier. That specific incident was fixed
by a one-time manual re-verification of every static ID against live OLS —
but a one-time fix doesn't stop it recurring: if EFO deprecates a currently-
correct static ID next year, tier_for() would keep returning "auto" for it
indefinitely, since nothing re-checks a static match after the fact.

_ground_static_match() closes that gap by running metacurator's round-trip +
obsolete + branch checks (see app.normalization.ols.fetch_term/is_in_branch)
against any match that would otherwise earn "auto", and downgrading it to
"review" if any check fails:

    1. Lookup   — already done by the caller (static-dict substring match);
                  not this module's concern.
    2. Round-trip — fetch_term() re-fetches the ontology_id from OLS by IRI
                  and confirms it still resolves to something.
    3. Branch check — is_in_branch() confirms the term is still reachable
                  from its ontology's declared root (ROOTS below) — catches
                  a static ID that now resolves to an unrelated concept.
    4. Obsolete check — fetch_term() also surfaces OLS's own obsolete flag
                  and replaced_by, so a deprecated-but-still-resolving term
                  doesn't slip through as "auto" either.

This check is deliberately narrow in scope: it only ever downgrades auto ->
review, never the reverse, and never touches live-OLS-lookup results (those
are already "review" and stay there — this module does not loosen the
source-based split above to a match-quality-based one, which would reopen
the original hole). Results are cached (grounding_check_cache, TTL-based —
see app.normalization.ontology_cache) since the static dicts only contain a
few dozen unique ontology_id's; a cold cache costs one OLS round-trip per
unique ID, not per request. If OLS itself is unreachable, the check is
treated as "unable to verify" and the match keeps its prior tier (fail open)
rather than forcing every result to "review" during an OLS outage.
"""

from __future__ import annotations

from typing import Optional

from app.normalization import ols
from app.normalization.ontology_cache import (
    get_cached_grounding,
    store_cached_grounding,
)
from app.normalization.types import NormalizedTerm

TIER_AUTO = "auto"
TIER_REVIEW = "review"
TIER_NONE = "none"

# Schema-declared branch root per ontology, keyed by the CURIE prefix found on
# NormalizedTerm.ontology_id (see condition.py/body_site.py/host_species.py's
# lookup dicts for which prefixes are in play). These are among the most
# stable, widely-cited IDs in each ontology (deliberately not disease-specific
# leaf terms, which is what went wrong in the original incident) - low risk
# of drifting themselves.
ROOTS: dict[str, tuple[str, str]] = {
    # prefix -> (OLS ontology slug, root ontology_id)
    "EFO": ("efo", "EFO:0000408"),  # "disease"
    "MONDO": ("mondo", "MONDO:0000001"),  # "disease or disorder"
    "UBERON": ("uberon", "UBERON:0001062"),  # "anatomical entity"
    "NCBITaxon": ("ncbitaxon", "NCBITaxon:2759"),  # "Eukaryota"
}


def _prefix(ontology_id: str) -> str:
    return ontology_id.split(":", 1)[0] if ":" in ontology_id else ""


def _ground_static_match(ontology_id: str) -> Optional[bool]:
    """Run (or read cached) round-trip + obsolete + branch checks for
    *ontology_id*. Returns True if it still passes all of them, False if any
    check completed and failed, or None if grounding couldn't be attempted
    (unrecognized prefix) or completed (OLS unreachable) — see module
    docstring for why None means "fail open", not "fail closed"."""
    root_info = ROOTS.get(_prefix(ontology_id))
    if root_info is None:
        return None
    ontology, root_id = root_info

    cached = get_cached_grounding(ontology_id)
    if cached is not None:
        if not cached["term_exists"] or cached["is_obsolete"]:
            return False
        if cached["root_id"] == root_id and cached["branch_ok"] is False:
            return False
        return True

    verification = ols.fetch_term(ontology_id)
    if verification is None:
        return None  # OLS unreachable / unparseable - unable to verify

    branch_ok: Optional[bool] = None
    if verification.exists:
        branch_ok = ols.is_in_branch(ontology_id, ontology, root_id)

    store_cached_grounding(
        ontology_id,
        term_exists=verification.exists,
        label=verification.label,
        is_obsolete=verification.is_obsolete,
        replaced_by=verification.replaced_by,
        branch_ok=branch_ok,
        root_id=root_id,
    )

    if not verification.exists or verification.is_obsolete:
        return False
    if branch_ok is False:
        return False
    return True


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
    if not term.ontology_id:
        return TIER_NONE
    if term.status != "PRESENT" or term.mapping_confidence < 1.0:
        return TIER_REVIEW
    if _ground_static_match(term.ontology_id) is False:
        return TIER_REVIEW
    return TIER_AUTO
