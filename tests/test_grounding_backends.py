"""Tests for the app.normalization.grounding package's backend architecture
(GroundingBackend Protocol, OLSBackend, LocalOntologyBackend, ChainedBackend,
seed data, and the explainable ground()/GroundingDecision entry point).

tests/test_grounding.py covers tier_for()'s unchanged public contract;
this file covers the new machinery tier_for() is now built on top of.
LocalOntologyBackend tests run against an in-memory store (`:memory:`) so
they're fast and never touch disk or network, and pass regardless of
whether the optional `duckdb` package is installed (falls back to stdlib
sqlite3 - see local_backend.py's module docstring) except where a test is
explicitly about the DuckDB engine path, which skips cleanly if duckdb
isn't importable.
"""

from __future__ import annotations

import pytest
from conftest import requires_real_ontology_store

from app.normalization import grounding as grounding_module
from app.normalization import ols as ols_module
from app.normalization.grounding.backend import (
    SCOPE_BROAD,
    SCOPE_EXACT,
    SCOPE_NARROW,
    SCOPE_RELATED,
    GroundedTerm,
    GroundingCheck,
    GroundingDecision,
    rank_candidates,
    rank_candidates_explained,
)
from app.normalization.grounding.chain import ChainedBackend
from app.normalization.grounding.local_backend import (
    DEFAULT_DB_PATH,
    LocalOntologyBackend,
)
from app.normalization.grounding.ols_backend import OLSBackend
from app.normalization.grounding.roots import ROOTS, prefix_of
from app.normalization.grounding.seed import build_seed_store
from app.normalization.grounding.tiering import _build_default_backend, ground
from app.normalization.ols import TermVerification
from app.normalization.types import NormalizedTerm


@pytest.fixture(autouse=True)
def _no_grounding_cache(monkeypatch):
    """Same reasoning as tests/test_grounding.py's fixture of the same name:
    grounding checks persist to a real on-disk SQLite cache by default: any
    test in this file that reaches tiering.ground()/tier_for() must not
    silently read from or pollute it."""
    monkeypatch.setattr(grounding_module, "get_cached_grounding", lambda *a: None)
    monkeypatch.setattr(
        grounding_module, "store_cached_grounding", lambda *a, **k: None
    )


# ---------------------------------------------------------------------------
# backend.py: value objects + rank_candidates()
# ---------------------------------------------------------------------------


def test_rank_candidates_orders_exact_before_broad_before_narrow():
    narrow = GroundedTerm(curie="A:1", label="a", ontology="a", scope=SCOPE_NARROW)
    exact = GroundedTerm(curie="A:2", label="b", ontology="a", scope=SCOPE_EXACT)
    broad = GroundedTerm(curie="A:3", label="c", ontology="a", scope=SCOPE_BROAD)
    ranked = rank_candidates([narrow, broad, exact])
    assert [c.curie for c in ranked] == ["A:2", "A:3", "A:1"]


def test_rank_candidates_empty_list():
    assert rank_candidates([]) == []


def test_rank_candidates_explained_scope_dominates_similarity():
    """A worse textual match at a stronger scope must still outrank a
    perfect textual match at a weaker scope - scope is the primary signal,
    similarity only refines within a tier (see backend.py's docstring for
    why: exact-scope evidence is inherently more trustworthy than a
    related-synonym hit, however close the wording)."""
    exact_but_different_wording = GroundedTerm(
        curie="A:1", label="Parkinson disease", ontology="a", scope=SCOPE_EXACT
    )
    related_and_identical_wording = GroundedTerm(
        curie="A:2", label="Parkinson's", ontology="a", scope=SCOPE_RELATED
    )
    ranked = rank_candidates_explained(
        [related_and_identical_wording, exact_but_different_wording],
        query="Parkinson's",
    )
    assert ranked[0].term.curie == "A:1"
    assert ranked[0].term.scope == SCOPE_EXACT


def test_rank_candidates_explained_similarity_breaks_ties_within_scope():
    close = GroundedTerm(curie="A:1", label="Parkinson disease", ontology="a")
    far = GroundedTerm(curie="A:2", label="Alzheimer disease", ontology="a")
    ranked = rank_candidates_explained([far, close], query="Parkinson disease")
    assert ranked[0].term.curie == "A:1"
    assert ranked[0].similarity > ranked[1].similarity
    assert ranked[0].confidence > ranked[1].confidence


def test_rank_candidates_explained_reports_a_reason():
    term = GroundedTerm(
        curie="A:1", label="feces", ontology="uberon", scope=SCOPE_EXACT
    )
    ranked = rank_candidates_explained([term], query="fecal")
    assert "exact" in ranked[0].explanation
    assert "feces" in ranked[0].explanation


def test_rank_candidates_explained_without_query_treats_all_as_maximally_similar():
    """No query text -> pure scope ordering, same result as rank_candidates()."""
    a = GroundedTerm(curie="A:1", label="x", ontology="a", scope=SCOPE_EXACT)
    b = GroundedTerm(curie="A:2", label="y", ontology="a", scope=SCOPE_EXACT)
    ranked = rank_candidates_explained([a, b])
    assert ranked[0].similarity == ranked[1].similarity == 1.0


class _BranchCheckOnlyBackend:
    """Minimal fake exposing just reachable_from() (and optionally
    get_xrefs()) - for testing rank_candidates_explained()'s branch-
    validity/cross-reference signals in isolation, without needing a real
    LocalOntologyBackend or touching the shared `_StubBackend` fixture
    other ChainedBackend tests rely on."""

    def __init__(self, *, branch_result=None, xrefs=None):
        self._branch_result = branch_result
        self._xrefs = xrefs

    def reachable_from(self, curie, root, ontology):
        return self._branch_result

    def get_xrefs(self, ontology, curie):
        if self._xrefs is None:
            raise AssertionError("get_xrefs() should not be called when xrefs=None")
        return self._xrefs


def test_rank_candidates_explained_branch_bonus_when_reachable(monkeypatch):
    import app.normalization.grounding.roots as roots_module

    monkeypatch.setattr(roots_module, "ROOTS", {"X": ("x", "X:ROOT")})
    monkeypatch.setattr(roots_module, "EXTENDED_ONTOLOGY_ROOTS", {})
    term = GroundedTerm(curie="X:1", label="term one", ontology="x", scope=SCOPE_BROAD)

    ranked = rank_candidates_explained(
        [term], backend=_BranchCheckOnlyBackend(branch_result=True)
    )

    assert ranked[0].confidence == 0.85  # 0.75 scope weight + 0.1 branch bonus
    assert "reachable from root X:ROOT" in ranked[0].explanation


def test_rank_candidates_explained_branch_penalty_when_not_reachable(monkeypatch):
    import app.normalization.grounding.roots as roots_module

    monkeypatch.setattr(roots_module, "ROOTS", {"X": ("x", "X:ROOT")})
    monkeypatch.setattr(roots_module, "EXTENDED_ONTOLOGY_ROOTS", {})
    term = GroundedTerm(curie="X:1", label="term one", ontology="x", scope=SCOPE_BROAD)

    ranked = rank_candidates_explained(
        [term], backend=_BranchCheckOnlyBackend(branch_result=False)
    )

    assert ranked[0].confidence == 0.45  # 0.75 scope weight - 0.3 branch penalty
    assert "NOT reachable from root X:ROOT" in ranked[0].explanation


def test_rank_candidates_explained_branch_unverified_leaves_confidence_unchanged(
    monkeypatch,
):
    import app.normalization.grounding.roots as roots_module

    monkeypatch.setattr(roots_module, "ROOTS", {"X": ("x", "X:ROOT")})
    monkeypatch.setattr(roots_module, "EXTENDED_ONTOLOGY_ROOTS", {})
    term = GroundedTerm(curie="X:1", label="term one", ontology="x", scope=SCOPE_BROAD)

    ranked = rank_candidates_explained(
        [term], backend=_BranchCheckOnlyBackend(branch_result=None)
    )

    assert ranked[0].confidence == 0.75  # unchanged - fail-open, not a penalty
    assert "reachable" not in ranked[0].explanation.lower()


def test_rank_candidates_explained_no_root_configured_skips_branch_check():
    """An ontology with no ROOTS/EXTENDED_ONTOLOGY_ROOTS entry (e.g. one of
    the NO_SINGLE_ROOT ontologies) must not error - branch check is simply
    skipped, same as when no backend is given at all."""
    term = GroundedTerm(
        curie="NCIT:1", label="term one", ontology="ncit", scope=SCOPE_BROAD
    )
    ranked = rank_candidates_explained(
        [term], backend=_BranchCheckOnlyBackend(branch_result=True)
    )
    assert ranked[0].confidence == 0.75  # no bonus applied - no root to check against


def test_rank_candidates_explained_surfaces_xrefs_without_scoring(monkeypatch):
    import app.normalization.grounding.roots as roots_module

    monkeypatch.setattr(roots_module, "ROOTS", {})
    monkeypatch.setattr(roots_module, "EXTENDED_ONTOLOGY_ROOTS", {})
    term = GroundedTerm(curie="X:1", label="term one", ontology="x", scope=SCOPE_EXACT)

    ranked = rank_candidates_explained(
        [term],
        backend=_BranchCheckOnlyBackend(xrefs=["DOID:1612", "ICD10:C50"]),
    )

    assert "cross-references on file" in ranked[0].explanation
    assert "DOID:1612" in ranked[0].explanation
    # Purely informational - xrefs must not change the confidence score.
    assert ranked[0].confidence == 1.0


def test_rank_candidates_explained_backend_without_get_xrefs_is_fine():
    """OLSBackend (and any backend that doesn't implement the optional,
    non-Protocol get_xrefs() capability) must rank normally, not error."""

    class _NoXrefBackend:
        def reachable_from(self, curie, root, ontology):
            return None

    term = GroundedTerm(curie="X:1", label="term one", ontology="x", scope=SCOPE_EXACT)
    ranked = rank_candidates_explained([term], backend=_NoXrefBackend())
    assert "cross-references" not in ranked[0].explanation


def test_chained_backend_get_xrefs_merges_and_dedupes():
    class _XrefBackend:
        def __init__(self, xrefs):
            self._xrefs = xrefs

        def get_xrefs(self, ontology, curie):
            return self._xrefs

    chain = ChainedBackend(
        [_XrefBackend(["DOID:1612", "ICD10:C50"]), _XrefBackend(["DOID:1612", "X:1"])]
    )
    assert chain.get_xrefs("mondo", "MONDO:1") == ["DOID:1612", "ICD10:C50", "X:1"]


def test_local_backend_bulk_insert_xrefs_and_get_xrefs(local_backend):
    local_backend.upsert_term("mondo", "MONDO:1", "term one")
    local_backend.bulk_insert_xrefs(
        "mondo", [("MONDO:1", "DOID:1612"), ("MONDO:1", "ICD10:C50")]
    )
    assert local_backend.get_xrefs("mondo", "MONDO:1") == ["DOID:1612", "ICD10:C50"]
    assert local_backend.get_xrefs("mondo", "MONDO:nonexistent") == []


def test_local_backend_clear_ontology_removes_xrefs_too(local_backend):
    local_backend.upsert_term("mondo", "MONDO:1", "term one")
    local_backend.bulk_insert_xrefs("mondo", [("MONDO:1", "DOID:1612")])
    local_backend.clear_ontology("mondo")
    assert local_backend.get_xrefs("mondo", "MONDO:1") == []


def test_chained_backend_lookup_ranks_merged_results():
    """The merge order in ChainedBackend.lookup() should not determine
    result order - a better match from a later backend still sorts first."""
    poor_match = GroundedTerm(
        curie="A:1", label="Alzheimer disease", ontology="a", scope=SCOPE_EXACT
    )
    good_match = GroundedTerm(
        curie="A:2", label="Parkinson disease", ontology="a", scope=SCOPE_EXACT
    )
    chain = ChainedBackend(
        [
            _StubBackend(lookup_result=[poor_match]),
            _StubBackend(lookup_result=[good_match]),
        ]
    )
    results = chain.lookup("Parkinson disease", "a")
    assert results[0].curie == "A:2"


def test_prefix_of():
    assert prefix_of("MONDO:0005180") == "MONDO"
    assert prefix_of("not-a-curie") == ""


# ---------------------------------------------------------------------------
# ols_backend.py: OLSBackend delegates to app.normalization.ols, doesn't
# reimplement any HTTP logic
# ---------------------------------------------------------------------------


def test_ols_backend_get_delegates_to_fetch_term(monkeypatch):
    calls = []

    def fake_fetch_term(curie, default_prefix=""):
        calls.append(curie)
        return TermVerification(exists=True, label="Parkinson disease")

    monkeypatch.setattr(ols_module, "fetch_term", fake_fetch_term)
    backend = OLSBackend()
    check = backend.get("MONDO:0005180", "mondo")
    assert calls == ["MONDO:0005180"]
    assert isinstance(check, GroundingCheck)
    assert check.exists is True
    assert check.label == "Parkinson disease"
    assert check.source == "ols"


def test_ols_backend_get_returns_none_when_ols_unreachable(monkeypatch):
    monkeypatch.setattr(ols_module, "fetch_term", lambda *a, **k: None)
    assert OLSBackend().get("MONDO:0005180", "mondo") is None


def test_ols_backend_reachable_from_delegates_to_is_in_branch(monkeypatch):
    calls = []

    def fake_is_in_branch(curie, ontology, root):
        calls.append((curie, ontology, root))
        return True

    monkeypatch.setattr(ols_module, "is_in_branch", fake_is_in_branch)
    result = OLSBackend().reachable_from("MONDO:0005180", "MONDO:0000001", "mondo")
    assert result is True
    assert calls == [("MONDO:0005180", "mondo", "MONDO:0000001")]


def test_ols_backend_lookup_delegates_to_ols_search(monkeypatch):
    monkeypatch.setattr(
        ols_module,
        "ols_search",
        lambda query, ontology, prefix, **k: ("duodenum", "UBERON:0002114", 0.9),
    )
    results = OLSBackend().lookup("duodenal", "uberon")
    assert len(results) == 1
    assert results[0].curie == "UBERON:0002114"
    assert results[0].label == "duodenum"
    assert results[0].scope == SCOPE_EXACT
    assert results[0].source == "ols"


def test_ols_backend_lookup_returns_empty_list_on_no_hit(monkeypatch):
    monkeypatch.setattr(ols_module, "ols_search", lambda *a, **k: None)
    assert OLSBackend().lookup("nonexistent", "efo") == []


# ---------------------------------------------------------------------------
# local_backend.py: real queries against an in-memory store (no mocking -
# this is the actual SQL running for real, via sqlite3)
# ---------------------------------------------------------------------------


@pytest.fixture
def local_backend():
    backend = LocalOntologyBackend(db_path=":memory:")
    yield backend
    backend.close()


def test_local_backend_engine_is_sqlite3_when_duckdb_unavailable(local_backend):
    # This suite doesn't assume duckdb is installed - assert whichever
    # engine actually loaded is a real, working one.
    assert local_backend._db.engine in ("sqlite3", "duckdb")


def test_local_backend_gives_actionable_error_for_wrong_engine_file(
    tmp_path, monkeypatch
):
    """A DuckDB-format file opened without duckdb installed must fail with
    an explanation, not a bare `sqlite3.DatabaseError: file is not a
    database` - found for real running scripts/ontology_sync.py's --status
    against a store built with duckdb available, then reading it back
    without duckdb importable."""
    import builtins

    real_import = builtins.__import__

    def _no_duckdb(name, *args, **kwargs):
        if name == "duckdb":
            raise ImportError("simulated: duckdb not installed")
        return real_import(name, *args, **kwargs)

    db_path = tmp_path / "not_really_sqlite.db"
    db_path.write_bytes(b"DuckDB-format bytes that are not a SQLite file at all")

    monkeypatch.setattr(builtins, "__import__", _no_duckdb)
    with pytest.raises(RuntimeError, match="DuckDB's format"):
        LocalOntologyBackend(db_path=str(db_path))


def test_local_backend_get_on_empty_store_is_unknown_not_false(local_backend):
    """A store that has never claimed coverage of "efo" can't say a curie
    doesn't exist - only that it doesn't know. Returns None (inconclusive),
    not GroundingCheck(exists=False) - see LocalOntologyBackend's module
    docstring for why conflating these was a real correctness bug (a
    ChainedBackend would short-circuit on the false negative instead of
    falling through to a backend that could actually answer)."""
    assert local_backend.get("EFO:9999999", "efo") is None


def test_local_backend_get_missing_term_in_complete_ontology_reports_not_exists(
    local_backend,
):
    local_backend.upsert_term("efo", "EFO:0000400", "diabetes mellitus")
    local_backend.mark_complete("efo")
    check = local_backend.get("EFO:9999999", "efo")
    assert check.exists is False


def test_local_backend_insert_and_get_round_trip(local_backend):
    local_backend.upsert_term("efo", "EFO:0000400", "diabetes mellitus")
    check = local_backend.get("EFO:0000400", "efo")
    assert check.exists is True
    assert check.label == "diabetes mellitus"
    assert check.is_obsolete is False


def test_local_backend_get_reports_obsolete_and_replacement(local_backend):
    local_backend.upsert_term(
        "efo",
        "EFO:0002508",
        "obsolete_Parkinson's disease",
        obsolete=True,
        replaced_by="MONDO:0005180",
    )
    check = local_backend.get("EFO:0002508", "efo")
    assert check.exists is True
    assert check.is_obsolete is True
    assert check.replaced_by == "MONDO:0005180"


def test_local_backend_lookup_exact_label_match(local_backend):
    local_backend.upsert_term("mondo", "MONDO:0005180", "Parkinson disease")
    results = local_backend.lookup("Parkinson Disease", "mondo")
    assert len(results) == 1
    assert results[0].curie == "MONDO:0005180"
    assert results[0].scope == SCOPE_EXACT


def test_local_backend_lookup_ignores_obsolete_terms(local_backend):
    local_backend.upsert_term(
        "mondo", "MONDO:0005180", "Parkinson disease", obsolete=True
    )
    assert local_backend.lookup("Parkinson disease", "mondo") == []


def test_local_backend_lookup_via_synonym_when_scope_requested(local_backend):
    local_backend.upsert_term("mondo", "MONDO:0005180", "Parkinson disease")
    local_backend.insert_synonym("mondo", "MONDO:0005180", "Parkinson's", SCOPE_BROAD)
    # Not requested by default (SCOPE_EXACT only) - synonym shouldn't match.
    assert local_backend.lookup("Parkinson's", "mondo") == []
    # Requested explicitly - now it should.
    results = local_backend.lookup(
        "Parkinson's", "mondo", scopes=(SCOPE_EXACT, SCOPE_BROAD)
    )
    assert len(results) == 1
    assert results[0].scope == SCOPE_BROAD


def test_local_backend_reachable_from_true_when_curie_is_root(local_backend):
    assert (
        local_backend.reachable_from("MONDO:0000001", "MONDO:0000001", "mondo") is True
    )


def test_local_backend_reachable_from_direct_edge(local_backend):
    local_backend.insert_edge("mondo", "MONDO:0005180", "is_a", "MONDO:0000001")
    assert (
        local_backend.reachable_from("MONDO:0005180", "MONDO:0000001", "mondo") is True
    )


def test_local_backend_reachable_from_multi_hop(local_backend):
    # A -is_a-> B -is_a-> C (root). Confirms the recursive CTE actually
    # recurses, not just checks a direct edge. Marked complete so a miss
    # ("Z" is genuinely unreachable) reports False, not "unknown".
    local_backend.insert_edge("mondo", "A", "is_a", "B")
    local_backend.insert_edge("mondo", "B", "is_a", "C")
    local_backend.mark_complete("mondo")
    assert local_backend.reachable_from("A", "C", "mondo") is True
    assert local_backend.reachable_from("A", "Z", "mondo") is False


def test_local_backend_reachable_from_incomplete_store_is_unknown_not_false(
    local_backend,
):
    """Same graph as the multi-hop test, but *not* marked complete - a miss
    here must be "unknown" (None), not a confident False, since this store
    never claimed to hold mondo's full hierarchy."""
    local_backend.insert_edge("mondo", "A", "is_a", "B")
    assert local_backend.reachable_from("A", "Z", "mondo") is None


def test_local_backend_reachable_from_terminates_on_cycle(local_backend):
    # A -is_a-> B -is_a-> A: a real cycle. The UNION-based recursive CTE
    # must still terminate (this is exactly the footgun SPEC 070 calls out
    # UNION ALL for) and correctly report an unrelated root as unreachable.
    local_backend.insert_edge("mondo", "A", "is_a", "B")
    local_backend.insert_edge("mondo", "B", "is_a", "A")
    local_backend.mark_complete("mondo")
    assert local_backend.reachable_from("A", "NOT_THERE", "mondo") is False


def test_local_backend_ontology_versions(local_backend):
    local_backend.upsert_term("mondo", "MONDO:1", "x", version="v2026-07")
    assert local_backend.ontology_versions("mondo") == ["v2026-07"]


def test_local_backend_mark_complete_records_term_count_and_source(local_backend):
    local_backend.upsert_term("efo", "EFO:1", "a")
    local_backend.upsert_term("efo", "EFO:2", "b")
    local_backend.mark_complete(
        "efo", source="https://example.test/efo.db.gz", version="v1"
    )
    assert local_backend.is_complete("efo") is True
    assert local_backend.is_complete("mondo") is False
    rows = local_backend._db.execute(
        "SELECT term_count, source, version FROM ontology_meta WHERE ontology = 'efo'"
    )
    assert rows == [(2, "https://example.test/efo.db.gz", "v1")]


def test_local_backend_bulk_upsert_terms(local_backend):
    local_backend.bulk_upsert_terms(
        "efo",
        [
            ("EFO:1", "term one", False, "", ""),
            ("EFO:2", "term two", True, "EFO:1", "v1"),
        ],
    )
    assert local_backend.get("EFO:1", "efo").label == "term one"
    check2 = local_backend.get("EFO:2", "efo")
    assert check2.is_obsolete is True
    assert check2.replaced_by == "EFO:1"


def test_local_backend_bulk_insert_synonyms_and_edges(local_backend):
    local_backend.upsert_term("efo", "EFO:1", "term one")
    local_backend.bulk_insert_synonyms("efo", [("EFO:1", "synonym one", SCOPE_EXACT)])
    local_backend.bulk_insert_edges("efo", [("EFO:1", "is_a", "EFO:0000408")])
    # An exact-scope *synonym* (e.g. real oio:hasExactSynonym data) must be
    # findable under the default scopes=(SCOPE_EXACT,) - a real bug found
    # while writing this test: an earlier version of lookup() treated
    # SCOPE_EXACT as "labels only" and never queried exact-scope synonyms
    # at all. See local_backend.py's lookup() docstring.
    results = local_backend.lookup("synonym one", "efo")
    assert len(results) == 1
    assert results[0].curie == "EFO:1"
    assert results[0].scope == SCOPE_EXACT
    assert local_backend.reachable_from("EFO:1", "EFO:0000408", "efo") is True


def test_local_backend_clear_ontology_removes_all_three_tables(local_backend):
    local_backend.upsert_term("efo", "EFO:1", "term one")
    local_backend.bulk_insert_synonyms("efo", [("EFO:1", "synonym one", SCOPE_EXACT)])
    local_backend.bulk_insert_edges("efo", [("EFO:1", "is_a", "EFO:0000408")])
    local_backend.upsert_term("mondo", "MONDO:1", "unrelated ontology")

    local_backend.clear_ontology("efo")

    assert local_backend._db.execute(
        "SELECT COUNT(*) FROM terms WHERE ontology='efo'"
    ) == [(0,)]
    assert local_backend._db.execute(
        "SELECT COUNT(*) FROM synonyms WHERE ontology='efo'"
    ) == [(0,)]
    assert local_backend._db.execute(
        "SELECT COUNT(*) FROM edges WHERE ontology='efo'"
    ) == [(0,)]
    # A different ontology's data must be untouched.
    assert local_backend.get("MONDO:1", "mondo").label == "unrelated ontology"


def test_local_backend_resync_does_not_duplicate_synonyms_or_edges(local_backend):
    """Real bug found in a 2026-08 full-sync validation pass: re-running a
    full ontology import (e.g. `ensure_ontology()` retried after a
    transient failure, or picking up a newer release) silently doubled/
    tripled synonym and edge row counts because those tables only ever saw
    plain INSERTs with no per-ontology clear - unlike `terms`, which used
    INSERT OR REPLACE and was safe. This simulates what a real re-sync does
    (write once, clear, write the same data again) and asserts the second
    write does not accumulate on top of the first."""

    def _write_snapshot():
        local_backend.upsert_term("doid", "DOID:1", "disease one")
        local_backend.bulk_insert_synonyms(
            "doid", [("DOID:1", "disease one synonym", SCOPE_EXACT)]
        )
        local_backend.bulk_insert_edges("doid", [("DOID:1", "is_a", "DOID:4")])

    _write_snapshot()
    first_synonyms = local_backend._db.execute(
        "SELECT COUNT(*) FROM synonyms WHERE ontology='doid'"
    )
    first_edges = local_backend._db.execute(
        "SELECT COUNT(*) FROM edges WHERE ontology='doid'"
    )

    local_backend.clear_ontology("doid")
    _write_snapshot()

    assert (
        local_backend._db.execute("SELECT COUNT(*) FROM synonyms WHERE ontology='doid'")
        == first_synonyms
    )
    assert (
        local_backend._db.execute("SELECT COUNT(*) FROM edges WHERE ontology='doid'")
        == first_edges
    )


def test_local_backend_lookup_finds_label_regardless_of_requested_scopes(local_backend):
    """A term's own label is always searched - it isn't itself a synonym
    scope, so passing e.g. scopes=(SCOPE_NARROW,) must not suppress label
    matches."""
    local_backend.upsert_term("efo", "EFO:1", "term one")
    results = local_backend.lookup("term one", "efo", scopes=(SCOPE_NARROW,))
    assert len(results) == 1
    assert results[0].scope == SCOPE_EXACT


@pytest.mark.parametrize("_", [None])
def test_local_backend_duckdb_engine_when_available(_):
    """Only meaningful when duckdb is actually installed (declared in
    requirements.txt, expected in CI/prod) - skips cleanly otherwise rather
    than failing an environment that doesn't have it."""
    pytest.importorskip("duckdb")
    backend = LocalOntologyBackend(db_path=":memory:")
    try:
        assert backend._db.engine == "duckdb"
        backend.upsert_term("efo", "EFO:0000400", "diabetes mellitus")
        assert backend.get("EFO:0000400", "efo").label == "diabetes mellitus"
    finally:
        backend.close()


# ---------------------------------------------------------------------------
# seed.py: build_seed_store() against a real in-memory LocalOntologyBackend
# ---------------------------------------------------------------------------


def test_build_seed_store_inserts_known_terms(local_backend):
    count = build_seed_store(local_backend)
    assert count > 0
    # Parkinson disease, a static CONDITION_LOOKUP entry, should round-trip.
    check = local_backend.get("MONDO:0005180", "mondo")
    assert check.exists is True
    assert check.label == "Parkinson disease"


def test_build_seed_store_terms_reach_their_root(local_backend):
    build_seed_store(local_backend)
    ontology, root_id = ROOTS["MONDO"]
    assert local_backend.reachable_from("MONDO:0005180", root_id, ontology) is True


def test_build_seed_store_is_idempotent(local_backend):
    first = build_seed_store(local_backend)
    second = build_seed_store(local_backend)
    assert first == second
    # No duplicate edges from calling it twice.
    ontology, root_id = ROOTS["MONDO"]
    rows = local_backend._db.execute(
        "SELECT COUNT(*) FROM edges WHERE ontology = ? AND subject = ? AND object = ?",
        (ontology, "MONDO:0005180", root_id),
    )
    assert rows[0][0] == 1


def test_build_seed_store_seeds_every_static_dict_ontology_prefix(local_backend):
    """Every ROOTS entry backed by a static lookup dict
    (EFO/MONDO/UBERON/NCBITaxon - see seed.py's _SEED_SOURCES) gets seed
    terms. DOID is deliberately excluded from this check: no BioAnalyzer
    normalizer's static dict emits DOID ids, so build_seed_store() has
    nothing to seed it with by design - DOID only ever gets real data via
    ensure_ontology() (see test_build_seed_store_skips_doid below)."""
    from app.normalization.grounding.seed import _SEED_SOURCES

    build_seed_store(local_backend)
    for prefix, (ontology, root_id) in ROOTS.items():
        if prefix not in _SEED_SOURCES:
            continue
        rows = local_backend._db.execute(
            "SELECT COUNT(*) FROM terms WHERE ontology = ?", (ontology,)
        )
        assert rows[0][0] > 0, f"no seed terms for {prefix}"


def test_build_seed_store_skips_doid(local_backend):
    """DOID has no static lookup dict (no normalizer currently emits DOID
    ids) - build_seed_store() must not fabricate seed data for it."""
    build_seed_store(local_backend)
    rows = local_backend._db.execute(
        "SELECT COUNT(*) FROM terms WHERE ontology = 'doid'"
    )
    assert rows[0][0] == 0
    assert local_backend.is_complete("doid") is False


# ---------------------------------------------------------------------------
# chain.py: ChainedBackend composition
# ---------------------------------------------------------------------------


class _StubBackend:
    def __init__(self, *, get_result=None, branch_result=None, lookup_result=None):
        self._get_result = get_result
        self._branch_result = branch_result
        self._lookup_result = lookup_result or []
        self.get_calls = 0
        self.branch_calls = 0

    def lookup(self, value, ontology, *, scopes=(SCOPE_EXACT,)):
        return self._lookup_result

    def get(self, curie, ontology):
        self.get_calls += 1
        return self._get_result

    def reachable_from(self, curie, root, ontology):
        self.branch_calls += 1
        return self._branch_result


def test_chained_backend_returns_first_non_none_get():
    first = _StubBackend(get_result=None)  # inconclusive
    second = _StubBackend(get_result=GroundingCheck(exists=True, label="x"))
    chain = ChainedBackend([first, second])
    result = chain.get("X:1", "x")
    assert result is not None
    assert result.label == "x"
    assert first.get_calls == 1
    assert second.get_calls == 1


def test_chained_backend_short_circuits_on_first_conclusive_answer():
    first = _StubBackend(get_result=GroundingCheck(exists=False))
    second = _StubBackend(
        get_result=GroundingCheck(exists=True, label="should not be reached")
    )
    chain = ChainedBackend([first, second])
    result = chain.get("X:1", "x")
    assert result.exists is False
    assert second.get_calls == 0


def test_chained_backend_reachable_from_fails_open_when_all_inconclusive():
    chain = ChainedBackend(
        [_StubBackend(branch_result=None), _StubBackend(branch_result=None)]
    )
    assert chain.reachable_from("X:1", "X:0", "x") is None


def test_chained_backend_lookup_merges_and_dedups():
    term_a = GroundedTerm(curie="X:1", label="a", ontology="x")
    term_b = GroundedTerm(curie="X:1", label="a-dup", ontology="x")  # same curie
    term_c = GroundedTerm(curie="X:2", label="c", ontology="x")
    chain = ChainedBackend(
        [
            _StubBackend(lookup_result=[term_a]),
            _StubBackend(lookup_result=[term_b, term_c]),
        ]
    )
    results = chain.lookup("q", "x")
    assert [r.curie for r in results] == ["X:1", "X:2"]


def test_chained_backend_requires_at_least_one_backend():
    with pytest.raises(ValueError):
        ChainedBackend([])


# ---------------------------------------------------------------------------
# tiering.py: _build_default_backend() - configurable backend selection
# ---------------------------------------------------------------------------


def test_default_backend_is_chain_when_unset(monkeypatch):
    monkeypatch.delenv("GROUNDING_BACKEND_MODE", raising=False)
    monkeypatch.setenv("LOCAL_ONTOLOGY_DB_PATH", ":memory:")
    assert isinstance(_build_default_backend(), ChainedBackend)


def test_default_backend_is_ols_explicitly(monkeypatch):
    monkeypatch.setenv("GROUNDING_BACKEND_MODE", "ols")
    assert isinstance(_build_default_backend(), OLSBackend)


def test_default_backend_local_mode(monkeypatch):
    monkeypatch.setenv("GROUNDING_BACKEND_MODE", "local")
    monkeypatch.setenv("LOCAL_ONTOLOGY_DB_PATH", ":memory:")
    backend = _build_default_backend()
    assert isinstance(backend, LocalOntologyBackend)


def test_default_backend_chain_mode(monkeypatch):
    monkeypatch.setenv("GROUNDING_BACKEND_MODE", "chain")
    monkeypatch.setenv("LOCAL_ONTOLOGY_DB_PATH", ":memory:")
    backend = _build_default_backend()
    assert isinstance(backend, ChainedBackend)


def test_default_backend_unrecognized_mode_falls_back_to_ols(monkeypatch):
    monkeypatch.setenv("GROUNDING_BACKEND_MODE", "not-a-real-mode")
    assert isinstance(_build_default_backend(), OLSBackend)


def test_default_backend_mode_is_case_insensitive(monkeypatch):
    monkeypatch.setenv("GROUNDING_BACKEND_MODE", "OLS")
    assert isinstance(_build_default_backend(), OLSBackend)


# ---------------------------------------------------------------------------
# tiering.py: ground() / GroundingDecision - explainability
# ---------------------------------------------------------------------------


def test_ground_reports_reason_for_no_ontology_id():
    term = NormalizedTerm(
        label="x", ontology_id="", status="PRESENT", mapping_confidence=1.0
    )
    decision = ground(term)
    assert isinstance(decision, GroundingDecision)
    assert decision.tier == "none"
    assert "ontology_id" in decision.reason


def test_ground_reports_reason_for_low_confidence():
    term = NormalizedTerm(
        label="x", ontology_id="MONDO:1", status="PRESENT", mapping_confidence=0.9
    )
    decision = ground(term)
    assert decision.tier == "review"
    assert "0.9" in decision.reason


def test_ground_reports_reason_for_non_present_status():
    term = NormalizedTerm(
        label="x", ontology_id="MONDO:1", status="ABSENT", mapping_confidence=1.0
    )
    decision = ground(term)
    assert decision.tier == "review"
    assert "ABSENT" in decision.reason


def test_ground_attaches_full_check_evidence_on_success():
    """The GroundingDecision returned for a clean "auto" match must carry
    the actual GroundingCheck (round-trip label, obsolete status, branch
    result, source) - not just the bare tier string. An earlier version of
    ground() computed this evidence internally and then discarded it,
    leaving GroundingDecision.check permanently None."""
    stub = _StubBackend(
        get_result=GroundingCheck(
            exists=True, label="Parkinson disease", source="stub"
        ),
        branch_result=True,
    )
    term = NormalizedTerm(
        label="Parkinson disease",
        ontology_id="MONDO:0005180",
        status="PRESENT",
        mapping_confidence=1.0,
    )
    decision = ground(term, backend=stub)
    assert decision.tier == "auto"
    assert decision.check is not None
    assert decision.check.exists is True
    assert decision.check.branch_ok is True
    assert decision.check.checked_root == "MONDO:0000001"


def test_ground_downgrades_when_claimed_label_does_not_match_real_label():
    """Real, severe bug found in a 2026-08-09 adversarial review: a
    correct-shaped, non-obsolete, correctly-branched CURIE that's simply
    the WRONG concept (e.g. an off-by-one ID pointing at a real but
    unrelated disease) passed round-trip + obsolete + branch checks and
    graded "auto" - the same incident class the whole subsystem exists to
    prevent, just not caught by any of the original three checks. This
    locks in the fix: claimed label vs. the ontology's own real label for
    that CURIE must be checked too."""
    stub = _StubBackend(
        get_result=GroundingCheck(
            exists=True, label="progressive external ophthalmoplegia", source="stub"
        ),
        branch_result=True,
    )
    term = NormalizedTerm(
        label="Parkinson disease",  # claimed - but the CURIE below is not that
        ontology_id="MONDO:0005181",
        status="PRESENT",
        mapping_confidence=1.0,
    )
    decision = ground(term, backend=stub)
    assert decision.tier == "review"
    assert "does not match" in decision.reason
    assert "progressive external ophthalmoplegia" in decision.reason


def test_ground_label_check_tolerates_legitimate_relabeling():
    """A deliberately shorter/friendlier static-dict label ("skin" for
    UBERON:0002097's real "skin of body") must not be flagged - the
    threshold is calibrated against this exact real case (0.5 similarity),
    with margin below the real mismatch case (0.15 similarity, see the
    test above)."""
    stub = _StubBackend(
        get_result=GroundingCheck(exists=True, label="skin of body", source="stub"),
        branch_result=True,
    )
    term = NormalizedTerm(
        label="skin",
        ontology_id="UBERON:0002097",
        status="PRESENT",
        mapping_confidence=1.0,
    )
    decision = ground(term, backend=stub)
    assert decision.tier == "auto"


def test_ground_label_check_fails_open_when_backend_omits_label():
    """A backend that doesn't populate GroundingCheck.label (e.g. a stub in
    another test, or a real backend that genuinely has no label for a
    term) must not block on the label check - fail-open, consistent with
    every other check in this discipline."""
    stub = _StubBackend(
        get_result=GroundingCheck(exists=True, source="stub"),  # label="" (default)
        branch_result=True,
    )
    term = NormalizedTerm(
        label="Parkinson disease",
        ontology_id="MONDO:0005180",
        status="PRESENT",
        mapping_confidence=1.0,
    )
    decision = ground(term, backend=stub)
    assert decision.tier == "auto"


def test_ground_reports_obsolete_reason_with_replacement():
    stub = _StubBackend(
        get_result=GroundingCheck(
            exists=True, is_obsolete=True, replaced_by="MONDO:9999", source="stub"
        )
    )
    term = NormalizedTerm(
        label="x", ontology_id="EFO:0002508", status="PRESENT", mapping_confidence=1.0
    )
    decision = ground(term, backend=stub)
    assert decision.tier == "review"
    assert "obsolete" in decision.reason
    assert "MONDO:9999" in decision.reason
    assert decision.check.replaced_by == "MONDO:9999"


def test_ground_reports_branch_check_failure_reason():
    stub = _StubBackend(
        get_result=GroundingCheck(exists=True, source="stub"), branch_result=False
    )
    term = NormalizedTerm(
        label="x", ontology_id="EFO:0003601", status="PRESENT", mapping_confidence=1.0
    )
    decision = ground(term, backend=stub)
    assert decision.tier == "review"
    assert "not reachable" in decision.reason
    assert decision.check.branch_ok is False


def test_ground_surfaces_normalized_term_candidates_as_grounded_terms():
    """A term's runner-up candidates (surfaced by the static-dict
    normalizers on an ambiguous match) should be visible on the
    GroundingDecision too - "why competing candidates were rejected" needs
    something to point at."""
    term = NormalizedTerm(
        label="obesity disorder",
        ontology_id="MONDO:0011122",
        status="PARTIALLY_PRESENT",
        mapping_confidence=0.9,
        candidates=(("type 2 diabetes mellitus", "MONDO:0005148"),),
    )
    decision = ground(term)
    assert len(decision.candidates) == 1
    assert decision.candidates[0].curie == "MONDO:0005148"
    assert decision.candidates[0].label == "type 2 diabetes mellitus"


def test_ground_with_explicit_backend_overrides_default(monkeypatch):
    """Confirms `backend=` is real and load-bearing, not decorative -
    passing a stub backend that reports the term doesn't exist must
    downgrade the tier even though the module-level default OLSBackend was
    never touched."""
    term = NormalizedTerm(
        label="x", ontology_id="MONDO:0005180", status="PRESENT", mapping_confidence=1.0
    )
    stub = _StubBackend(get_result=GroundingCheck(exists=False))
    decision = ground(term, backend=stub)
    assert decision.tier == "review"
    assert "round-trip failed" in decision.reason
    assert decision.check is not None
    assert decision.check.exists is False


@requires_real_ontology_store
def test_local_backend_reachable_from_stays_fast_against_real_ncbitaxon_data():
    """Permanent regression guard for a real, severe performance bug fixed
    2026-08: a single `WITH RECURSIVE` SQL query for `reachable_from()`
    took 4-12 seconds per call against NCBITaxon's real ~2.7M-edge table
    (`EXPLAIN QUERY PLAN` showed the recursive join only binding the
    `ontology` half of the composite index, forcing a full per-hop table
    scan) - fixed by rewriting to an application-level BFS issuing one
    indexed, non-recursive query per frontier level (see
    `local_backend.py`'s module docstring and `_bfs_edges_from()`). Run
    against the *real* synced production store (not the small in-memory
    fixture every other test in this file uses), since the bug this
    guards against only manifested at real NCBITaxon scale (~2.7M terms,
    ~2.7M edges) - skips cleanly in an environment that hasn't run
    `scripts/ontology_sync.py`. The 1-second bound is deliberately
    generous versus the ~5ms this fix actually achieves (avoiding CI
    flakiness) while still catching a real regression back toward the
    old 4-12s behavior by two to three orders of magnitude."""
    import time

    backend = LocalOntologyBackend(db_path=DEFAULT_DB_PATH)
    try:
        start = time.perf_counter()
        result = backend.reachable_from("NCBITaxon:9606", "NCBITaxon:2759", "ncbitaxon")
        elapsed = time.perf_counter() - start
    finally:
        backend.close()
    assert result is True
    assert elapsed < 1.0, f"reachable_from() took {elapsed:.3f}s, expected < 1.0s"
