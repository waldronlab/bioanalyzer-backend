#!/usr/bin/env python3
"""
Build BugSigDB's Condition vocabulary (ontology ID -> the label BugSigDB uses)
from a `full_dump.csv` export, for app/normalization/bugsigdb_vocabulary.py.

Why this exists: BugSigDB records one fixed label per Condition ontology ID,
taken from an older EFO release - e.g. MONDO:0005180 is always "Parkinson's
disease" (410 rows), where current MONDO and EFO both say "Parkinson
disease". BioAnalyzer used to emit the current ontology label, so a correct
ontology ID still scored as a label mismatch against BugSigDB, and a curator
had to retype it. The 2026-11-12 benchmark found 17 of 100 papers in exactly
that state. The ontology itself can't supply BugSigDB's wording; BugSigDB's
own export can.

Only rows with a single Condition and a single EFO ID are used: BugSigDB
packs multiple conditions into one comma-joined cell, and pairing those
positionally isn't reliable. When one ID carries more than one label (2 of
~930 IDs in the 2026-08 export), the most frequently curated label wins.

Usage:
    python scripts/build_bugsigdb_condition_vocabulary.py --dump full_dump.csv
    # Held-out copy for benchmarking (no leakage from the benchmark's papers):
    python scripts/build_bugsigdb_condition_vocabulary.py --dump full_dump.csv \\
        --exclude-pmids pmids.txt -o cache/bugsigdb_condition_vocabulary.heldout.json
"""

from __future__ import annotations

import argparse
import collections
import csv
import json
import sqlite3
import sys
from pathlib import Path

DEFAULT_OUTPUT = (
    Path(__file__).resolve().parents[1]
    / "app"
    / "normalization"
    / "data"
    / "bugsigdb_condition_vocabulary.json"
)


def _obsolete_ids(curies, db_path: Path) -> list[str]:
    """IDs the local ontology store marks obsolete. BugSigDB still records a
    few retired IDs (e.g. MONDO:0100318 "SARS-CoV-2-related disease"); they
    must never be offered as a Condition. IDs from ontologies the store
    doesn't hold can't be checked and are kept."""
    if not db_path.exists():
        print(
            f"Warning: {db_path} not found - obsolete IDs not filtered "
            "(normalize_condition still re-checks at run time)",
            file=sys.stderr,
        )
        return []
    con = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    try:
        obsolete = []
        for curie in curies:
            row = con.execute(
                "SELECT obsolete FROM terms WHERE ontology = ? AND curie = ?",
                (curie.split(":")[0].lower(), curie),
            ).fetchone()
            if row is not None and row[0]:
                obsolete.append(curie)
        return obsolete
    finally:
        con.close()


def build_vocabulary(
    dump_path: Path, exclude_pmids: set[str], ontology_db: Path | None = None
) -> dict:
    with open(dump_path, encoding="utf-8") as f:
        first_line = f.readline()
        snapshot = first_line.strip("# \n") if first_line.startswith("#") else ""
        if not first_line.startswith("#"):
            f.seek(0)
        rows = list(csv.DictReader(f))

    counts: dict[str, collections.Counter] = collections.defaultdict(
        collections.Counter
    )
    used_rows = 0
    for row in rows:
        if (row.get("PMID") or "").strip() in exclude_pmids:
            continue
        label = (row.get("Condition") or "").strip()
        curie = (row.get("EFO ID") or "").strip()
        if not label or not curie or label == "NA" or curie == "NA":
            continue
        if "," in label or "," in curie:
            continue
        counts[curie.upper().replace("NCBITAXON:", "NCBITaxon:")][label] += 1
        used_rows += 1

    dropped = _obsolete_ids(counts, ontology_db) if ontology_db else []
    terms = {}
    for curie in sorted(set(counts) - set(dropped)):
        (label, n), *others = counts[curie].most_common()
        entry = {"label": label, "rows": sum(counts[curie].values())}
        if others:
            entry["other_labels"] = [other for other, _ in others]
        terms[curie] = entry

    return {
        "source": snapshot or str(dump_path),
        "built_from_rows": used_rows,
        "excluded_pmids": len(exclude_pmids),
        "dropped_obsolete_ids": sorted(dropped),
        "terms": terms,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument(
        "--dump", default="full_dump.csv", help="BugSigDB full_dump.csv"
    )
    parser.add_argument(
        "--exclude-pmids",
        help="File of PMIDs (one per line) whose rows are left out, e.g. a "
        "benchmark sample, so scoring against them isn't helped by their own labels",
    )
    parser.add_argument("-o", "--output", default=str(DEFAULT_OUTPUT))
    parser.add_argument(
        "--ontology-db",
        default="ontology_store/ontology_store.db",
        help="Local ontology store used to drop obsolete IDs ('' to skip)",
    )
    args = parser.parse_args()

    dump_path = Path(args.dump)
    if not dump_path.exists():
        print(f"Error: dump file not found: {dump_path}", file=sys.stderr)
        return 1
    exclude: set[str] = set()
    if args.exclude_pmids:
        exclude = {
            line.strip()
            for line in Path(args.exclude_pmids).read_text().splitlines()
            if line.strip()
        }

    vocab = build_vocabulary(
        dump_path, exclude, Path(args.ontology_db) if args.ontology_db else None
    )
    out = Path(args.output)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(vocab, indent=1, ensure_ascii=False) + "\n")
    print(
        f"Wrote {out}: {len(vocab['terms'])} condition terms from "
        f"{vocab['built_from_rows']} rows ({vocab['source']}); "
        f"dropped obsolete: {', '.join(vocab['dropped_obsolete_ids']) or 'none'}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
