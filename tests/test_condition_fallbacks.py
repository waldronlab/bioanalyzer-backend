"""Condition grounding fallbacks: spelling, MAFLD/MASLD aliases, "measurement"
and qualifier-stripping exact lookups, embedding model loading, snap tiering."""

from __future__ import annotations

import json
import sys
import types

import pytest

import app.normalization.condition as condition
import app.normalization.embedding_match as embedding_match
from app.normalization import bugsigdb_vocabulary
from app.normalization.grounding.tiering import TIER_REVIEW, tier_for
from app.normalization.types import NormalizedTerm, normalize_spelling

TERMS = {
    "MONDO:0013209": {"label": "Non-alcoholic fatty liver disease"},
    "MONDO:0004790": {"label": "Fatty liver disease"},
    "MONDO:0005010": {"label": "Coronary artery disease"},
    "HP:0002140": {"label": "Ischemic stroke"},
}


@pytest.fixture
def vocab(tmp_path, monkeypatch):
    path = tmp_path / "v.json"
    path.write_text(json.dumps({"terms": TERMS}))
    monkeypatch.setenv("BUGSIGDB_CONDITION_VOCAB_PATH", str(path))
    bugsigdb_vocabulary._load.cache_clear()
    monkeypatch.setattr(embedding_match, "nearest", lambda *a, **k: [])
    monkeypatch.setattr(condition, "ols_search", lambda *a, **k: None)
    monkeypatch.setattr(condition, "_is_live", lambda curie: True)
    yield
    bugsigdb_vocabulary._load.cache_clear()


@pytest.mark.parametrize(
    "british,american",
    [
        ("Ischaemic stroke", "Ischemic stroke"),
        ("iron-deficiency anaemia", "iron-deficiency anemia"),
        ("anaemic", "anemic"),
        ("oedematous", "edematous"),
        ("infectious diarrhoeal disease", "infectious diarrheal disease"),
        ("leukaemic", "leukemic"),
        ("oestrogen deficiency", "estrogen deficiency"),
        ("paediatrics", "pediatrics"),
        ("caesarean delivery", "cesarean delivery"),
        ("haemolytic uraemic", "hemolytic uraemic"),
        ("haematological", "hematological"),
        ("foetal growth", "fetal growth"),
        ("tumour", "tumor"),
    ],
)
def test_british_spelling_variants(british, american):
    assert normalize_spelling(british).lower() == american.lower()


def test_spelling_does_not_break_unrelated_words():
    for word in ("oestrus-free", "Estonia", "oesophagus"):
        assert "oestr" not in normalize_spelling(word).replace("oestrus", "")
    assert normalize_spelling("hemoglobin") == "hemoglobin"


@pytest.mark.parametrize(
    "text",
    [
        "MAFLD",
        "MASLD",
        "metabolic dysfunction-associated fatty liver disease",
        "Metabolic (dysfunction)-associated fatty liver disease".replace(
            " (dysfunction)", " dysfunction"
        ),
        "metabolic dysfunction-associated steatotic liver disease",
        "metabolic-associated fatty liver disease",
    ],
)
def test_mafld_masld_map_to_nafld_not_parent(vocab, monkeypatch, text):
    monkeypatch.setattr(condition, "local_lookup", lambda *a, **k: None)
    term = condition.normalize_condition(text)
    assert term.ontology_id == "MONDO:0013209"
    assert term.label == "Non-alcoholic fatty liver disease"


def _store(monkeypatch, entries):
    """local_lookup stub: exact match on a lowercase query -> NormalizedTerm."""
    seen = []

    def fake(query, slugs):
        seen.append(query.lower())
        hit = entries.get(query.lower())
        return NormalizedTerm(hit[0], hit[1], "PRESENT", 0.9) if hit else None

    monkeypatch.setattr(condition, "local_lookup", fake)
    return seen


def test_measurement_suffix_fallback(vocab, monkeypatch):
    _store(
        monkeypatch,
        {"smoking status measurement": ("smoking status measurement", "EFO:0006527")},
    )
    term = condition.normalize_condition("smoking status")
    assert term.ontology_id == "EFO:0006527"
    assert term.mapping_confidence < 1.0
    assert term.raw == "smoking status"


def test_qualifier_is_stripped_only_after_full_phrase_misses(vocab, monkeypatch):
    seen = _store(monkeypatch, {"periodontitis": ("periodontitis", "MONDO:0005266")})
    term = condition.normalize_condition("severe periodontitis")
    assert term.ontology_id == "MONDO:0005266"
    assert term.raw == "severe periodontitis"  # dropped qualifier stays visible
    assert term.mapping_confidence <= 0.8
    assert "severe periodontitis" in seen
    assert seen.index("severe periodontitis") < seen.index("periodontitis")


def test_entity_names_with_chronic_or_acute_match_exactly_first(vocab, monkeypatch):
    seen = _store(
        monkeypatch,
        {
            "chronic kidney disease": ("chronic kidney disease", "MONDO:0005300"),
            "kidney disease": ("kidney disease", "MONDO:0005240"),
        },
    )
    term = condition.normalize_condition("chronic kidney disease")
    assert term.ontology_id == "MONDO:0005300"
    assert "kidney disease" not in seen or seen.index("chronic kidney disease") == 0


def test_resistant_qualifier_stripped(vocab, monkeypatch):
    _store(monkeypatch, {"tuberculosis": ("tuberculosis", "MONDO:0018076")})
    term = condition.normalize_condition("drug-resistant tuberculosis")
    assert term.ontology_id == "MONDO:0018076"


def test_obsolete_fallback_hit_rejected(vocab, monkeypatch):
    _store(monkeypatch, {"periodontitis": ("periodontitis", "MONDO:0005266")})
    monkeypatch.setattr(condition, "_is_live", lambda curie: False)
    term = condition.normalize_condition("severe periodontitis")
    assert term.ontology_id == ""


def test_coronary_artery_disorder_relabelled_when_id_in_vocabulary(vocab, monkeypatch):
    _store(
        monkeypatch,
        {"coronary artery disorder": ("coronary artery disorder", "MONDO:0005010")},
    )
    term = condition.normalize_condition("coronary artery disorder")
    assert term.ontology_id == "MONDO:0005010"
    assert term.label == "Coronary artery disease"


def test_embedding_snap_is_review_tier_even_at_perfect_cosine(vocab, monkeypatch):
    monkeypatch.setattr(condition, "local_lookup", lambda *a, **k: None)
    monkeypatch.setattr(
        embedding_match,
        "nearest",
        lambda *a, **k: [("Ischemic stroke", "HP:0002140", 1.0)],
    )
    term = condition.normalize_condition("cerebral infarct xyz")
    assert term.ontology_id == "HP:0002140"
    assert term.mapping_confidence <= embedding_match.MAX_SNAP_CONFIDENCE < 1.0
    assert tier_for(term) == TIER_REVIEW


class _FakeST:
    def __init__(self, name=None, modules=None, device=None):
        self.name, self.modules = name, modules


def _install_fake_st(monkeypatch):
    calls = {}

    class Transformer:
        def __init__(self, path, max_seq_length=None):
            calls["path"] = path

        def get_word_embedding_dimension(self):
            return 768

    class Pooling:
        def __init__(self, dim, pooling_mode=None):
            calls["pooling"] = pooling_mode

    st = types.ModuleType("sentence_transformers")
    st.SentenceTransformer = _FakeST
    st.models = types.SimpleNamespace(Transformer=Transformer, Pooling=Pooling)
    monkeypatch.setitem(sys.modules, "sentence_transformers", st)
    return calls


def test_local_plain_hf_dir_uses_cls_pooling(tmp_path, monkeypatch):
    calls = _install_fake_st(monkeypatch)
    (tmp_path / "config.json").write_text("{}")
    model = embedding_match._load_model(str(tmp_path))
    assert calls["pooling"] == "cls"
    assert calls["path"] == str(tmp_path)
    assert model.modules is not None


def test_local_dir_with_st_metadata_and_hub_ids_load_as_is(tmp_path, monkeypatch):
    calls = _install_fake_st(monkeypatch)
    (tmp_path / "modules.json").write_text("[]")
    assert embedding_match._load_model(str(tmp_path)).name == str(tmp_path)
    assert embedding_match._load_model("org/some-model").name == "org/some-model"
    assert "pooling" not in calls


def test_get_model_fails_open(tmp_path, monkeypatch):
    monkeypatch.setattr(embedding_match, "_model", None)
    monkeypatch.setattr(embedding_match, "_model_failed", False)
    monkeypatch.setenv("CONDITION_EMBEDDING_MODEL", str(tmp_path / "missing"))

    def boom(name):
        raise OSError("no model")

    monkeypatch.setattr(embedding_match, "_load_model", boom)
    try:
        assert embedding_match._get_model() is None
        assert embedding_match._model_failed is True
    finally:
        monkeypatch.setattr(embedding_match, "_model_failed", False)
