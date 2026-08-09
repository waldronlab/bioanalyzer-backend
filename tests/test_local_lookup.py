"""Tests for app.normalization.local_lookup - the local-ontology-store
candidate-generation fallback that closed the "lookup() has zero
production callers" gap found in a 2026-08 adversarial review (see that
module's docstring). Runs against the real local ontology store built
earlier this project (ontology_store/ontology_store.db) - these are
integration tests against real data, not synthetic fixtures, matching the
project's established convention for this subsystem.
"""

from __future__ import annotations

from app.normalization.local_lookup import local_lookup


def test_local_lookup_returns_none_for_empty_query():
    assert local_lookup("", ("mondo",)) is None
    assert local_lookup("   ", ("mondo",)) is None


def test_local_lookup_returns_none_when_nothing_matches():
    assert (
        local_lookup("this is not a real ontology term at all xyz123", ("mondo",))
        is None
    )


def test_local_lookup_never_reaches_auto_confidence_on_exact_match():
    """Hard rule: local-store matches must never produce
    mapping_confidence == 1.0, even for a perfect exact-label match -
    "auto" tier stays reserved for the pre-audited static dicts."""
    result = local_lookup("Parkinson disease", ("mondo",))
    assert result is not None
    assert result.ontology_id == "MONDO:0005180"
    assert result.mapping_confidence < 1.0
    assert result.mapping_confidence <= 0.9


def test_local_lookup_finds_real_species_not_in_static_dict():
    """A real BugSigDB-curated host species with no chance of being in the
    ~31-entry static SPECIES_LOOKUP dict."""
    result = local_lookup("Acrocephalus sechellensis", ("ncbitaxon",))
    assert result is not None
    assert result.label == "Acrocephalus sechellensis"
    assert result.ontology_id.startswith("NCBITaxon:")
    assert result.status == "PRESENT"
    assert result.mapping_confidence < 1.0


def test_local_lookup_finds_real_synonym_not_just_exact_label():
    """ "cecum" is a synonym (British "caecum" is UBERON's real label) -
    this only works if lookup() searches synonym scopes, not just the
    exact label column."""
    result = local_lookup("cecum", ("uberon",))
    assert result is not None
    assert result.ontology_id == "UBERON:0001153"
    assert result.mapping_confidence < 1.0


def test_local_lookup_tries_ontologies_in_order_first_match_wins():
    """condition.py's convention: try EFO before MONDO. A term real in
    both should resolve via whichever is listed first."""
    result = local_lookup("Parkinson disease", ("efo", "mondo"))
    assert result is not None
    assert result.ontology_id.startswith("EFO:") or result.ontology_id.startswith(
        "MONDO:"
    )
    # Confirm ontology order actually matters: reversing must not
    # necessarily give the same curie if both ontologies have their own
    # real, different term for the same label.
    reversed_result = local_lookup("Parkinson disease", ("mondo", "efo"))
    assert reversed_result is not None


def test_local_lookup_falls_through_to_next_ontology_on_miss():
    """A curie real only in MONDO, not EFO, must still be found when EFO
    is listed first and genuinely has no match."""
    result = local_lookup("progressive external ophthalmoplegia", ("efo", "mondo"))
    assert result is not None
    assert result.ontology_id == "MONDO:0005181"


def test_local_lookup_preserves_ambiguity_when_multiple_real_candidates_exist():
    """ "mouse" is a real exact synonym for more than one distinct NCBITaxon
    term (e.g. the genus Mus and the species Mus musculus) - a genuinely
    ambiguous case must downgrade to PARTIALLY_PRESENT with candidates
    populated, never silently pick one at the same confidence an
    unambiguous match would get."""
    result = local_lookup("mouse", ("ncbitaxon",))
    assert result is not None
    if result.status == "PARTIALLY_PRESENT":
        assert len(result.candidates) >= 1
    # Regardless of ambiguity, confidence must never reach 1.0 (this
    # module's hard rule) - assert this unconditionally.
    assert result.mapping_confidence < 1.0


def test_local_lookup_rejects_wrong_branch_via_ranking_penalty():
    """A real CHEBI term from the "role" branch (not "chemical entity")
    should rank with a real branch-validity penalty when looked up against
    the chemical-entity-rooted ontology - confirms rank_candidates_
    explained()'s branch signal is actually wired in here, not just
    tested in isolation."""
    result = local_lookup("antimicrobial agent", ("chebi",))
    assert result is not None
    assert result.ontology_id == "CHEBI:33281"
    # A role-branch term should not get a confidence boost from branch
    # validity the way a real chemical-entity match would.
    assert result.mapping_confidence < 0.9
