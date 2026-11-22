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


class _FakeBackend:
    """Exact-scope lookup + descendant check over small in-memory tables."""

    def __init__(self, exact, parents=None):
        self.exact = exact  # normalized text -> [(curie, label)]
        self.parents = parents or {}  # curie -> {ancestor curies}

    def lookup(self, value, ontology, scopes=()):
        from app.normalization.grounding.backend import GroundedTerm

        return [
            GroundedTerm(
                curie=c, label=lbl, ontology=ontology, scope="exact", source="t"
            )
            for c, lbl in self.exact.get(value.lower().replace(",", "").strip(), [])
            if c.lower().startswith(ontology)
        ]

    def reachable_from(self, curie, root, ontology):
        return curie == root or root in self.parents.get(curie, set())

    def is_obsolete(self, curie, ontology):
        return False


@pytest.fixture
def specific_backend(vocab, monkeypatch):
    backend = _FakeBackend(
        {
            "chronic hepatitis b": [
                ("MONDO:0005366", "chronic hepatitis B virus infection")
            ],
            "type 2 diabetes mellitus": [("MONDO:0005148", "type 2 diabetes mellitus")],
            "hepatitis": [("MONDO:0002251", "hepatitis")],
            "ibd": [("MONDO:0009999", "unrelated ibd thing")],
        },
        {"MONDO:0005366": {"MONDO:0002251"}},
    )
    monkeypatch.setattr(condition, "local_lookup_backend", lambda: backend)
    monkeypatch.setattr(condition, "local_lookup", lambda *a, **k: None)
    return backend


def test_uninvert_heading():
    f = condition._uninvert_heading
    assert f("Diabetes Mellitus, Type 2") == "Type 2 Diabetes Mellitus"
    assert f("Hepatitis B, Chronic") == "Chronic Hepatitis B"
    assert f("obesity, diabetes") == "obesity, diabetes"  # list, not a heading
    assert f("a, b, chronic") == "a, b, chronic"  # more than one comma
    assert f("Hepatitis B, chronic viral") == "chronic viral Hepatitis B"
    assert f("Hepatitis C, Chronic") == "Chronic Hepatitis C"
    assert f("Diabetes Mellitus, Adult-Onset") == "Adult-Onset Diabetes Mellitus"
    assert f("Diabetes Mellitus, Type II") == "Type II Diabetes Mellitus"
    # every tail word must be a qualifier: these are lists, not headings
    assert f("obesity, type 2 diabetes") == "obesity, type 2 diabetes"
    assert f("IBS, functional constipation") == "IBS, functional constipation"
    assert f("Hepatitis B, one two three four") == "Hepatitis B, one two three four"


@pytest.mark.parametrize("text", ["chronic hepatitis B", "Hepatitis B, Chronic"])
def test_specific_disease_beats_substring_static_key(specific_backend, text):
    term = condition.normalize_condition(text)
    assert term.ontology_id == "MONDO:0005366"
    assert term.mapping_confidence < 1.0
    assert term.raw == text


def test_inverted_type2_diabetes_maps_to_specific_term(specific_backend):
    term = condition.normalize_condition("Diabetes Mellitus, Type 2")
    assert term.ontology_id == "MONDO:0005148"
    assert term.raw == "Diabetes Mellitus, Type 2"


def test_static_answers_hold_without_a_specific_descendant(specific_backend):
    # exact-key matches and an unrelated (non-descendant) exact hit keep the
    # audited static ID
    assert condition.normalize_condition("hepatitis").ontology_id == "MONDO:0002251"
    assert condition.normalize_condition("IBD").ontology_id == "MONDO:0005265"
    assert (
        condition.normalize_condition("type 2 diabetes").ontology_id == "MONDO:0005148"
    )


def test_specific_hit_needs_unique_exact_descendant(specific_backend):
    specific_backend.exact["chronic hepatitis b"].append(("MONDO:0000001", "other"))
    assert (
        condition.normalize_condition("chronic hepatitis B").ontology_id
        == "MONDO:0002251"
    )


def _ground_as(monkeypatch, curie):
    monkeypatch.setattr(
        condition,
        "_ground_condition",
        lambda raw: NormalizedTerm("grounded disease", curie, "PRESENT", 0.9),
    )
    monkeypatch.setattr(
        embedding_match,
        "nearest",
        lambda *a, **k: [("Fatty liver disease", "MONDO:0004790", 0.95)],
    )


def test_snap_records_pre_snap_term_when_prefix_used_by_vocabulary(vocab, monkeypatch):
    _ground_as(monkeypatch, "MONDO:0005354")  # not in vocab; MONDO is
    term = condition.normalize_condition("some disease")
    assert term.ontology_id == "MONDO:0004790"  # primary is the snapped term
    assert term.pre_snap == ("grounded disease", "MONDO:0005354")


def test_pre_snap_dropped_when_prefix_not_used_by_vocabulary(vocab, monkeypatch):
    _ground_as(monkeypatch, "ZZZ:0001")
    term = condition.normalize_condition("some disease")
    assert term.ontology_id == "MONDO:0004790"
    assert term.pre_snap is None


def test_no_snap_means_no_pre_snap(vocab, monkeypatch):
    _ground_as(monkeypatch, "MONDO:0004790")  # already in the vocabulary
    assert condition.normalize_condition("some disease").pre_snap is None


def test_empty_vocabulary_unchanged(monkeypatch):
    bugsigdb_vocabulary._load.cache_clear()
    monkeypatch.setenv("BUGSIGDB_CONDITION_VOCAB_PATH", "/nonexistent.json")
    monkeypatch.setattr(condition, "ols_search", lambda *a, **k: None)
    _ground_as(monkeypatch, "MONDO:0005354")
    term = condition.normalize_condition("some disease")
    assert term.ontology_id == "MONDO:0005354"
    assert term.pre_snap is None
    bugsigdb_vocabulary._load.cache_clear()
