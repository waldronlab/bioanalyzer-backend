"""search-recall subcommand of scripts/eval/bugsigdb_ground_truth_benchmark.py."""

import csv
import importlib.util
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
_spec = importlib.util.spec_from_file_location(
    "bugsigdb_ground_truth_benchmark_sr",
    ROOT / "scripts" / "eval" / "bugsigdb_ground_truth_benchmark.py",
)
gtb = importlib.util.module_from_spec(_spec)
sys.modules[_spec.name] = gtb
_spec.loader.exec_module(gtb)

ANCESTORS = {
    "MONDO:2": {"MONDO:1"},  # MONDO:1 is a general term above MONDO:2
    "NCBITAXON:9606": {"NCBITAXON:9605"},
}


def _cache():
    return gtb.AncestorCache(None, fetcher=lambda c: ANCESTORS.get(c.upper(), set()))


def _field(value, oid, tags=None):
    d = {"value": value, "ontology_id": oid, "status": "PRESENT"}
    if tags is not None:
        d["tags"] = [{"label": lab, "ontology_id": i} for lab, i in tags]
    return d


def _result(pmid, cond, host, body):
    return {
        "pmid": pmid,
        "fields": {"condition": cond, "host_species": host, "body_site": body},
    }


def _gt(**kw):
    base = {
        "host_species": [],
        "body_site_labels": [],
        "body_site_ids": [],
        "condition_labels": [],
        "condition_ids": [],
    }
    base.update(kw)
    return base


def _host(label):
    return {"homo sapiens": "NCBITaxon:9606"}.get(label, "")


def _run(results, gt, **kw):
    return gtb.compute_search_recall(results, gt, _cache(), host_resolver=_host, **kw)


def test_top1_vs_tags_exact_vs_hierarchy():
    results = {
        "1": _result(
            "1",
            _field("x", "MONDO:9", [("x", "MONDO:9"), ("y", "MONDO:3")]),
            _field("", ""),
            _field("", ""),
        ),
        "2": _result("2", _field("z", "MONDO:2"), _field("", ""), _field("", "")),
    }
    gt = {
        "1": _gt(condition_ids=["MONDO:3"]),  # only in secondary tag
        "2": _gt(condition_ids=["MONDO:1"]),  # ancestor of predicted
    }
    counts, misses = _run(results, gt)
    c = counts["condition"]
    assert c == {"n": 2, "top1": 0, "tags_exact": 1, "tags_hierarchy": 2}
    assert misses == []


def test_missing_paper_is_a_miss_and_denominator_counts_it():
    gt = {"7": _gt(condition_ids=["MONDO:1"], condition_labels=["ibd"])}
    counts, misses = _run({}, gt)
    assert counts["condition"]["n"] == 1
    assert counts["condition"]["tags_hierarchy"] == 0
    assert misses[0]["PMID"] == "7"
    assert "missing" in misses[0]["predicted_tags"]


def test_any_of_multiple_curated_ids_counts():
    results = {
        "1": _result(
            "1",
            _field("a", "MONDO:5", [("a", "MONDO:5")]),
            _field("", ""),
            _field("", ""),
        )
    }
    gt = {"1": _gt(condition_ids=["MONDO:8", "MONDO:5", "MONDO:6"])}
    counts, _ = _run(results, gt)
    assert counts["condition"]["tags_exact"] == 1


def test_label_fallback_counts_within_exact():
    results = {
        "1": _result(
            "1",
            _field("Parkinson's Disease", "", [("Parkinson's Disease", "")]),
            _field("", ""),
            _field("", ""),
        )
    }
    gt = {"1": _gt(condition_labels=["parkinson's disease"])}
    counts, _ = _run(results, gt)
    assert counts["condition"]["tags_exact"] == 1


def test_papers_without_curated_value_not_in_denominator_and_all_requires_three():
    results = {
        "1": _result(
            "1",
            _field("c", "MONDO:1"),
            _field("Homo sapiens", "NCBITaxon:9606"),
            _field("feces", "UBERON:1"),
        )
    }
    gt = {
        "1": _gt(
            condition_ids=["MONDO:1"],
            host_species=["homo sapiens"],
            body_site_ids=["UBERON:1"],
        ),
        "2": _gt(condition_ids=["MONDO:1"]),  # only condition curated
    }
    counts, _ = _run(results, gt)
    assert counts["host_species"]["n"] == 1
    assert counts["body_site"]["n"] == 1
    assert counts["condition"]["n"] == 2
    assert counts["all"] == {"n": 1, "top1": 1, "tags_exact": 1, "tags_hierarchy": 1}


def test_host_species_hierarchy_via_mapped_ncbitaxon():
    results = {
        "1": _result(
            "1",
            _field("", ""),
            _field("Homo sapiens", "NCBITaxon:9606"),
            _field("", ""),
        )
    }
    gt = {"1": _gt(host_species=["homo sapiens"])}
    counts, _ = _run(results, gt)
    assert counts["host_species"]["tags_exact"] == 1


def test_ancestor_cache_roundtrip_offline(tmp_path):
    path = tmp_path / "anc.json"
    calls = []

    def fetch(c):
        calls.append(c)
        return {"MONDO:1"}

    cache = gtb.AncestorCache(path, fetcher=fetch)
    assert cache.ancestors("MONDO:2") == {"MONDO:1"}
    cache.save()
    cache2 = gtb.AncestorCache(path, fetcher=lambda c: calls.append("again"))
    assert cache2.ancestors("mondo:2") == {"MONDO:1"}
    assert calls == ["MONDO:2"]


def test_failed_ancestor_lookup_not_cached():
    cache = gtb.AncestorCache(None, fetcher=lambda c: None)
    assert cache.ancestors("MONDO:2") == set()
    assert cache._data == {}


def test_failed_lookup_not_requeried_within_a_run_nor_persisted(tmp_path):
    calls = []
    path = tmp_path / "anc.json"
    cache = gtb.AncestorCache(path, fetcher=lambda c: calls.append(c))  # -> None
    for _ in range(3):
        assert cache.ancestors("MONDO:2") == set()
    assert calls == ["MONDO:2"]
    cache.save()
    assert not path.exists()


def test_ancestor_fetch_uses_original_case_curie():
    calls = []

    def fetch(c):
        calls.append(c)
        return {"NCBITaxon:9605"}

    results = {
        "1": _result(
            "1",
            _field("", ""),
            _field(
                "Homo sapiens", "NCBITaxon:9606", [("Homo sapiens", "NCBITaxon:9606")]
            ),
            _field("", ""),
        )
    }
    gt = {"1": _gt(host_species=["homo"])}
    cache = gtb.AncestorCache(None, fetcher=fetch)
    gtb.compute_search_recall(
        results, gt, cache, host_resolver=lambda label: "NCBITaxon:9605"
    )
    assert calls == ["NCBITaxon:9606"]


def test_cmd_writes_outputs(tmp_path, monkeypatch):
    res = tmp_path / "r.json"
    res.write_text(
        json.dumps(
            [_result("1", _field("c", "MONDO:2"), _field("", ""), _field("", ""))]
        )
    )
    gtp = tmp_path / "gt.json"
    gtp.write_text(
        json.dumps(
            {"1": _gt(condition_ids=["MONDO:1"]), "2": _gt(condition_ids=["MONDO:4"])}
        )
    )
    monkeypatch.setattr(gtb, "_ANCESTOR_SLEEP_SECONDS", 0)
    import app.normalization.ols as ols

    monkeypatch.setattr(
        ols, "fetch_ancestor_ids", lambda c: ANCESTORS.get(c.upper(), set())
    )
    args = gtb.argparse.Namespace(
        results=str(res),
        ground_truth=str(gtp),
        out=str(tmp_path / "out"),
        ancestor_cache=str(tmp_path / "anc.json"),
        synonym_scoring=False,
    )
    assert gtb.cmd_search_recall(args) == 0
    out = tmp_path / "out"
    rows = list(csv.DictReader(open(out / "summary.csv")))
    cond = [r for r in rows if r["field"] == "condition"][0]
    assert cond["n_papers"] == "2" and cond["hits_tags_hierarchy"] == "1"
    assert (out / "summary.md").exists()
    assert len(list(csv.DictReader(open(out / "misses.csv")))) == 1


def test_results_without_tags_key_are_counted():
    results = {
        "1": _result("1", _field("c", "MONDO:2"), _field("", ""), _field("", "")),
        "2": _result(
            "2",
            _field("c", "MONDO:2", [("c", "MONDO:2")]),
            _field("", ""),
            _field("", ""),
        ),
    }
    gt = {"1": _gt(condition_ids=["MONDO:2"]), "2": _gt(condition_ids=["MONDO:2"])}
    counts, _ = _run(results, gt)
    assert counts["_meta"]["results_without_tags"] == 1


def test_host_resolver_memoized_and_failures_counted():
    calls = []

    def resolver(label):
        calls.append(label)
        raise RuntimeError("boom")

    results = {}
    gt = {str(i): _gt(host_species=["homo sapiens"]) for i in range(3)}
    counts, _ = gtb.compute_search_recall(results, gt, _cache(), host_resolver=resolver)
    assert calls == ["homo sapiens"]
    assert counts["_meta"]["unresolved_host_labels"] == 1


def test_top1_uses_same_synonym_rule(monkeypatch):
    monkeypatch.setattr(gtb, "_ontology_equivalent", lambda f, p, g: True)
    results = {
        "1": _result(
            "1", _field("Parkinson disease", ""), _field("", ""), _field("", "")
        )
    }
    gt = {"1": _gt(condition_labels=["parkinson's disease"])}
    counts, _ = _run(results, gt, synonym_scoring=True)
    assert counts["condition"]["top1"] == 1
    counts, _ = _run(results, gt, synonym_scoring=False)
    assert counts["condition"]["top1"] == 0
