"""scripts/curator_daily_pipeline.py keeps earlier papers across daily runs.

Each run skips PMIDs it has already analyzed, so its own results hold only new
papers. Writing those over the output CSV used to drop every earlier paper.
"""

import csv
import io
import json
import sys

import pytest

from scripts import curator_daily_pipeline as pipeline

HEADER = "PMID,Title,Condition\r\n"


def _rows(text):
    return list(csv.DictReader(io.StringIO(text)))


def test_merge_keeps_old_rows_and_new_rows_win():
    existing = HEADER + "1,Old one,IBD\r\n2,Old two,CRC\r\n"
    new = HEADER + "2,New two,obesity\r\n3,New three,T2D\r\n"
    merged, total = pipeline._merge_predictions(existing, new)
    assert total == 3
    assert [(r["PMID"], r["Title"]) for r in _rows(merged)] == [
        ("1", "Old one"),
        ("2", "New two"),
        ("3", "New three"),
    ]


def test_merge_uses_new_columns_and_blanks_missing_ones():
    existing = "PMID,Title\r\n1,Old one\r\n"
    new = HEADER + "2,New two,obesity\r\n"
    merged, _ = pipeline._merge_predictions(existing, new)
    rows = _rows(merged)
    assert list(rows[0].keys()) == ["PMID", "Title", "Condition"]
    assert rows[0]["Condition"] == ""


def test_merge_into_empty_existing_file():
    merged, total = pipeline._merge_predictions("", HEADER + "1,One,IBD\r\n")
    assert total == 1
    assert _rows(merged)[0]["PMID"] == "1"


# --------------------------------------------------------------------------- #
# Two daily runs end to end (API and rendering stubbed)
# --------------------------------------------------------------------------- #


class _Resp:
    def __init__(self, pmid):
        self.status_code = 200
        self._pmid = pmid

    def json(self):
        return {"pmid": self._pmid, "title": f"Paper {self._pmid}"}


@pytest.fixture
def stubbed(monkeypatch):
    requested = []

    def fake_get(url, timeout=None, headers=None):
        pmid = url.rstrip("/").rsplit("/", 1)[-1]
        requested.append(pmid)
        return _Resp(pmid)

    def fake_render(results, fmt):
        assert fmt == "curator_desk_csv"
        out = io.StringIO()
        w = csv.writer(out)
        w.writerow(["PMID", "Title"])
        for r in results:
            w.writerow([r["pmid"], r["title"]])
        return out.getvalue()

    monkeypatch.setattr(pipeline.requests, "get", fake_get)
    monkeypatch.setattr(pipeline, "render_results", fake_render)
    return requested


def _run(monkeypatch, tmp_path, pmids, *extra):
    pmids_file = tmp_path / "pmids.txt"
    pmids_file.write_text("\n".join(pmids), encoding="utf-8")
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "curator_daily_pipeline.py",
            "--pmids-file",
            str(pmids_file),
            "-o",
            str(tmp_path / "data" / "curator_predictions.csv"),
            "--state-file",
            str(tmp_path / "data" / "curator_analyzed_pmids.json"),
            *extra,
        ],
    )
    return pipeline.main()


def test_second_run_adds_new_papers_and_keeps_earlier_ones(
    monkeypatch, tmp_path, stubbed
):
    assert _run(monkeypatch, tmp_path, ["1", "2"]) == 0
    assert _run(monkeypatch, tmp_path, ["2", "3"]) == 0

    assert stubbed == ["1", "2", "3"]  # PMID 2 wasn't paid for twice
    out = (tmp_path / "data" / "curator_predictions.csv").read_text(encoding="utf-8")
    assert [r["PMID"] for r in _rows(out)] == ["1", "2", "3"]
    state = json.loads(
        (tmp_path / "data" / "curator_analyzed_pmids.json").read_text("utf-8")
    )
    assert state["analyzed_pmids"] == ["1", "2", "3"]


def test_no_merge_restores_overwrite(monkeypatch, tmp_path, stubbed):
    _run(monkeypatch, tmp_path, ["1", "2"])
    _run(monkeypatch, tmp_path, ["3"], "--no-merge")
    out = (tmp_path / "data" / "curator_predictions.csv").read_text(encoding="utf-8")
    assert [r["PMID"] for r in _rows(out)] == ["3"]


def test_run_with_nothing_new_leaves_files_alone(monkeypatch, tmp_path, stubbed):
    _run(monkeypatch, tmp_path, ["1"])
    csv_path = tmp_path / "data" / "curator_predictions.csv"
    before = csv_path.read_text(encoding="utf-8")
    assert _run(monkeypatch, tmp_path, ["1"]) == 0
    assert csv_path.read_text(encoding="utf-8") == before
