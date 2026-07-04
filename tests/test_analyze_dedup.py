"""Tests for cross-run de-duplication of the cumulative curator_desk_csv
output (scripts.cli.BioAnalyzerCLI.analyze_papers). The output file itself
is the manifest: re-running against the same path must skip both
re-analysis and re-emission for PMIDs it already contains.
"""

import asyncio
import csv
import io
from unittest.mock import MagicMock

from scripts.cli import BioAnalyzerCLI


def _fake_analysis(pmid: str) -> dict:
    return {
        "pmid": pmid,
        "title": f"Title {pmid}",
        "journal": "J",
        "fields": {},
        "has_differential_abundance": False,
        "differential_abundance_confidence": 0.0,
        "in_bugsigdb": False,
    }


def _rows(path) -> list:
    with open(path, encoding="utf-8") as f:
        return list(csv.DictReader(f))


def test_second_run_skips_already_emitted_pmids(tmp_path, monkeypatch):
    out_path = tmp_path / "predictions.csv"
    cli = BioAnalyzerCLI()

    call_log = []

    def fake_get(url, params=None, timeout=None):
        pmid = url.rsplit("/", 1)[-1]
        call_log.append(pmid)
        resp = MagicMock()
        resp.status_code = 200
        resp.json.return_value = _fake_analysis(pmid)
        return resp

    monkeypatch.setattr("scripts.cli.requests.get", fake_get)

    asyncio.run(
        cli.analyze_papers(
            ["1", "2"], fmt="curator_desk_csv", output_file=str(out_path)
        )
    )
    assert call_log == ["1", "2"]
    rows = _rows(out_path)
    assert [r["PMID"] for r in rows] == ["1", "2"]

    call_log.clear()
    asyncio.run(
        cli.analyze_papers(
            ["2", "3"], fmt="curator_desk_csv", output_file=str(out_path)
        )
    )
    # PMID 2 was already in the file — only 3 should have been (re-)analysed.
    assert call_log == ["3"]

    rows = _rows(out_path)
    assert [r["PMID"] for r in rows] == ["1", "2", "3"]
    # Exactly one header line, even after the append.
    assert out_path.read_text().count("PMID,Year,Title") == 1


def test_nothing_new_skips_network_entirely(tmp_path, monkeypatch):
    out_path = tmp_path / "predictions.csv"
    cli = BioAnalyzerCLI()

    call_log = []

    def fake_get(url, params=None, timeout=None):
        pmid = url.rsplit("/", 1)[-1]
        call_log.append(pmid)
        resp = MagicMock()
        resp.status_code = 200
        resp.json.return_value = _fake_analysis(pmid)
        return resp

    monkeypatch.setattr("scripts.cli.requests.get", fake_get)

    asyncio.run(
        cli.analyze_papers(["1"], fmt="curator_desk_csv", output_file=str(out_path))
    )
    call_log.clear()

    asyncio.run(
        cli.analyze_papers(["1"], fmt="curator_desk_csv", output_file=str(out_path))
    )
    assert call_log == []
    assert [r["PMID"] for r in _rows(out_path)] == ["1"]


def test_refresh_bypasses_dedup_and_overwrites(tmp_path, monkeypatch):
    out_path = tmp_path / "predictions.csv"
    cli = BioAnalyzerCLI()

    def fake_get(url, params=None, timeout=None):
        pmid = url.rsplit("/", 1)[-1]
        resp = MagicMock()
        resp.status_code = 200
        resp.json.return_value = _fake_analysis(pmid)
        return resp

    monkeypatch.setattr("scripts.cli.requests.get", fake_get)

    asyncio.run(
        cli.analyze_papers(
            ["1", "2"], fmt="curator_desk_csv", output_file=str(out_path)
        )
    )
    asyncio.run(
        cli.analyze_papers(
            ["2"], fmt="curator_desk_csv", output_file=str(out_path), refresh=True
        )
    )
    # --refresh overwrites rather than appending/deduping.
    rows = _rows(out_path)
    assert [r["PMID"] for r in rows] == ["2"]


def test_deleting_output_file_starts_clean_slate(tmp_path, monkeypatch):
    out_path = tmp_path / "predictions.csv"
    cli = BioAnalyzerCLI()

    def fake_get(url, params=None, timeout=None):
        pmid = url.rsplit("/", 1)[-1]
        resp = MagicMock()
        resp.status_code = 200
        resp.json.return_value = _fake_analysis(pmid)
        return resp

    monkeypatch.setattr("scripts.cli.requests.get", fake_get)

    asyncio.run(
        cli.analyze_papers(["1"], fmt="curator_desk_csv", output_file=str(out_path))
    )
    out_path.unlink()

    asyncio.run(
        cli.analyze_papers(["1"], fmt="curator_desk_csv", output_file=str(out_path))
    )
    assert [r["PMID"] for r in _rows(out_path)] == ["1"]
