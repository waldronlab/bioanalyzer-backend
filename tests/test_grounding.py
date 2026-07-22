import pytest

from app.normalization import grounding as grounding_module
from app.normalization import ols as ols_module
from app.normalization.grounding import TIER_AUTO, TIER_NONE, TIER_REVIEW, tier_for
from app.normalization.ols import TermVerification
from app.normalization.types import NormalizedTerm


@pytest.fixture(autouse=True)
def _no_grounding_cache(monkeypatch):
    """Grounding checks persist to a real on-disk SQLite cache
    (grounding_check_cache); disable that here so each test's fetch_term/
    is_in_branch mock is actually exercised instead of being short-circuited
    by a previous test's cached result for the same ontology_id."""
    monkeypatch.setattr(grounding_module, "get_cached_grounding", lambda *a: None)
    monkeypatch.setattr(
        grounding_module, "store_cached_grounding", lambda *a, **k: None
    )


@pytest.fixture(autouse=True)
def _stub_live_ols(monkeypatch):
    """By default, make the round-trip/branch checks behave as if OLS
    confirmed the term is live, not obsolete, and in-branch — i.e. a static
    match that grounds cleanly. Individual tests override fetch_term/
    is_in_branch to exercise the downgrade paths instead. Without this,
    tier_for() would attempt a real network call to OLS on every "auto"-
    candidate test, which is exactly what CLAUDE.md says this suite avoids."""

    def _fake_fetch_term(ontology_id, default_prefix=""):
        return TermVerification(exists=True, label="stub label", is_obsolete=False)

    monkeypatch.setattr(ols_module, "fetch_term", _fake_fetch_term)
    monkeypatch.setattr(ols_module, "is_in_branch", lambda *a: True)


def test_tier_none_when_no_ontology_id():
    term = NormalizedTerm(
        label="stool",
        ontology_id="",
        status="PARTIALLY_PRESENT",
        mapping_confidence=0.5,
    )
    assert tier_for(term) == TIER_NONE


def test_tier_auto_for_full_confidence_present_match():
    term = NormalizedTerm(
        label="Homo sapiens",
        ontology_id="NCBITaxon:9606",
        status="PRESENT",
        mapping_confidence=1.0,
    )
    assert tier_for(term) == TIER_AUTO


def test_tier_review_for_partial_confidence_match():
    term = NormalizedTerm(
        label="Mus musculus",
        ontology_id="NCBITaxon:10090",
        status="PARTIALLY_PRESENT",
        mapping_confidence=0.9,
    )
    assert tier_for(term) == TIER_REVIEW


def test_tier_review_for_live_lookup_match():
    term = NormalizedTerm(
        label="duodenum",
        ontology_id="UBERON:0002114",
        status="PRESENT",
        mapping_confidence=0.9,
    )
    assert tier_for(term) == TIER_REVIEW


# ---------------------------------------------------------------------------
# Four-step grounding discipline: round-trip / obsolete / branch downgrades
# ---------------------------------------------------------------------------


def _static_match(ontology_id: str) -> NormalizedTerm:
    return NormalizedTerm(
        label="Parkinson disease",
        ontology_id=ontology_id,
        status="PRESENT",
        mapping_confidence=1.0,
    )


def test_tier_auto_when_static_match_grounds_cleanly():
    # Sanity check that the default fixture stubs actually let "auto" through.
    assert tier_for(_static_match("MONDO:0005180")) == TIER_AUTO


def test_tier_downgraded_when_round_trip_fails(monkeypatch):
    """The ID doesn't resolve to anything on OLS anymore - the strongest
    possible signal of a fabricated/deleted static entry."""
    monkeypatch.setattr(
        ols_module, "fetch_term", lambda *a, **k: TermVerification(exists=False)
    )
    assert tier_for(_static_match("MONDO:0005180")) == TIER_REVIEW


def test_tier_downgraded_when_term_is_obsolete(monkeypatch):
    monkeypatch.setattr(
        ols_module,
        "fetch_term",
        lambda *a, **k: TermVerification(
            exists=True,
            label="obsolete_Parkinson's disease",
            is_obsolete=True,
            replaced_by="MONDO:0005180",
        ),
    )
    assert tier_for(_static_match("EFO:0002508")) == TIER_REVIEW


def test_tier_downgraded_when_branch_check_fails(monkeypatch):
    """Term round-trips and isn't obsolete, but no longer lives under its
    ontology's declared root - it now resolves to an unrelated concept."""
    monkeypatch.setattr(
        ols_module,
        "fetch_term",
        lambda *a, **k: TermVerification(exists=True, label="somite 13"),
    )
    monkeypatch.setattr(ols_module, "is_in_branch", lambda *a: False)
    assert tier_for(_static_match("EFO:0003601")) == TIER_REVIEW


def test_tier_stays_auto_when_ols_unreachable(monkeypatch):
    """OLS being unreachable is treated as "unable to verify", not "failed" -
    the match keeps its prior tier (fail open) rather than forcing every
    result to "review" during an OLS outage."""
    monkeypatch.setattr(ols_module, "fetch_term", lambda *a, **k: None)
    assert tier_for(_static_match("MONDO:0005180")) == TIER_AUTO


def test_tier_auto_for_unmapped_ontology_prefix():
    """A prefix with no configured branch root (e.g. BugSigDB's own
    controlled vocab, which never has an ontology_id, or a future ontology
    not yet wired into ROOTS) skips grounding entirely rather than erroring."""
    term = NormalizedTerm(
        label="widget",
        ontology_id="UNKNOWNONTOLOGY:123",
        status="PRESENT",
        mapping_confidence=1.0,
    )
    assert tier_for(term) == TIER_AUTO


def test_grounding_result_is_cached(monkeypatch):
    calls = []

    def _fake_fetch_term(ontology_id, default_prefix=""):
        calls.append(ontology_id)
        return TermVerification(exists=True, label="Parkinson disease")

    store = {}
    monkeypatch.setattr(ols_module, "fetch_term", _fake_fetch_term)
    monkeypatch.setattr(
        grounding_module,
        "store_cached_grounding",
        lambda ontology_id, **kw: store.__setitem__(ontology_id, kw),
    )
    monkeypatch.setattr(
        grounding_module,
        "get_cached_grounding",
        lambda ontology_id: store.get(ontology_id),
    )

    term = _static_match("MONDO:0005180")
    assert tier_for(term) == TIER_AUTO
    assert tier_for(term) == TIER_AUTO
    assert calls == ["MONDO:0005180"]  # second call served from the cache
