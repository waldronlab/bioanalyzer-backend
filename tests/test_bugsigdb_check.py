"""
Tests for BugSigDB PMID membership detection in app/services/bugsigdb_check.py.
"""

from pathlib import Path

import pytest

from app.services import bugsigdb_check as bc

DUMP_HEADER_COMMENT = (
    "# BugSigDB 2026-08-09_12:03_UTC, License: Creative Commons Attribution "
    "4.0 International, URL: https://bugsigdb.org"
)
DUMP_COLUMNS = "BSDB ID,Study,Study design,PMID,DOI,URL,Title"


def _write_dump(tmp_path: Path, pmid_rows, filename: str = "full_dump.csv") -> Path:
    """Write a minimal but structurally realistic BugSigDB dump: the same
    leading '#' metadata-comment line real full_dump.csv ships with, then a
    real CSV header, then one row per pmid in pmid_rows."""
    lines = [DUMP_HEADER_COMMENT, DUMP_COLUMNS]
    for i, pmid in enumerate(pmid_rows):
        lines.append(f"bsdb:{i}/1/1,Study {i},observational,{pmid},NA,NA,Title {i}")
    dump_path = tmp_path / filename
    dump_path.write_text("\n".join(lines) + "\n")
    return dump_path


@pytest.fixture(autouse=True)
def _isolate_module_state():
    """Every test gets a clean in-process PMID cache and its own dump path -
    both are module-level globals that would otherwise leak between tests."""
    original_path = bc.LOCAL_DUMP_PATH
    bc._bugsigdb_pmids = None
    bc._cache_loaded_at = 0.0
    yield
    bc.LOCAL_DUMP_PATH = original_path
    bc._bugsigdb_pmids = None
    bc._cache_loaded_at = 0.0


class TestNormalizePmid:
    def test_plain_int(self):
        assert bc.normalize_pmid(12345678) == 12345678

    def test_plain_string(self):
        assert bc.normalize_pmid("12345678") == 12345678

    def test_surrounding_whitespace(self):
        assert bc.normalize_pmid("  12345678  ") == 12345678
        assert bc.normalize_pmid("\t12345678\n") == 12345678

    def test_missing_pmid_is_none(self):
        assert bc.normalize_pmid(None) is None
        assert bc.normalize_pmid("") is None
        assert bc.normalize_pmid("   ") is None

    def test_nan_like_is_none(self):
        assert bc.normalize_pmid("NaN") is None
        assert bc.normalize_pmid(float("nan")) is None

    def test_invalid_pmid_is_none(self):
        assert bc.normalize_pmid("NA") is None
        assert bc.normalize_pmid("PMC11017998") is None
        assert bc.normalize_pmid("10.5603.mrj.99890") is None
        assert bc.normalize_pmid("not-a-pmid") is None


class TestIsInBugsigdbLocalFile:
    def test_pmid_present_returns_true(self, tmp_path):
        bc.LOCAL_DUMP_PATH = _write_dump(tmp_path, [11223344, 55667788])
        assert bc.is_in_bugsigdb(11223344) is True

    def test_pmid_absent_returns_false(self, tmp_path):
        bc.LOCAL_DUMP_PATH = _write_dump(tmp_path, [11223344])
        assert bc.is_in_bugsigdb(99999999) is False

    def test_pmid_with_whitespace_still_matches(self, tmp_path):
        bc.LOCAL_DUMP_PATH = _write_dump(tmp_path, [11223344])
        assert bc.is_in_bugsigdb("  11223344  ") is True

    def test_int_vs_string_representation(self, tmp_path):
        bc.LOCAL_DUMP_PATH = _write_dump(tmp_path, [11223344])
        assert bc.is_in_bugsigdb(11223344) is True
        assert bc.is_in_bugsigdb("11223344") is True

    def test_missing_pmid_returns_false(self, tmp_path):
        bc.LOCAL_DUMP_PATH = _write_dump(tmp_path, ["NA", 11223344])
        assert bc.is_in_bugsigdb("") is False
        assert bc.is_in_bugsigdb(None) is False

    def test_invalid_pmid_returns_false(self, tmp_path):
        bc.LOCAL_DUMP_PATH = _write_dump(tmp_path, [11223344])
        assert bc.is_in_bugsigdb("PMC11017998") is False

    def test_multiple_papers_processed_independently(self, tmp_path):
        bc.LOCAL_DUMP_PATH = _write_dump(tmp_path, [11111111, 33333333])
        results = {
            pmid: bc.is_in_bugsigdb(pmid)
            for pmid in [11111111, 22222222, 33333333, 44444444]
        }
        assert results == {
            11111111: True,
            22222222: False,
            33333333: True,
            44444444: False,
        }

    def test_true_independent_of_other_curation_fields(self, tmp_path):
        # Membership must never depend on any other BugSigDB curation field
        # having been successfully extracted for the paper - the dump row
        # itself may be otherwise sparse (as real rows often are).
        bc.LOCAL_DUMP_PATH = _write_dump(tmp_path, [11223344])
        assert bc.is_in_bugsigdb(11223344) is True

    def test_duplicate_pmid_entries_still_true(self, tmp_path):
        bc.LOCAL_DUMP_PATH = _write_dump(tmp_path, [11223344, 11223344, 11223344])
        assert bc.is_in_bugsigdb(11223344) is True
        assert bc.get_bugsigdb_pmids() == {11223344}

    def test_regression_leading_comment_line_previously_caused_false_negative(
        self, tmp_path
    ):
        """The dump's first line is a "# BugSigDB ..." metadata comment, not
        the CSV header. Before the fix, pd.read_csv(usecols=["PMID"]) raised
        ValueError on that line ("Usecols do not match columns"), the error
        was swallowed by a broad except, and get_bugsigdb_pmids() silently
        returned an empty set - so a real PMID that IS in the dump still
        came back "No"/False for every single lookup."""
        bc.LOCAL_DUMP_PATH = _write_dump(tmp_path, [30123456])
        assert bc.is_in_bugsigdb(30123456) is True


class TestGetBugsigdbPmidsCaching:
    def test_caches_between_calls(self, tmp_path):
        dump_path = _write_dump(tmp_path, [11223344])
        bc.LOCAL_DUMP_PATH = dump_path
        first = bc.get_bugsigdb_pmids()
        # Mutate the file on disk; without force_refresh the cached set
        # should still win - one dump load per batch, not one per paper.
        dump_path.write_text(DUMP_HEADER_COMMENT + "\n" + DUMP_COLUMNS + "\n")
        second = bc.get_bugsigdb_pmids()
        assert first == second == {11223344}

    def test_force_refresh_reloads(self, tmp_path):
        dump_path = _write_dump(tmp_path, [11223344])
        bc.LOCAL_DUMP_PATH = dump_path
        bc.get_bugsigdb_pmids()
        dump_path.write_text(
            "\n".join(
                [DUMP_HEADER_COMMENT, DUMP_COLUMNS, "bsdb:1,S,obs,99999999,NA,NA,T"]
            )
            + "\n"
        )
        refreshed = bc.get_bugsigdb_pmids(force_refresh=True)
        assert refreshed == {99999999}


class TestRemoteFallback:
    def test_falls_back_to_remote_when_no_local_file(self, tmp_path, monkeypatch):
        bc.LOCAL_DUMP_PATH = tmp_path / "does_not_exist.csv"

        class _Resp:
            text = "\n".join(
                [DUMP_HEADER_COMMENT, DUMP_COLUMNS, "bsdb:1,S,obs,55555555,NA,NA,T"]
            )

            def raise_for_status(self):
                pass

        monkeypatch.setattr(bc.requests, "get", lambda *a, **k: _Resp())
        assert bc.is_in_bugsigdb(55555555) is True

    def test_remote_failure_degrades_to_false(self, tmp_path, monkeypatch):
        bc.LOCAL_DUMP_PATH = tmp_path / "does_not_exist.csv"

        def _raise(*a, **k):
            raise ConnectionError("no network")

        monkeypatch.setattr(bc.requests, "get", _raise)
        assert bc.is_in_bugsigdb(12345) is False

    def test_local_file_present_but_unparseable_falls_back_to_remote(
        self, tmp_path, monkeypatch
    ):
        bad_path = tmp_path / "full_dump.csv"
        bad_path.write_text("not,a,valid,bugsigdb,dump\nwith no PMID column\n")
        bc.LOCAL_DUMP_PATH = bad_path

        class _Resp:
            text = "\n".join(
                [DUMP_HEADER_COMMENT, DUMP_COLUMNS, "bsdb:1,S,obs,66778899,NA,NA,T"]
            )

            def raise_for_status(self):
                pass

        monkeypatch.setattr(bc.requests, "get", lambda *a, **k: _Resp())
        assert bc.is_in_bugsigdb(66778899) is True
