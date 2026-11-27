"""Cache DB uses WAL so concurrent reads don't block on writes."""

import sqlite3
import threading

import pytest

from app.services.cache_manager import CacheManager


def test_cache_db_is_in_wal_mode(tmp_path):
    db = tmp_path / "analysis_cache.db"
    CacheManager(cache_dir=str(tmp_path), db_path=str(db))
    with sqlite3.connect(db) as conn:
        assert conn.execute("PRAGMA journal_mode").fetchone()[0].lower() == "wal"


def _write_commits_during_open_read(db) -> None:
    reader = sqlite3.connect(db, isolation_level=None)
    writer = sqlite3.connect(db, timeout=0.5)
    try:
        reader.execute("BEGIN")
        reader.execute("SELECT COUNT(*) FROM metadata_cache").fetchone()
        # Rollback-journal mode: COMMIT needs an exclusive lock the open read
        # holds off -> "database is locked". WAL: commits immediately.
        writer.execute(
            "INSERT INTO metadata_cache (pmid, metadata, timestamp, source) "
            "VALUES ('1', '{}', 'now', 'test')"
        )
        writer.commit()
    finally:
        reader.execute("ROLLBACK")
        reader.close()
        writer.close()


def test_write_commits_while_a_read_transaction_is_open(tmp_path):
    db = tmp_path / "analysis_cache.db"
    CacheManager(cache_dir=str(tmp_path), db_path=str(db))
    _write_commits_during_open_read(db)


def test_without_wal_the_same_write_is_blocked(tmp_path):
    """Control: proves the test above actually exercises WAL."""
    db = tmp_path / "plain.db"
    with sqlite3.connect(db) as conn:
        conn.execute(
            "CREATE TABLE metadata_cache (pmid TEXT, metadata TEXT, timestamp TEXT, source TEXT)"
        )
    with pytest.raises(sqlite3.OperationalError, match="locked"):
        _write_commits_during_open_read(db)


def test_wal_failure_does_not_break_init(tmp_path, monkeypatch, caplog):
    class _FailingConn:
        def execute(self, sql):
            raise sqlite3.OperationalError("disk I/O error")

    manager = CacheManager(cache_dir=str(tmp_path), db_path=str(tmp_path / "c.db"))
    manager._enable_wal(_FailingConn())  # must not raise
    assert "Could not enable WAL" in caplog.text


def test_concurrent_writes_and_reads_succeed(tmp_path):
    manager = CacheManager(cache_dir=str(tmp_path), db_path=str(tmp_path / "c.db"))
    errors = []

    def write_and_read(i):
        try:
            assert manager.store_metadata(str(i), {"title": f"paper {i}"})
            cached = manager.get_metadata(str(i))
            assert cached["metadata"]["title"] == f"paper {i}"
        except Exception as e:  # pragma: no cover - surfaced below
            errors.append(e)

    threads = [threading.Thread(target=write_and_read, args=(i,)) for i in range(20)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert errors == []
