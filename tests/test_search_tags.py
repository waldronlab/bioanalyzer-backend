"""Search tags on condition / host_species / body_site fields."""

from unittest.mock import patch

from app.normalization.types import NormalizedTerm
from app.services.bugsigdb_analyzer import field_extraction as fe


def _term(label, oid, status="PRESENT"):
    return NormalizedTerm(
        label=label, ontology_id=oid, status=status, mapping_confidence=0.9
    )


def _primary(value, oid, status="PRESENT", raw=""):
    return {"value": value, "ontology_id": oid, "status": status, "raw": raw}


def test_split_multi_value():
    assert fe._split_multi_value("a and b, c; d ") == ["a", "b", "c", "d"]
    assert fe._split_multi_value("") == []
    assert fe._split_multi_value(None) == []
    # "and" inside a word is not a separator
    assert fe._split_multi_value("sandy soil") == ["sandy soil"]


def test_tags_primary_first_dedup_and_skip_absent():
    table = {
        "b": _term("B", "X:2"),
        "dup": _term("Primary again", "x:1"),  # same ID, different case
        "none": NormalizedTerm.absent(),
        "c": _term("C", "X:3"),
    }
    tags, _ = fe._build_search_tags(
        _primary("Primary", "X:1"), ["b", "dup", "none", "c", "b"], lambda t: table[t]
    )
    assert tags == [
        {"label": "Primary", "ontology_id": "X:1"},
        {"label": "B", "ontology_id": "X:2"},
        {"label": "C", "ontology_id": "X:3"},
    ]


def test_tags_dedup_by_label_when_no_id():
    table = {"a": _term("Diet", ""), "b": _term("diet", "")}
    tags, _ = fe._build_search_tags(
        _primary("", "", status="ABSENT"), ["a", "b"], table.get
    )
    assert tags == [{"label": "Diet", "ontology_id": ""}]


def test_tags_skip_term_on_error_and_never_raise():
    def normalizer(text):
        if text == "boom":
            raise RuntimeError("fail with key=abc")
        return _term("Ok", "X:9")

    with patch.object(fe.logger, "warning") as warn:
        tags, _ = fe._build_search_tags(
            _primary("P", "X:1"), ["boom", "fine"], normalizer
        )
    assert [t["ontology_id"] for t in tags] == ["X:1", "X:9"]
    assert warn.called


def test_single_value_not_renormalized_with_realistic_raw():
    """normalize_host_species("human").raw == "" in production, so the skip
    must compare against the raw LLM input, not term.raw."""
    calls = {"host": [], "body": [], "cond": []}

    def host(t):
        calls["host"].append(t)
        return _term("Homo sapiens", "NCBITaxon:9606")

    def body(t):
        calls["body"].append(t)
        return _term("feces", "UBERON:0001988")

    def cond(t):
        calls["cond"].append(t)
        return _term("celiac disease", "MONDO:0005130")

    payload = {
        "host_species_raw": "human",
        "body_site_raw": "feces",
        "condition_raw": "celiac disease",
        "conditions": ["celiac disease"],
    }
    with (
        patch.object(fe, "normalize_host_species", host),
        patch.object(fe, "normalize_body_site", body),
        patch.object(fe, "normalize_condition", cond),
    ):
        out = fe._field_results_from_unified_payload(payload)
    assert calls == {"host": ["human"], "body": ["feces"], "cond": ["celiac disease"]}
    assert len(out["host_species"]["tags"]) == 1


def test_split_keeps_single_word_and_multiword_phrase_together():
    assert fe._split_multi_value("small and large intestine") == [
        "small and large intestine"
    ]
    assert fe._split_multi_value("feces and saliva") == ["feces", "saliva"]
    assert fe._split_multi_value("small and large intestine, feces") == [
        "small and large intestine",
        "feces",
    ]
    assert fe._split_multi_value("Upper and lower respiratory tract") == [
        "Upper and lower respiratory tract"
    ]


def test_split_separates_ordinary_lists():
    assert fe._split_multi_value("gut and oral cavity") == ["gut", "oral cavity"]
    assert fe._split_multi_value("human and Mus musculus") == ["human", "Mus musculus"]
    assert fe._split_multi_value("feces and vaginal swab") == ["feces", "vaginal swab"]


def test_secondary_pieces_capped_and_deduped():
    calls = []

    def norm(t):
        calls.append(t)
        return _term(t, f"X:{len(calls)}")

    pieces = ["a", "A", "b", "c", "d", "e", "f", "g", "primary raw"]
    primary = {
        "status": "PRESENT",
        "value": "P",
        "ontology_id": "X:0",
        "raw": "Primary Raw",
    }
    tags, _ = fe._build_search_tags(primary, pieces, norm, "")
    assert calls == ["a", "b", "c", "d", "e"]
    assert len(tags) == 6
    assert fe._MAX_SECONDARY_TAG_PIECES == 5


def test_unified_payload_passes_cond_term_pre_snap_into_tags():
    term = NormalizedTerm(
        "Snapped", "MONDO:2", "PRESENT", 0.9, pre_snap=("Grounded", "MONDO:1")
    )
    payload = {"condition_raw": "IBD", "conditions": ["IBD"]}
    with patch.object(fe, "normalize_condition", lambda t: term):
        out = fe._field_results_from_unified_payload(payload)
    assert [t["ontology_id"] for t in out["condition"]["tags"]] == [
        "MONDO:2",
        "MONDO:1",
    ]


def test_secondary_tags_skip_absent_and_low_confidence():
    low = NormalizedTerm("Weak", "X:7", "PRESENT", 0.4)
    table = {
        "a": low,
        "b": NormalizedTerm("junk", "", "ABSENT", 0.0),
        "c": _term("C", "X:3"),
    }
    tags, _ = fe._build_search_tags(_primary("P", "X:1"), ["a", "b", "c"], table.get)
    assert [t["ontology_id"] for t in tags] == ["X:1", "X:3"]


def test_disambiguation_drops_rejected_primary_tag():
    table = {"IBD": _term("IBD", "X:1"), "Diet": _term("diet", "X:3")}
    field = {"status": "PRESENT", "value": "IBD", "ontology_id": "X:1"}
    fe._attach_search_tags(field, ["IBD", "Diet"], table.get, "IBD")
    # disambiguation switches the primary to Y
    field.update({"value": "Crohn disease", "ontology_id": "X:2"})
    fe._refresh_primary_tag(field)
    assert [t["ontology_id"] for t in field["tags"]] == ["X:2", "X:3"]
    assert "_primary_tag" not in field


def test_rejected_primary_kept_when_independently_produced():
    table = {"IBD": _term("IBD", "X:1"), "bowel disease": _term("IBD", "X:1")}
    field = {"status": "PRESENT", "value": "IBD", "ontology_id": "X:1"}
    fe._attach_search_tags(field, ["IBD", "bowel disease"], table.get, "IBD")
    field.update({"value": "Crohn disease", "ontology_id": "X:2"})
    fe._refresh_primary_tag(field)
    assert [t["ontology_id"] for t in field["tags"]] == ["X:2", "X:1"]


def test_refresh_primary_tag_puts_new_primary_first():
    field = {
        "status": "PRESENT",
        "value": "New",
        "ontology_id": "X:5",
        "tags": [
            {"label": "Old", "ontology_id": "X:1"},
            {"label": "New", "ontology_id": "X:5"},
        ],
    }
    fe._refresh_primary_tag(field)
    assert [t["ontology_id"] for t in field["tags"]] == ["X:5", "X:1"]
    fe._refresh_primary_tag({"status": "PRESENT"})  # no tags key: no-op


def test_unified_payload_builds_tags_for_three_fields():
    host = {
        "human": _term("Homo sapiens", "NCBITaxon:9606"),
        "mouse": _term("Mus musculus", "NCBITaxon:10090"),
    }
    sites = {
        "feces": _term("feces", "UBERON:0001988"),
        "saliva": _term("saliva", "UBERON:0001836"),
    }
    conds = {
        "IBD": _term("inflammatory bowel disease", "EFO:0003767"),
        "Diet": _term("diet", "EFO:0002755"),
    }
    payload = {
        "host_species_raw": "human and mouse",
        "body_site_raw": "feces, saliva",
        "condition_raw": "IBD",
        "conditions": ["IBD", "Diet"],
    }
    with (
        patch.object(
            fe,
            "normalize_host_species",
            lambda t: host[t] if t in host else host["human"],
        ),
        patch.object(fe, "normalize_body_site", lambda t: sites.get(t, sites["feces"])),
        patch.object(fe, "normalize_condition", lambda t: conds[t]),
    ):
        out = fe._field_results_from_unified_payload(payload)
    assert [t["ontology_id"] for t in out["condition"]["tags"]] == [
        "EFO:0003767",
        "EFO:0002755",
    ]
    assert [t["ontology_id"] for t in out["host_species"]["tags"]] == [
        "NCBITaxon:9606",
        "NCBITaxon:10090",
    ]
    assert [t["ontology_id"] for t in out["body_site"]["tags"]] == [
        "UBERON:0001988",
        "UBERON:0001836",
    ]
    assert "tags" not in out["sample_size"]


def test_ancestor_ontologies_and_union_with_404(monkeypatch):
    from app.normalization import ols

    assert ols.ancestor_ontologies("MONDO:1") == ["efo", "mondo"]
    assert ols.ancestor_ontologies("Orphanet:5") == ["efo", "ordo"]
    assert ols.ancestor_ontologies("UBERON:1") == ["uberon"]

    class R:
        def __init__(self, code, ids=()):
            self.status_code = code
            self._ids = ids

        def raise_for_status(self):
            pass

        def json(self):
            return {"_embedded": {"terms": [{"obo_id": i} for i in self._ids]}}

    def get(url, params=None, timeout=0):
        return R(200, ["MONDO:9"]) if "/efo/" in url else R(404)

    monkeypatch.setattr(ols.requests, "get", get)
    assert ols.fetch_ancestor_ids("MONDO:0000001") == {"MONDO:9"}
    # 404 everywhere -> unknown, not an empty (cacheable) set
    monkeypatch.setattr(ols.requests, "get", lambda *a, **k: R(404))
    assert ols.fetch_ancestor_ids("MONDO:0000001") is None


def _snapped(label, oid, pre):
    return NormalizedTerm(label, oid, "PRESENT", 0.9, pre_snap=pre)


def test_snapped_condition_gets_both_tags_in_order():
    cond = {
        "IBD": _snapped("Snapped", "MONDO:2", ("Grounded", "MONDO:1")),
        "Diet": _snapped("Snapped2", "MONDO:4", ("Grounded2", "MONDO:3")),
    }
    payload = {"condition_raw": "IBD", "conditions": ["IBD", "Diet"]}
    with patch.object(fe, "normalize_condition", lambda t: cond[t]):
        # primary comes from the same first normalization in production
        primary = cond["IBD"]
        field = {
            "status": "PRESENT",
            "value": primary.label,
            "ontology_id": primary.ontology_id,
        }
        fe._attach_search_tags(
            field, ["IBD", "Diet"], lambda t: cond[t], "IBD", primary.pre_snap
        )
    assert [t["ontology_id"] for t in field["tags"]] == [
        "MONDO:2",
        "MONDO:1",
        "MONDO:4",
        "MONDO:3",
    ]


def test_pre_snap_tag_absent_when_no_pre_snap():
    field = {"status": "PRESENT", "value": "P", "ontology_id": "X:1"}
    fe._attach_search_tags(field, ["a"], lambda t: _term("A", "X:2"), "zzz", None)
    assert [t["ontology_id"] for t in field["tags"]] == ["X:1", "X:2"]


def test_disambiguation_drops_rejected_primary_but_keeps_its_pre_snap():
    field = {"status": "PRESENT", "value": "Snapped", "ontology_id": "MONDO:2"}
    fe._attach_search_tags(
        field,
        ["IBD", "Diet"],
        lambda t: {"IBD": _term("Snapped", "MONDO:2"), "Diet": _term("diet", "EFO:9")}[
            t
        ],
        "IBD",
        ("Grounded", "MONDO:1"),
    )
    assert [t["ontology_id"] for t in field["tags"]] == ["MONDO:2", "MONDO:1", "EFO:9"]
    field.update({"value": "Chosen", "ontology_id": "MONDO:7"})
    fe._refresh_primary_tag(field)
    assert [t["ontology_id"] for t in field["tags"]] == ["MONDO:7", "MONDO:1", "EFO:9"]


def test_unchanged_primary_keeps_pre_snap_tag_once():
    field = {"status": "PRESENT", "value": "Snapped", "ontology_id": "MONDO:2"}
    fe._attach_search_tags(field, [], lambda t: None, "IBD", ("Grounded", "MONDO:1"))
    fe._refresh_primary_tag(field)
    assert [t["ontology_id"] for t in field["tags"]] == ["MONDO:2", "MONDO:1"]


def test_pre_snap_kept_when_secondary_independently_produces_it():
    field = {"status": "PRESENT", "value": "Snapped", "ontology_id": "MONDO:2"}
    fe._attach_search_tags(
        field,
        ["other"],
        lambda t: _term("Grounded", "MONDO:1"),
        "IBD",
        ("Grounded", "MONDO:1"),
    )
    field.update({"value": "Chosen", "ontology_id": "MONDO:7"})
    fe._refresh_primary_tag(field)
    assert [t["ontology_id"] for t in field["tags"]] == ["MONDO:7", "MONDO:1"]


def test_vocabulary_prefixes_derived_from_loaded_terms():
    from app.normalization.bugsigdb_vocabulary import BugSigDBVocabulary

    v = BugSigDBVocabulary({"MONDO:1": {"label": "a"}, "efo:2": {"label": "b"}})
    assert v.prefixes() == frozenset({"MONDO", "EFO"})
    assert BugSigDBVocabulary({}).prefixes() == frozenset()


def test_obo_iri_canonical_prefix_and_orphanet_iri(monkeypatch):
    from app.normalization import ols

    assert ols._obo_iri("NCBITAXON:9606").endswith("/NCBITaxon_9606")
    urls = []

    class R:
        status_code = 200

        def raise_for_status(self):
            pass

        def json(self):
            return {"_embedded": {"terms": []}}

    monkeypatch.setattr(ols.requests, "get", lambda url, **k: urls.append(url) or R())
    ols.fetch_ancestor_ids("Orphanet:123")
    assert urls and all(
        "orpha.net" in u
        or "orpha.net"
        in __import__("urllib.parse").parse.unquote(
            __import__("urllib.parse").parse.unquote(u)
        )
        for u in urls
    )
