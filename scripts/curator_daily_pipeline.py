#!/usr/bin/env python3
"""
Curator Desk daily pipeline (spec §4.3, §7.1, long-term vision).

PubMed discovery search → BioAnalyzer batch analysis → curator_desk_csv export.

Usage:
  python scripts/curator_daily_pipeline.py --max-results 50 -o results/curator_predictions.csv
  python scripts/curator_daily_pipeline.py --pmids-file existing_pmids.txt -o out.csv

Requires BioAnalyzer API (BioAnalyzer start) or set BIOANALYZER_API_URL.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import requests

project_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(project_root))

from app.services.pubmed_queries import RECOMMENDED_DISCOVERY_QUERY, SEARCH_PRESETS
from app.services.data_retrieval import PubMedRetriever
from scripts.cli import render_results


def _load_analyzed_pmids(state_path: Path) -> set[str]:
    if not state_path.exists():
        return set()
    try:
        data = json.loads(state_path.read_text(encoding="utf-8"))
        return set(str(p) for p in data.get("analyzed_pmids", []))
    except (json.JSONDecodeError, OSError):
        return set()


def _save_analyzed_pmids(state_path: Path, pmids: set[str]) -> None:
    state_path.parent.mkdir(parents=True, exist_ok=True)
    state_path.write_text(
        json.dumps(
            {
                "analyzed_pmids": sorted(pmids),
                "updated_at": datetime.now(timezone.utc).isoformat(),
            },
            indent=2,
        ),
        encoding="utf-8",
    )


def _search_pmids(preset: str, query: str | None, max_results: int) -> list[str]:
    term = (
        query.strip()
        if query
        else SEARCH_PRESETS.get(preset, RECOMMENDED_DISCOVERY_QUERY)
    )
    retriever = PubMedRetriever()
    return retriever.search(term, max_results=max_results)


def _high_confidence_ready(result: dict, min_mapping_conf: float) -> bool:
    """Papers ready for near-direct BugSigDB import (long-term zero-effort curation)."""
    fields = result.get("fields") or {}
    required = (
        "host_species",
        "body_site",
        "condition",
        "sequencing_type",
        "sample_size",
    )
    for key in required:
        field = fields.get(key) or {}
        if field.get("status") != "PRESENT":
            return False
        if key in ("host_species", "body_site", "condition"):
            try:
                if float(field.get("mapping_confidence", 0) or 0) < min_mapping_conf:
                    return False
            except (TypeError, ValueError):
                return False
    return bool(result.get("has_differential_abundance"))


def _analyze_pmids(pmids: list[str], api_base: str, timeout: int) -> list[dict]:
    results: list[dict] = []
    for pmid in pmids:
        url = f"{api_base.rstrip('/')}/analyze/{pmid}"
        try:
            resp = requests.get(url, timeout=timeout)
            if resp.status_code == 200:
                results.append(resp.json())
            else:
                print(f"WARN PMID {pmid}: {resp.status_code} {resp.text[:120]}")
        except requests.RequestException as exc:
            print(f"ERROR PMID {pmid}: {exc}")
    return results


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Curator Desk daily BioAnalyzer pipeline"
    )
    parser.add_argument(
        "--preset", choices=["discovery", "broad", "precision"], default="discovery"
    )
    parser.add_argument("--query", help="Override PubMed query")
    parser.add_argument("--max-results", type=int, default=50)
    parser.add_argument(
        "--pmids-file", help="Analyze PMIDs from file instead of searching"
    )
    parser.add_argument("-o", "--output", default="results/curator_predictions.csv")
    parser.add_argument("--state-file", default="results/analyzed_pmids.json")
    parser.add_argument("--skip-analyzed", action="store_true", default=True)
    parser.add_argument(
        "--api-url",
        default=None,
        help="BioAnalyzer API base (default: BIOANALYZER_API_URL or localhost)",
    )
    parser.add_argument("--timeout", type=int, default=180)
    parser.add_argument(
        "--high-confidence-only",
        action="store_true",
        help="Keep only rows with all 5 fields PRESENT, ontology mapping >= threshold, and DA detected",
    )
    parser.add_argument("--min-mapping-confidence", type=float, default=0.9)
    args = parser.parse_args()

    import os

    api_base = args.api_url or os.getenv(
        "BIOANALYZER_API_URL", "http://localhost:8000/api/v1"
    )

    if args.pmids_file:
        pmids = [
            line.strip()
            for line in Path(args.pmids_file).read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
    else:
        print(f"Searching PubMed (preset={args.preset}, max={args.max_results})...")
        pmids = _search_pmids(args.preset, args.query, args.max_results)
        print(f"Found {len(pmids)} PMID(s)")

    state_path = Path(args.state_file)
    analyzed = _load_analyzed_pmids(state_path) if args.skip_analyzed else set()
    new_pmids = [p for p in pmids if p not in analyzed]
    if not new_pmids:
        print("No new PMIDs to analyze.")
        return 0

    print(f"Analyzing {len(new_pmids)} PMID(s) via {api_base}...")
    results = _analyze_pmids(new_pmids, api_base, args.timeout)
    if not results:
        print("No analysis results.")
        return 1

    if args.high_confidence_only:
        before = len(results)
        results = [
            r for r in results if _high_confidence_ready(r, args.min_mapping_confidence)
        ]
        print(
            f"High-confidence filter: {len(results)}/{before} rows "
            f"(mapping_confidence >= {args.min_mapping_confidence})"
        )
        if not results:
            print("No rows passed high-confidence filter.")
            return 1

    csv_text = render_results(results, "curator_desk_csv")
    out_path = Path(args.output)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(csv_text, encoding="utf-8")
    print(f"Wrote {len(results)} row(s) to {out_path}")

    analyzed.update(new_pmids)
    _save_analyzed_pmids(state_path, analyzed)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
