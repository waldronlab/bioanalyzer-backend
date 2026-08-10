"""GroundingBackend backed by a local, offline ontology store.

Projects semantic-sql data into this table shape:

    terms(ontology, curie, label, definition, obsolete, replaced_by, version)
    synonyms(ontology, curie, synonym, scope)      # scope: exact|broad|narrow|related
    edges(ontology, subject, predicate, object)    # asserted direct edges (is_a, part_of, ...)

plus one table this backend needs beyond that shape:

    ontology_meta(ontology, complete, term_count, source, version, updated_at)

`complete` is the fix for a real correctness bug found in a 2026-08 audit of
the first version of this module: `get()`/`reachable_from()` used to report
"doesn't exist" / "not reachable" for *any* curie missing from a partially-
seeded ontology, which is only true for an ontology this store holds a
*complete* copy of. For a partial store (e.g. the ~50-term static-dict seed
- see `seed.py`), "not found here" means "unknown", not "confirmed absent" -
returning a hard negative for an ontology this store never claimed to fully
cover would make `ChainedBackend` short-circuit on a false answer instead of
falling through to a backend that actually knows. `mark_complete()` is
called by `seed.ensure_ontology()` once a real full-ontology import
succeeds; `build_seed_store()` deliberately does not call it, since the
static-dict seed was never meant to be a complete ontology copy.

Branch-check ancestry is computed on demand - not a materialized closure
table - via an application-level BFS (`_bfs_edges_from`) issuing one
indexed `subject IN (...)` query per frontier level, with an explicit
`visited` set as the cycle guard/dedup. This replaced a single `WITH
RECURSIVE` SQL query (this module's original approach) after a 2026-08 perf
audit found it took 4-12 seconds per check against NCBITaxon's real
2.7M-edge table: `EXPLAIN QUERY PLAN` showed the recursive step's join only
binds the `ontology` half of `idx_edges_subject`, not `subject` too, so
each hop nested-loop-scanned the whole ontology's edges instead of seeking
- a SQLite limitation with correlated index seeks inside a recursive CTE's
join that `INDEXED BY` does not fix (confirmed empirically). The BFS
version's per-level queries aren't correlated the same way, so they seek
the composite index correctly - the identical NCBITaxon lookup that took
~9s went to <5ms. Also, unlike a naive single-parent walk, the explicit
BFS frontier correctly handles multi-parent DAGs (a term with more than
one `is_a`/`part_of` parent), which a linear walk would silently miss.

Matching is done in SQL against an indexed, precomputed `label_normalized`/
`synonym_normalized` column, not by pulling every row for an ontology into
Python and normalizing each one at query time. The first version of this
module did the latter - fine at 50 seed rows, a full O(n) table scan per
lookup at the scale a real ontology import (`ensure_ontology()`) actually
produces (EFO/MONDO/UBERON are ~20k-200k rows each; NCBITaxon is ~2M).

Storage engine: DuckDB if installed - a real
embedded analytical database, better suited to scanning a multi-thousand-row
ontology projection), transparently falling back to Python's stdlib
`sqlite3` if it isn't. Both are queried through the exact same plain SQL
(standard joins, `IN (...)`, `?` placeholders) - the engine choice is an
implementation detail behind this class, never something a caller needs to
know about. `duckdb` is declared in requirements.txt but imported lazily
here, so a missing/failed install degrades to the always-available sqlite3
path rather than breaking import of this module.
"""

from __future__ import annotations

import logging
import os
import re
from datetime import datetime, timezone
from typing import Any, List, Optional, Tuple

from app.normalization.grounding.backend import (
    SCOPE_EXACT,
    GroundedTerm,
    GroundingCheck,
)
from app.utils.credential_masking import mask_exception_message

logger = logging.getLogger(__name__)

DEFAULT_DB_PATH = os.getenv(
    "LOCAL_ONTOLOGY_DB_PATH", os.path.join("ontology_store", "ontology_store.db")
)

_SCHEMA = """
CREATE TABLE IF NOT EXISTS terms (
    ontology TEXT NOT NULL,
    curie TEXT NOT NULL,
    label TEXT,
    label_normalized TEXT,
    definition TEXT,
    obsolete INTEGER DEFAULT 0,
    replaced_by TEXT,
    version TEXT,
    PRIMARY KEY (ontology, curie)
);
CREATE TABLE IF NOT EXISTS synonyms (
    ontology TEXT NOT NULL,
    curie TEXT NOT NULL,
    synonym TEXT NOT NULL,
    synonym_normalized TEXT,
    scope TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS edges (
    ontology TEXT NOT NULL,
    subject TEXT NOT NULL,
    predicate TEXT NOT NULL,
    object TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS ontology_meta (
    ontology TEXT PRIMARY KEY,
    complete INTEGER DEFAULT 0,
    term_count INTEGER DEFAULT 0,
    source TEXT,
    version TEXT,
    updated_at TEXT
);
CREATE TABLE IF NOT EXISTS xrefs (
    ontology TEXT NOT NULL,
    curie TEXT NOT NULL,
    xref TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_terms_label_norm ON terms(ontology, label_normalized);
CREATE INDEX IF NOT EXISTS idx_synonyms_norm ON synonyms(ontology, synonym_normalized);
CREATE INDEX IF NOT EXISTS idx_edges_subject ON edges(ontology, subject);
CREATE INDEX IF NOT EXISTS idx_xrefs_curie ON xrefs(ontology, curie);
CREATE INDEX IF NOT EXISTS idx_xrefs_xref ON xrefs(xref);
"""

# Ancestors were originally computed with a single `WITH RECURSIVE` query
# (this module's original approach) - correct, but a real 2026-08 perf audit found
# it takes 4-12 SECONDS per branch-check against NCBITaxon's real 2.7M-edge
# table (verified: EXPLAIN QUERY PLAN shows the recursive step's join only
# binds the `ontology` half of idx_edges_subject - `SEARCH e USING INDEX
# idx_edges_subject (ontology=?)`, not `(ontology=? AND subject=?)` - so
# each hop nested-loop-scans the whole ontology's edge rows instead of
# seeking. `INDEXED BY idx_edges_subject` does not change this - confirmed
# empirically, same plan, same ~9s. This is a known SQLite limitation with
# correlated index seeks inside a recursive CTE's join, not something a
# query hint fixes.
#
# Fixed by replacing the single SQL recursion with an application-level
# BFS (_bfs_edges_from below) that issues one indexed, non-recursive query
# per frontier level (`subject IN (...)`, which *does* seek the composite
# index correctly - confirmed against the same data, <1ms for a 29-hop
# NCBITaxon chain). Portable across both engines since it's ordinary SQL,
# not engine-specific tuning. Explicit `visited`-set dedup replaces the old
# UNION-as-cycle-guard trick and also correctly handles multi-parent DAGs
# (a term with >1 `is_a`/`part_of` parent), which a single linear walk
# would have missed.
_EDGE_QUERY_CHUNK = 500


def _bfs_edges_from(db: "_Connection", ontology: str, start: str, target: str) -> bool:
    frontier = {start}
    visited = {start}
    # A real ontology's is_a/part_of depth from any term to its top-level
    # root never approaches this; it's a runaway-graph safety cap, not a
    # tuned expectation (confirmed: NCBITaxon's deepest species-to-root
    # chains are ~30 hops).
    for _ in range(500):
        if not frontier:
            return False
        next_frontier: set = set()
        frontier_list = list(frontier)
        for i in range(0, len(frontier_list), _EDGE_QUERY_CHUNK):
            chunk = frontier_list[i : i + _EDGE_QUERY_CHUNK]
            placeholders = ", ".join("?" for _ in chunk)
            rows = db.execute(
                # nosec B608 - `placeholders` is just a `?`-per-chunk-item
                # count string (see the line above), never a value; every
                # real value (`ontology`, each `chunk` item) is passed
                # through the parameterized tuple below, not interpolated.
                f"SELECT object FROM edges WHERE ontology = ? AND subject IN ({placeholders})",  # nosec B608
                (ontology, *chunk),
            )
            for (obj,) in rows:
                if obj == target:
                    return True
                if obj not in visited:
                    visited.add(obj)
                    next_frontier.add(obj)
        frontier = next_frontier
    return False


def normalize(value: str) -> str:
    """Casefold, trim, collapse whitespace/punctuation - the "normalize the
    value" half of the lookup step. Public (no
    leading underscore) because callers writing into this store (`seed.py`)
    need to precompute the same normalization the query side matches
    against - keeping it as one function used by both sides is what makes
    the indexed-column approach correct instead of just fast."""
    value = value.strip().casefold()
    value = re.sub(r"[\s_-]+", " ", value)
    value = re.sub(r"[^\w\s]", "", value)
    return value.strip()


class _Connection:
    """Uniform execute/fetch surface over sqlite3 or duckdb, so
    LocalOntologyBackend's query methods don't need to know which engine is
    live. Not a general-purpose DB-API shim - just the handful of calls this
    module makes."""

    def __init__(self, db_path: str):
        self.engine, self._conn = self._connect(db_path)
        self._init_schema()

    @staticmethod
    def _connect(db_path: str) -> Tuple[str, Any]:
        if db_path != ":memory:":
            parent = os.path.dirname(db_path)
            if parent:
                os.makedirs(parent, exist_ok=True)
        try:
            import duckdb  # optional, lazy - see module docstring

            return "duckdb", duckdb.connect(db_path)
        except ImportError:
            import sqlite3

            try:
                conn = sqlite3.connect(db_path, check_same_thread=False)
                # sqlite3.connect() is lazy - it doesn't read the file at
                # all until a query touches real page data. "SELECT 1" is a
                # constant expression and doesn't count (verified: it does
                # NOT catch a DuckDB-formatted file - the failure only
                # surfaced later, from _init_schema's CREATE TABLE).
                # sqlite_master is what every SQLite file has and only a
                # SQLite file can serve, so this forces the real check now.
                conn.execute("SELECT name FROM sqlite_master LIMIT 1")
                return "sqlite3", conn
            except sqlite3.DatabaseError as e:
                # A DuckDB-written file and a SQLite-written file are NOT
                # interchangeable on disk, despite this class presenting one
                # SQL surface over either - found empirically running
                # scripts/ontology_sync.py against a store built with
                # duckdb available, then read back without it installed:
                # sqlite3 fails with the unhelpful "file is not a database"
                # for what is actually "this file is a real DuckDB
                # database, just not one you can open right now". Re-raise
                # with the actual, actionable explanation instead.
                if db_path != ":memory:" and os.path.exists(db_path):
                    raise RuntimeError(
                        f"Cannot open {db_path!r} with sqlite3 ({e}). If this "
                        "store was built while `duckdb` was installed (its "
                        "default engine - see this module's docstring), the "
                        "file is in DuckDB's format, not SQLite's, and can "
                        "only be read back with duckdb installed. Install "
                        "duckdb, or delete this file and let it rebuild "
                        "(seed data is free; ensure_ontology() data will "
                        "need re-syncing)."
                    ) from e
                raise

    def _init_schema(self) -> None:
        for statement in _SCHEMA.strip().split(";"):
            statement = statement.strip()
            if statement:
                self._conn.execute(statement)
        if self.engine == "sqlite3":
            self._conn.commit()

    def execute(self, sql: str, params: tuple = ()) -> List[tuple]:
        cursor = self._conn.execute(sql, params)
        return cursor.fetchall()

    def executemany(self, sql: str, rows: List[tuple]) -> None:
        self._conn.executemany(sql, rows)
        if self.engine == "sqlite3":
            self._conn.commit()

    def commit(self) -> None:
        if self.engine == "sqlite3":
            self._conn.commit()
        # DuckDB autocommits outside an explicit transaction block.

    def close(self) -> None:
        self._conn.close()


class LocalOntologyBackend:
    """Offline GroundingBackend over a local terms/synonyms/edges store.

    Deterministic and reproducible by construction: given the same database
    file, every query returns the same answer every time, with no network
    call and no dependency on a third-party service's uptime - a property
    this design centers on and the live-OLS-only `OLSBackend`
    cannot offer. See `seed.py` for how this store gets populated.

    Write methods (`upsert_term`/`insert_synonym`/`insert_edge`/
    `mark_complete`) are the only supported way to populate this store -
    `seed.py` uses these, not the underlying `_db` connection directly
    (an earlier version had `seed.py` reach into `_db.execute()` itself,
    which meant the only code that knew this store's schema was scattered
    across two files instead of owned by one).
    """

    def __init__(self, db_path: str = DEFAULT_DB_PATH):
        self.db_path = db_path
        self._db = _Connection(db_path)

    @property
    def name(self) -> str:
        return f"local:{self._db.engine}"

    # ------------------------------------------------------------------
    # Write API
    # ------------------------------------------------------------------

    def upsert_term(
        self,
        ontology: str,
        curie: str,
        label: str,
        *,
        obsolete: bool = False,
        replaced_by: str = "",
        version: str = "",
        definition: str = "",
    ) -> None:
        self._db.execute(
            "INSERT OR REPLACE INTO terms "
            "(ontology, curie, label, label_normalized, definition, obsolete, "
            " replaced_by, version) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (
                ontology,
                curie,
                label,
                normalize(label),
                definition,
                int(obsolete),
                replaced_by,
                version,
            ),
        )

    def insert_synonym(
        self, ontology: str, curie: str, synonym: str, scope: str
    ) -> None:
        self._db.execute(
            "INSERT INTO synonyms (ontology, curie, synonym, synonym_normalized, scope) "
            "VALUES (?, ?, ?, ?, ?)",
            (ontology, curie, synonym, normalize(synonym), scope),
        )

    def insert_edge(
        self, ontology: str, subject: str, predicate: str, obj: str
    ) -> None:
        self._db.execute(
            "INSERT INTO edges (ontology, subject, predicate, object) "
            "SELECT ?, ?, ?, ? WHERE NOT EXISTS ("
            "  SELECT 1 FROM edges WHERE ontology = ? AND subject = ? "
            "  AND predicate = ? AND object = ?)",
            (ontology, subject, predicate, obj, ontology, subject, predicate, obj),
        )

    def bulk_upsert_terms(
        self, ontology: str, rows: List[Tuple[str, str, bool, str, str]]
    ) -> None:
        """Batch form of `upsert_term()` - *rows* is
        ``(curie, label, obsolete, replaced_by, version)`` tuples. Real
        ontology imports (`seed.ensure_ontology()`) are tens of thousands to
        millions of terms; one `execute()` call per row (interpreter +
        query-parse overhead each time) is the difference between seconds
        and hours at that scale - this is the fix for a scalability defect
        found in the 2026-08 audit of this module's first version, which
        only ever wrote one row at a time."""
        self._db.executemany(
            "INSERT OR REPLACE INTO terms "
            "(ontology, curie, label, label_normalized, obsolete, replaced_by, version) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            [
                (
                    ontology,
                    curie,
                    label,
                    normalize(label),
                    int(obsolete),
                    replaced_by,
                    version,
                )
                for curie, label, obsolete, replaced_by, version in rows
            ],
        )

    def bulk_insert_synonyms(
        self, ontology: str, rows: List[Tuple[str, str, str]]
    ) -> None:
        """Batch form of `insert_synonym()` - *rows* is
        ``(curie, synonym, scope)`` tuples."""
        self._db.executemany(
            "INSERT INTO synonyms (ontology, curie, synonym, synonym_normalized, scope) "
            "VALUES (?, ?, ?, ?, ?)",
            [
                (ontology, curie, synonym, normalize(synonym), scope)
                for curie, synonym, scope in rows
            ],
        )

    def bulk_insert_edges(
        self, ontology: str, rows: List[Tuple[str, str, str]]
    ) -> None:
        """Batch form of `insert_edge()` - *rows* is
        ``(subject, predicate, object)`` tuples. Unlike `insert_edge()`,
        does not de-duplicate against existing rows per-insert (that
        `NOT EXISTS` subquery is itself an O(n) cost not worth paying per
        row at bulk scale) - callers doing a bulk load into a fresh/cleared
        ontology don't need it; `build_seed_store()`'s much smaller,
        idempotency-sensitive writes still go through `insert_edge()`."""
        self._db.executemany(
            "INSERT INTO edges (ontology, subject, predicate, object) VALUES (?, ?, ?, ?)",
            [(ontology, subject, predicate, obj) for subject, predicate, obj in rows],
        )

    def insert_xref(self, ontology: str, curie: str, xref: str) -> None:
        self._db.execute(
            "INSERT INTO xrefs (ontology, curie, xref) SELECT ?, ?, ? WHERE NOT EXISTS ("
            "  SELECT 1 FROM xrefs WHERE ontology = ? AND curie = ? AND xref = ?)",
            (ontology, curie, xref, ontology, curie, xref),
        )

    def bulk_insert_xrefs(self, ontology: str, rows: List[Tuple[str, str]]) -> None:
        """Batch form of `insert_xref()` - *rows* is ``(curie, xref)``
        tuples, projected from semantic-sql's `has_dbxref_statement` view
        (`oio:hasDbXref`). Most xref values point to external vocabularies
        this store has no data for (Wikipedia URLs, ICD codes, Getty TGN,
        ...) and are still stored as-is - `get_xrefs()`'s caller decides
        what to do with an unrecognized prefix, this layer doesn't filter."""
        self._db.executemany(
            "INSERT INTO xrefs (ontology, curie, xref) VALUES (?, ?, ?)",
            [(ontology, curie, xref) for curie, xref in rows],
        )

    def get_xrefs(self, ontology: str, curie: str) -> List[str]:
        return [
            row[0]
            for row in self._db.execute(
                "SELECT xref FROM xrefs WHERE ontology = ? AND curie = ?",
                (ontology, curie),
            )
        ]

    def clear_ontology(self, ontology: str) -> None:
        """Delete every terms/synonyms/edges/xrefs row for *ontology* -
        called by `seed.ensure_ontology()` right before writing a fresh
        full import.

        Real bug found in a 2026-08 full-sync validation pass: `terms` uses
        `INSERT OR REPLACE` (safe to re-run), but `insert_synonym`/
        `insert_edge`/`bulk_insert_synonyms`/`bulk_insert_edges` are plain
        `INSERT` with no per-ontology clear - re-running `ensure_ontology()`
        against an ontology it had already fully synced (e.g. retrying a
        transient failure, or picking up a newer release) silently
        accumulated duplicate rows on top of the old ones instead of
        replacing them. Caught empirically: DOID's real store had 3x
        duplicate synonym/edge rows (67,875 raw / 22,625 distinct) after
        being synced multiple times across one session; HP and MONDO had
        the same issue at 3x/2x respectively. `clear_ontology()` makes a
        full re-sync an actual replace, matching what `ensure_ontology()`'s
        own docstring already claimed ("safe to re-run... overwrites,
        doesn't duplicate") but didn't, until this fix, actually do for
        synonyms/edges. Does not touch `ontology_meta` - `mark_complete()`
        overwrites that row directly via `INSERT OR REPLACE`."""
        for table in ("terms", "synonyms", "edges", "xrefs"):
            # `table` iterates a fixed, hardcoded literal tuple immediately
            # above, never external/user input; the real value (`ontology`)
            # is parameterized.
            query = f"DELETE FROM {table} WHERE ontology = ?"  # nosec B608
            self._db.execute(query, (ontology,))
        self.commit()

    def mark_complete(
        self, ontology: str, *, source: str = "", version: str = ""
    ) -> None:
        """Record that this store holds a *complete* copy of *ontology* -
        see module docstring for why this matters to get()/reachable_from().
        Call only after a real full-ontology import succeeds
        (`seed.ensure_ontology()`); never from `build_seed_store()`."""
        count = self._db.execute(
            "SELECT COUNT(*) FROM terms WHERE ontology = ?", (ontology,)
        )[0][0]
        self._db.execute(
            "INSERT OR REPLACE INTO ontology_meta "
            "(ontology, complete, term_count, source, version, updated_at) "
            "VALUES (?, 1, ?, ?, ?, ?)",
            (ontology, count, source, version, datetime.now(timezone.utc).isoformat()),
        )
        self.commit()

    def is_complete(self, ontology: str) -> bool:
        rows = self._db.execute(
            "SELECT complete FROM ontology_meta WHERE ontology = ?", (ontology,)
        )
        return bool(rows and rows[0][0])

    def commit(self) -> None:
        self._db.commit()

    # ------------------------------------------------------------------
    # GroundingBackend Protocol
    # ------------------------------------------------------------------

    def lookup(
        self, value: str, ontology: str, *, scopes: Tuple[str, ...] = (SCOPE_EXACT,)
    ) -> List[GroundedTerm]:
        """*scopes* controls which synonym types are searched
        (exact/broad/narrow/related) - a term's own label is always
        searched regardless of *scopes*, since the label isn't itself a
        synonym scope. An earlier version of this method treated
        `SCOPE_EXACT` as "search labels, and only labels" and explicitly
        excluded it from the synonym query - meaning a real
        `oio:hasExactSynonym` entry (which this backend projects with
        `scope="exact"` - see `seed.py`) could never be found by `lookup()`
        at all. Found while adding test coverage for real projected DOID
        synonym data; fixed here."""
        normalized = normalize(value)
        if not normalized:
            return []
        results: List[GroundedTerm] = []
        seen: set = set()

        for curie, label, version in self._db.execute(
            "SELECT curie, label, version FROM terms "
            "WHERE ontology = ? AND obsolete = 0 AND label_normalized = ?",
            (ontology, normalized),
        ):
            if curie not in seen:
                results.append(
                    GroundedTerm(
                        curie=curie,
                        label=label,
                        ontology=ontology,
                        scope=SCOPE_EXACT,
                        source=self.name,
                        ontology_version=version or "",
                    )
                )
                seen.add(curie)

        if scopes:
            placeholders = ",".join("?" for _ in scopes)
            rows = self._db.execute(
                # nosec B608 - `placeholders` is a `?`-per-scope-count
                # string only (see the line above); every real value
                # (`ontology`, each `scopes` entry, `normalized`) is passed
                # through the parameterized tuple below, not interpolated.
                f"SELECT s.curie, s.synonym, s.scope, t.label, t.version "  # nosec B608
                f"FROM synonyms s JOIN terms t "
                f"ON t.ontology = s.ontology AND t.curie = s.curie "
                f"WHERE s.ontology = ? AND s.scope IN ({placeholders}) "
                f"AND t.obsolete = 0 AND s.synonym_normalized = ?",
                (ontology, *scopes, normalized),
            )
            for curie, synonym, scope, label, version in rows:
                if curie not in seen:
                    results.append(
                        GroundedTerm(
                            curie=curie,
                            label=label or synonym,
                            ontology=ontology,
                            scope=scope,
                            source=self.name,
                            ontology_version=version or "",
                        )
                    )
                    seen.add(curie)
        return results

    def get(self, curie: str, ontology: str) -> Optional[GroundingCheck]:
        rows = self._db.execute(
            "SELECT label, obsolete, replaced_by FROM terms "
            "WHERE ontology = ? AND curie = ?",
            (ontology, curie),
        )
        if not rows:
            if self.is_complete(ontology):
                return GroundingCheck(exists=False, source=self.name)
            # This store doesn't claim complete coverage of `ontology` - a
            # miss here means "unknown", not "confirmed absent". Returning
            # None (not a GroundingCheck) lets a ChainedBackend correctly
            # fall through to a backend that can actually answer, instead
            # of treating a partial store's silence as a hard no.
            return None
        label, obsolete, replaced_by = rows[0]
        return GroundingCheck(
            exists=True,
            label=label or "",
            is_obsolete=bool(obsolete),
            replaced_by=replaced_by or "",
            source=self.name,
        )

    def reachable_from(self, curie: str, root: str, ontology: str) -> Optional[bool]:
        if curie == root:
            return True
        try:
            found = _bfs_edges_from(self._db, ontology, curie, root)
        except Exception as e:
            logger.warning(
                "Local branch-check query failed: %s", mask_exception_message(e)
            )
            return None
        if found:
            return True
        if self.is_complete(ontology):
            return False
        # Same reasoning as get(): an incomplete store's "no edges found"
        # isn't proof there's no path - it might just not have the
        # intermediate hierarchy yet.
        return None

    def ontology_versions(self, ontology: str) -> List[str]:
        """Distinct `version` values stored for *ontology* - lets a caller
        confirm which ontology release/build this store's answers reflect
        (SPEC requirement: "support ontology versioning")."""
        rows = self._db.execute(
            "SELECT DISTINCT version FROM terms WHERE ontology = ? "
            "AND version IS NOT NULL AND version != ''",
            (ontology,),
        )
        return [r[0] for r in rows]

    def close(self) -> None:
        self._db.close()
