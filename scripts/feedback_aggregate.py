#!/usr/bin/env python3
"""
Aggregate curator feedback CSVs into a single dataset for model evaluation.

Supports:
  - Local curator-feedback/*.csv files
  - Exported GitHub issue bodies containing ```csv blocks

Usage:
  python scripts/feedback_aggregate.py --input curator_table_r/curator-feedback -o results/aggregated_feedback.csv
"""

from __future__ import annotations

import argparse
import csv
import io
import re
from pathlib import Path

CSV_BLOCK_RE = re.compile(r"```csv\s*(.*?)```", re.DOTALL | re.IGNORECASE)


def _rows_from_file(path: Path) -> list[dict]:
    text = path.read_text(encoding="utf-8", errors="replace")
    if "```csv" in text.lower():
        blocks = CSV_BLOCK_RE.findall(text)
        rows: list[dict] = []
        for block in blocks:
            rows.extend(list(csv.DictReader(io.StringIO(block.strip()))))
        return rows
    with path.open(encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))


def _accuracy_by_field(rows: list[dict]) -> dict[str, dict[str, int]]:
    stats: dict[str, dict[str, int]] = {}
    for row in rows:
        for key, val in row.items():
            if not key.startswith("col_feedback__"):
                continue
            field = key.replace("col_feedback__", "")
            stats.setdefault(field, {"Correct": 0, "Incorrect": 0, "Unclear": 0, "Not reviewed": 0})
            label = (val or "Not reviewed").strip()
            stats[field][label] = stats[field].get(label, 0) + 1
    return stats


def main() -> int:
    parser = argparse.ArgumentParser(description="Aggregate curator feedback CSVs")
    parser.add_argument("--input", required=True, help="Directory or file with feedback CSVs")
    parser.add_argument("-o", "--output", default="results/aggregated_feedback.csv")
    parser.add_argument("--report", action="store_true", help="Print per-field accuracy summary")
    args = parser.parse_args()

    input_path = Path(args.input)
    files: list[Path] = []
    if input_path.is_file():
        files = [input_path]
    elif input_path.is_dir():
        files = sorted(input_path.glob("**/*.csv")) + sorted(input_path.glob("**/*.md"))
    else:
        print(f"Input not found: {input_path}")
        return 1

    all_rows: list[dict] = []
    for fp in files:
        try:
            all_rows.extend(_rows_from_file(fp))
        except Exception as exc:
            print(f"WARN skipping {fp}: {exc}")

    if not all_rows:
        print("No feedback rows found.")
        return 1

    out_path = Path(args.output)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames: list[str] = []
    for row in all_rows:
        for k in row:
            if k not in fieldnames:
                fieldnames.append(k)

    with out_path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(all_rows)

    print(f"Aggregated {len(all_rows)} row(s) → {out_path}")

    if args.report:
        stats = _accuracy_by_field(all_rows)
        print("\nPer-field prediction feedback:")
        for field, counts in sorted(stats.items()):
            reviewed = counts.get("Correct", 0) + counts.get("Incorrect", 0)
            acc = counts.get("Correct", 0) / reviewed if reviewed else 0.0
            print(f"  {field}: accuracy={acc:.1%} ({counts})")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
