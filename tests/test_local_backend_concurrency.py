"""LocalOntologyBackend must be safe to share across threads.

The default grounding backend is one module-level instance with one DB
connection. Batch analysis runs field extraction (and so ontology grounding)
in several `asyncio.to_thread` workers at once; DuckDB refuses a second
concurrent call on a connection ("connection is busy with another call") and
a shared sqlite3 connection isn't safe either, which made papers in a batch
fail at random.
"""

import sqlite3
import threading

import pytest

from app.normalization.grounding.backend import SCOPE_EXACT
from app.normalization.grounding.local_backend import LocalOntologyBackend

THREADS = 8
ITERATIONS = 20


def _sqlite_store(path):
    # A file that already has SQLite's header makes the backend pick sqlite3.
    sqlite3.connect(path).execute("CREATE TABLE IF NOT EXISTS _probe (x)").close()
    return path


def _engines():
    engines = ["sqlite3"]
    try:
        import duckdb  # noqa: F401

        engines.append("duckdb")
    except ImportError:
        pass
    return engines


@pytest.fixture(params=_engines())
def backend(request, tmp_path):
    path = str(tmp_path / "store.db")
    if request.param == "sqlite3":
        _sqlite_store(path)
    b = LocalOntologyBackend(db_path=path)
    assert b.name == f"local:{request.param}"
    b.upsert_term("efo", "EFO:0000001", "root disease")
    b.upsert_term("efo", "EFO:0000002", "child disease")
    b.insert_synonym("efo", "EFO:0000002", "kid disease", SCOPE_EXACT)
    b.insert_edge("efo", "EFO:0000002", "is_a", "EFO:0000001")
    b.mark_complete("efo")
    yield b
    b.close()


def test_concurrent_reads_never_fail(backend):
    start = threading.Barrier(THREADS)
    errors = []

    def worker():
        start.wait()
        try:
            for _ in range(ITERATIONS):
                check = backend.get("EFO:0000002", "efo")
                assert check is not None and check.exists
                assert backend.get("EFO:9999999", "efo").exists is False
                # reachable_from swallows DB errors into None, so check the value.
                assert backend.reachable_from("EFO:0000002", "EFO:0000001", "efo")
                assert backend.lookup("kid disease", "efo")
        except Exception as e:  # collected and reported below
            errors.append(repr(e))

    threads = [threading.Thread(target=worker) for _ in range(THREADS)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert errors == [], f"{len(errors)} thread(s) failed, first: {errors[0]}"


def test_concurrent_writes_and_reads_never_fail(backend):
    start = threading.Barrier(THREADS)
    errors = []

    def worker(i):
        start.wait()
        try:
            for j in range(ITERATIONS):
                curie = f"EFO:1{i:02d}{j:04d}"
                backend.upsert_term("efo", curie, f"term {i} {j}")
                check = backend.get(curie, "efo")
                assert check is not None and check.exists
        except Exception as e:
            errors.append(repr(e))

    threads = [threading.Thread(target=worker, args=(i,)) for i in range(THREADS)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert errors == [], f"{len(errors)} thread(s) failed, first: {errors[0]}"
