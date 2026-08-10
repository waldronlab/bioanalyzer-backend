#!/usr/bin/env python3
"""Fetch full ontology dumps into LocalOntologyBackend's local store.

Standalone (not wired into `scripts/cli.py`/`BioAnalyzer`) deliberately -
this is a one-time-per-ontology, bandwidth-heavy operation an operator runs
when they have real bandwidth, not something that belongs in the regular
CLI surface or gets invoked accidentally.

Background: a 2026-08 production-readiness pass measured (via a live HEAD
request against the public semantic-sql bucket) these compressed download
sizes and confirmed all are live and fetchable - all 9 have since been
fully synced and verified against real data (see
docs/GROUNDING_ARCHITECTURE.md):

    efo         241 MB
    mondo       225 MB
    uberon      190 MB
    ncbitaxon   2.1 GB
    doid         23 MB
    hp           84 MB
    chebi       760 MB  (real root CHEBI:24431 verified; see roots.py)
    ncit        525 MB  (real data synced; no meaningful single root - see roots.py)
    envo         15 MB  (real data synced; no meaningful single root - see roots.py)
    mesh         84 MB  (real data synced; no meaningful single root - see roots.py)

Usage:
    python scripts/ontology_sync.py efo mondo uberon ncbitaxon hp chebi
    python scripts/ontology_sync.py --all
    python scripts/ontology_sync.py --status

Each ontology is independent - a failure partway through (network drop,
disk space) doesn't affect ontologies already synced, and the command is
safe to re-run (`ensure_ontology()` overwrites, doesn't duplicate).
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.normalization.grounding.local_backend import (  # noqa: E402
    DEFAULT_DB_PATH,
    LocalOntologyBackend,
)
from app.normalization.grounding.roots import (  # noqa: E402
    EXTENDED_ONTOLOGY_ROOTS,
    NO_SINGLE_ROOT,
    ROOTS,
)
from app.normalization.grounding.seed import ensure_ontology  # noqa: E402

# ols_slug -> curie_prefix, for every ontology this script knows how to
# fetch. Drawn from ROOTS (already-active), EXTENDED_ONTOLOGY_ROOTS (a
# verified, meaningful root but not yet field-bound), and NO_SINGLE_ROOT
# (real data, deliberately no root - see roots.py's module docstring for
# the technical evidence behind each of these three categories).
_KNOWN_ONTOLOGIES = {
    ols_slug: prefix
    for prefix, (ols_slug, _root_id) in {**ROOTS, **EXTENDED_ONTOLOGY_ROOTS}.items()
}
_KNOWN_ONTOLOGIES.update({slug: prefix for slug, prefix in NO_SINGLE_ROOT.items()})


def _sync_one(slug: str, backend: LocalOntologyBackend) -> bool:
    if slug not in _KNOWN_ONTOLOGIES:
        print(
            f"  ✗ {slug}: no curie prefix registered - add it to ROOTS or "
            f"EXTENDED_ONTOLOGY_ROOTS in app/normalization/grounding/roots.py first"
        )
        return False
    curie_prefix = _KNOWN_ONTOLOGIES[slug]
    print(f"  ↓ {slug} ({curie_prefix}:*) ...", end=" ", flush=True)
    start = time.time()
    ok = ensure_ontology(slug, curie_prefix, backend)
    elapsed = time.time() - start
    if ok:
        count = backend._db.execute(
            "SELECT COUNT(*) FROM terms WHERE ontology = ?", (slug,)
        )[0][0]
        print(f"done in {elapsed:.0f}s - {count} terms, marked complete")
    else:
        print(f"FAILED after {elapsed:.0f}s - see log output above for the reason")
    return ok


def _print_status(backend: LocalOntologyBackend) -> None:
    print(f"Local ontology store: {backend.db_path} ({backend._db.engine})")
    print()
    for slug in sorted(_KNOWN_ONTOLOGIES):
        rows = backend._db.execute(
            "SELECT term_count, source, version, updated_at FROM ontology_meta "
            "WHERE ontology = ? AND complete = 1",
            (slug,),
        )
        if rows:
            count, source, version, updated_at = rows[0]
            print(
                f"  ✓ {slug}: {count} terms, version {version!r}, synced {updated_at}"
            )
        else:
            seed_rows = backend._db.execute(
                "SELECT COUNT(*) FROM terms WHERE ontology = ?", (slug,)
            )
            seed_count = seed_rows[0][0] if seed_rows else 0
            note = f"{seed_count} seed-only terms" if seed_count else "not synced"
            print(f"  · {slug}: {note}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "ontologies",
        nargs="*",
        help="ols slugs to sync (e.g. efo mondo uberon ncbitaxon hp)",
    )
    parser.add_argument("--all", action="store_true", help="sync every known ontology")
    parser.add_argument(
        "--status", action="store_true", help="show what's synced and exit"
    )
    parser.add_argument(
        "--db-path",
        default=DEFAULT_DB_PATH,
        help="local store path (default: %(default)s)",
    )
    args = parser.parse_args()

    backend = LocalOntologyBackend(db_path=args.db_path)
    try:
        if args.status:
            _print_status(backend)
            return 0

        targets = (
            sorted(_KNOWN_ONTOLOGIES)
            if args.all
            else [s.lower() for s in args.ontologies]
        )
        if not targets:
            parser.print_help()
            return 1

        print(f"Syncing {len(targets)} ontology(ies) into {args.db_path}:")
        results = [_sync_one(slug, backend) for slug in targets]
        failures = results.count(False)
        print()
        print(f"{len(results) - failures}/{len(results)} succeeded")
        return 1 if failures else 0
    finally:
        backend.close()


if __name__ == "__main__":
    raise SystemExit(main())
