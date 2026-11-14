"""Condition output expressed in BugSigDB's own vocabulary.

Covers app/normalization/bugsigdb_vocabulary.py, the BugSigDB steps of
app/normalization/condition.py::normalize_condition (exact BugSigDB label,
retired-term replacement, EFO<->MONDO equivalence, embedding match,
relabel), embedding_match.nearest(), and tiering's label-check exemption.
Everything runs offline: the ontology store is in-memory, OLS and the
embedding model are stubbed.
"""

from __future__ import annotations

import json

import numpy as np
import pytest

import app.normalization.condition as condition
import app.normalization.embedding_match as embedding_match
import app.normalization.grounding as grounding_module
from app.normalization import bugsigdb_vocabulary
from app.normalization.bugsigdb_vocabulary import BugSigDBVocabulary
from app.normalization.grounding.backend import GroundingCheck
from app.normalization.grounding.local_backend import LocalOntologyBackend
from app.normalization.grounding.tiering import TIER_AUTO, TIER_REVIEW, ground
from app.normalization.types import NormalizedTerm

TERMS = {
    "MONDO:0005180": {"label": "Parkinson's disease", "rows": 410},
    "MONDO:0005148": {"label": "Type II diabetes mellitus", "rows": 165},
    "MONDO:0011122": {"label": "Obesity", "rows": 287},
    "MONDO:0005146": {"label": "Post-traumatic stress disorder", "rows": 3},
    "MONDO:0700226": {"label": "Food allergy", "rows": 56},
    "EFO:0010130": {"label": "Health study participation", "rows": 12},
    "MONDO:0002009": {
        "label": "Major depressive disorder",
        "rows": 62,
        "other_labels": ["Unipolar depression"],
    },
}


@pytest.fixture
def vocab_file(tmp_path, monkeypatch):
    path = tmp_path / "vocab.json"
    path.write_text(json.dumps({"terms": TERMS}))
    monkeypatch.setenv("BUGSIGDB_CONDITION_VOCAB_PATH", str(path))
    bugsigdb_vocabulary._load.cache_clear()
    yield path
    bugsigdb_vocabulary._load.cache_clear()


@pytest.fixture
def offline(monkeypatch, vocab_file):
    """No local store, no OLS, no embedding model unless a test adds one."""
    store = LocalOntologyBackend(db_path=":memory:")
    monkeypatch.setattr(condition, "local_lookup", lambda *a, **k: None)
    monkeypatch.setattr(condition, "ols_search", lambda *a, **k: None)
    monkeypatch.setattr(condition, "local_lookup_backend", lambda: store)
    monkeypatch.setattr(embedding_match, "nearest", lambda *a, **k: [])
    monkeypatch.setattr(grounding_module, "get_cached_grounding", lambda *a: None)
    monkeypatch.setattr(
        grounding_module, "store_cached_grounding", lambda *a, **k: None
    )
    return store


# --- vocabulary ------------------------------------------------------------


def test_vocabulary_label_lookup_is_case_insensitive_on_curie():
    vocab = BugSigDBVocabulary(TERMS)
    assert vocab.label_for("mondo:0005180") == "Parkinson's disease"
    assert vocab.label_for("MONDO:9999999") is None
    assert vocab.label_for("") is None


def test_vocabulary_exact_label_match_ignores_case_and_punctuation():
    vocab = BugSigDBVocabulary(TERMS)
    assert vocab.match_label("parkinsons disease") == (
        "Parkinson's disease",
        "MONDO:0005180",
    )
    assert vocab.match_label("PARKINSON'S DISEASE")[1] == "MONDO:0005180"
    # Exact equality only - never a substring match.
    assert vocab.match_label("early Parkinson's disease") is None


def test_vocabulary_minority_label_identifies_the_id_but_majority_label_is_shown():
    vocab = BugSigDBVocabulary(TERMS)
    assert vocab.match_label("unipolar depression") == (
        "Major depressive disorder",
        "MONDO:0002009",
    )


def test_missing_vocabulary_file_fails_open(tmp_path, monkeypatch):
    monkeypatch.setenv("BUGSIGDB_CONDITION_VOCAB_PATH", str(tmp_path / "nope.json"))
    bugsigdb_vocabulary._load.cache_clear()
    try:
        assert len(bugsigdb_vocabulary.get_vocabulary()) == 0
    finally:
        bugsigdb_vocabulary._load.cache_clear()


def test_shipped_vocabulary_uses_bugsigdb_wording():
    bugsigdb_vocabulary._load.cache_clear()
    vocab = bugsigdb_vocabulary._load(str(bugsigdb_vocabulary.DEFAULT_VOCAB_PATH))
    assert len(vocab) > 800
    assert vocab.label_for("MONDO:0005180") == "Parkinson's disease"
    assert vocab.label_for("MONDO:0005148") == "Type II diabetes mellitus"


# --- normalize_condition ---------------------------------------------------


def test_static_match_keeps_its_id_and_tier_but_shows_bugsigdb_label(offline):
    term = condition.normalize_condition("Parkinson disease")
    assert term.ontology_id == "MONDO:0005180"
    assert term.label == "Parkinson's disease"
    assert term.mapping_confidence == 1.0
    assert term.raw == "Parkinson disease"


def test_relabel_applies_to_type_2_diabetes(offline):
    term = condition.normalize_condition("type 2 diabetes")
    assert (term.label, term.ontology_id) == (
        "Type II diabetes mellitus",
        "MONDO:0005148",
    )


def test_id_not_in_vocabulary_keeps_ontology_label(offline):
    term = condition.normalize_condition("asthma")  # static dict; not in TERMS
    assert (term.label, term.ontology_id) == ("asthma", "MONDO:0004979")


def test_exact_bugsigdb_label_is_used_when_nothing_else_grounds(offline):
    term = condition.normalize_condition("Health study participation")
    assert term.ontology_id == "EFO:0010130"
    assert term.status == "PRESENT"
    assert term.mapping_confidence < 1.0  # review, never auto


def test_healthy_is_never_given_an_id(offline, monkeypatch):
    monkeypatch.setattr(
        embedding_match,
        "nearest",
        lambda *a, **k: [("Health study participation", "EFO:0010130", 0.95)],
    )
    term = condition.normalize_condition("healthy")
    assert (term.label, term.ontology_id) == ("healthy", "")


def test_retired_efo_term_follows_cross_reference_to_live_mondo_term(offline):
    store = offline
    store.upsert_term(
        "efo", "EFO:0001358", "obsolete_post-traumatic stress disorder", obsolete=True
    )
    store.insert_synonym("efo", "EFO:0001358", "posttraumatic stress disorder", "exact")
    store.upsert_term("mondo", "MONDO:0005146", "post-traumatic stress disorder")
    store.insert_xref("mondo", "MONDO:0005146", "EFO:0001358")
    term = condition.normalize_condition("posttraumatic stress disorder")
    assert term.ontology_id == "MONDO:0005146"
    assert term.label == "Post-traumatic stress disorder"
    assert term.mapping_confidence == 0.85


def test_retired_term_replacement_must_be_in_bugsigdb_vocabulary(offline):
    store = offline
    store.upsert_term("efo", "EFO:0000001", "obsolete_rare thing", obsolete=True)
    store.insert_synonym("efo", "EFO:0000001", "rare thing", "exact")
    store.insert_xref("mondo", "MONDO:0000001", "EFO:0000001")  # not in TERMS
    term = condition.normalize_condition("rare thing")
    assert term.ontology_id == ""


def test_efo_id_swapped_for_equivalent_mondo_id_bugsigdb_uses(offline, monkeypatch):
    store = offline
    store.insert_xref("efo", "EFO:0001073", "MONDO:0011122")
    monkeypatch.setattr(
        condition,
        "local_lookup",
        lambda q, slugs: NormalizedTerm("obesity", "EFO:0001073", "PRESENT", 0.9),
    )
    term = condition.normalize_condition("adiposity")
    assert (term.label, term.ontology_id) == ("Obesity", "MONDO:0011122")
    assert term.mapping_confidence <= 0.9


def test_embedding_match_above_threshold_snaps_to_vocabulary_term(offline, monkeypatch):
    monkeypatch.setattr(
        embedding_match,
        "nearest",
        lambda text, k=5, vocab=None: [
            ("Food allergy", "MONDO:0700226", 0.89),
            ("Obesity", "MONDO:0011122", 0.41),
        ],
    )
    term = condition.normalize_condition("IgE-mediated food allergies")
    assert (term.label, term.ontology_id) == ("Food allergy", "MONDO:0700226")
    assert term.mapping_confidence <= 0.85
    assert term.raw == "IgE-mediated food allergies"


def test_embedding_match_below_threshold_only_offers_candidates(offline, monkeypatch):
    monkeypatch.setattr(
        embedding_match,
        "nearest",
        lambda text, k=5, vocab=None: [
            ("Food allergy", "MONDO:0700226", 0.72),
            ("Obesity", "MONDO:0011122", 0.65),
        ],
    )
    term = condition.normalize_condition("food sensitization")
    assert term.ontology_id == ""
    assert term.label == "food sensitization"
    assert ("Food allergy", "MONDO:0700226") in term.candidates


def test_embedding_match_below_floor_offers_nothing(offline, monkeypatch):
    monkeypatch.setattr(
        embedding_match,
        "nearest",
        lambda text, k=5, vocab=None: [("Obesity", "MONDO:0011122", 0.5)],
    )
    term = condition.normalize_condition("FGT inflammation")
    assert term.candidates == ()


# --- embedding_match.nearest -------------------------------------------------


class _FakeModel:
    """Embeds by a fixed lookup so cosine order is known."""

    VECTORS = {
        "Food allergy": [1.0, 0.0],
        "Obesity": [0.0, 1.0],
        "food allergies": [0.9, 0.1],
    }

    def encode(self, texts, normalize_embeddings=True, **kwargs):
        rows = np.array([self.VECTORS.get(t, [0.5, 0.5]) for t in texts], dtype=float)
        return rows / np.linalg.norm(rows, axis=1, keepdims=True)


def test_nearest_ranks_by_cosine(monkeypatch):
    monkeypatch.setenv("CONDITION_EMBEDDING_MATCH", "1")
    monkeypatch.setattr(embedding_match, "_get_model", lambda: _FakeModel())
    embedding_match._index.clear()
    vocab = BugSigDBVocabulary(
        {
            "MONDO:0700226": {"label": "Food allergy"},
            "MONDO:0011122": {"label": "Obesity"},
        }
    )
    result = embedding_match.nearest("food allergies", k=2, vocab=vocab)
    assert [curie for _, curie, _ in result] == ["MONDO:0700226", "MONDO:0011122"]
    assert result[0][2] > 0.9


def test_nearest_is_empty_when_disabled(monkeypatch):
    monkeypatch.setenv("CONDITION_EMBEDDING_MATCH", "0")
    assert embedding_match.nearest("food allergies") == []


def test_nearest_is_empty_when_model_unavailable(monkeypatch):
    monkeypatch.setenv("CONDITION_EMBEDDING_MATCH", "1")
    monkeypatch.setattr(embedding_match, "_get_model", lambda: None)
    vocab = BugSigDBVocabulary({"MONDO:0011122": {"label": "Obesity"}})
    assert embedding_match.nearest("obese", vocab=vocab) == []


# --- tiering -------------------------------------------------------------------


class _Backend:
    def __init__(self, label):
        self._label = label

    def get(self, curie, ontology):
        return GroundingCheck(exists=True, label=self._label, source="stub")

    def reachable_from(self, curie, root, ontology):
        return True

    def lookup(self, *a, **k):
        return []


def test_bugsigdb_label_for_the_same_id_is_not_a_label_mismatch(tmp_path, monkeypatch):
    path = tmp_path / "v.json"
    path.write_text(
        json.dumps({"terms": {"MONDO:0002009": {"label": "Unipolar depression"}}})
    )
    monkeypatch.setenv("BUGSIGDB_CONDITION_VOCAB_PATH", str(path))
    monkeypatch.setattr(grounding_module, "get_cached_grounding", lambda *a: None)
    monkeypatch.setattr(
        grounding_module, "store_cached_grounding", lambda *a, **k: None
    )
    bugsigdb_vocabulary._load.cache_clear()
    try:
        term = NormalizedTerm("Unipolar depression", "MONDO:0002009", "PRESENT", 1.0)
        assert (
            ground(term, backend=_Backend("major depressive disorder")).tier
            == TIER_AUTO
        )
        # A label that is NOT BugSigDB's for this ID is still caught.
        wrong = NormalizedTerm("Crohn disease", "MONDO:0002009", "PRESENT", 1.0)
        assert (
            ground(wrong, backend=_Backend("major depressive disorder")).tier
            == TIER_REVIEW
        )
    finally:
        bugsigdb_vocabulary._load.cache_clear()
