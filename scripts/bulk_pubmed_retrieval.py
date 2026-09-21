#!/usr/bin/env python3
"""
Bulk MeSH-query-driven PubMed/PMC retrieval (~10k-article scale).

Retrieval/ingestion ONLY - this script does not run BioAnalyzer's LLM
analysis pipeline (a deliberate, separately-triggered, cost-visible later
step). It searches PubMed for the named queries in
app.services.pubmed_queries.BULK_RETRIEVAL_QUERIES (3 topic-scoped MeSH
queries as of 2026-08: women's health, MASLD, colorectal cancer), dedupes
PMIDs across queries, and fetches metadata + (where available) PMC full
text by reusing PubMedRetriever unchanged - no new retrieval logic, no FTP
client, no new dependency.

Uses the existing E-utilities API path rather than the PubMed FTP baseline:
the baseline is a full ~38M-record mirror dump, the wrong tool for a
filtered ~10k-article subset search.

Checkpointing is append-only and per-record (records.jsonl / failures.jsonl),
not a single rewritten state blob - safe and cheap at 10k scale, and a
crash/interrupt loses at most the one in-flight PMID. Re-running with the
same -o resumes automatically (already-recorded PMIDs are skipped).

Usage:
  python scripts/bulk_pubmed_retrieval.py -o results/bulk_retrieval
  python scripts/bulk_pubmed_retrieval.py --queries womens_health \\
      --max-results 25 -o results/bulk_retrieval_smoke_test   # smoke test
  python scripts/bulk_pubmed_retrieval.py --check-oa -o results/bulk_retrieval
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Dict, List, Optional, Set

project_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(project_root))

from app.services.data_retrieval import PubMedRetriever  # noqa: E402
from app.services.pubmed_queries import BULK_RETRIEVAL_QUERIES  # noqa: E402
from app.utils.config import EMAIL, NCBI_API_KEY  # noqa: E402
from app.utils.credential_masking import mask_exception_message  # noqa: E402

# NCBI's PMC Open Access Web Service - a separate host from eutils, so it
# doesn't go through PubMedRetriever._make_request (scoped to eutils.*), but
# reuses the same requests.Session (and its rate-limited call pattern).
OA_SERVICE_URL = "https://www.ncbi.nlm.nih.gov/pmc/utils/oa/oa.fcgi"


def _load_done_pmids(*jsonl_paths: Path) -> Set[str]:
    """Union of PMIDs already present in one or more JSONL files.

    A truncated/unparseable last line (mid-write crash) is dropped rather
    than raising - that one record is simply re-fetched on resume.
    """
    done: Set[str] = set()
    for path in jsonl_paths:
        if not path.exists():
            continue
        lines = path.read_text(encoding="utf-8").splitlines()
        for line in lines:
            if not line.strip():
                continue
            try:
                record = json.loads(line)
            except json.JSONDecodeError:
                continue
            pmid = record.get("pmid")
            if pmid:
                done.add(str(pmid))
    return done


def _search_all_queries(
    retriever: PubMedRetriever, query_names: List[str], max_results: int
) -> Dict[str, List[str]]:
    """Returns query_name -> list of matching PMIDs (pre-dedup)."""
    results: Dict[str, List[str]] = {}
    for name in query_names:
        term = BULK_RETRIEVAL_QUERIES[name]
        print(f"Searching '{name}' (max_results={max_results})...")
        pmids = retriever.search(term, max_results=max_results)
        print(f"  {len(pmids)} PMID(s)")
        if len(pmids) == max_results:
            print(
                f"  WARNING: '{name}' returned exactly {max_results} result(s) - "
                "this likely means the search truncated rather than being "
                "genuinely exhausted. Re-run with a higher --max-results "
                "(NCBI's single-call ESearch ceiling is 10000); a query "
                "exceeding that would need history-server pagination, which "
                "this script does not implement."
            )
        results[name] = pmids
    return results


def _check_oa(retriever: PubMedRetriever, pmc_id: str) -> Optional[bool]:
    """True/False if determinable, None if the OA service call itself failed
    (never conflated with a real "not OA" answer)."""
    try:
        resp = retriever.session.get(
            OA_SERVICE_URL, params={"id": pmc_id}, timeout=(5, 15)
        )
        resp.raise_for_status()
        return "<record " in resp.text and "<error" not in resp.text
    except Exception as exc:
        print(f"  (OA check failed for {pmc_id}: {mask_exception_message(exc)})")
        return None


def main() -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument(
        "--queries",
        nargs="+",
        choices=list(BULK_RETRIEVAL_QUERIES),
        default=list(BULK_RETRIEVAL_QUERIES),
        help="Which named queries to run (default: all)",
    )
    parser.add_argument(
        "--max-results",
        type=int,
        default=10000,
        help="Per-query ESearch retmax - NCBI's single-call ceiling (default 10000)",
    )
    parser.add_argument(
        "-o", "--output", default="results/bulk_retrieval", help="Output directory"
    )
    parser.add_argument(
        "--check-oa",
        action="store_true",
        help="Also confirm true PMC Open Access status per article (one extra "
        "request per PMC-resolved article; off by default)",
    )
    args = parser.parse_args()

    outdir = Path(args.output)
    outdir.mkdir(parents=True, exist_ok=True)
    records_path = outdir / "records.jsonl"
    failures_path = outdir / "failures.jsonl"

    retriever = PubMedRetriever(api_key=NCBI_API_KEY, email=EMAIL or None)

    query_results = _search_all_queries(retriever, args.queries, args.max_results)

    pmid_sources: Dict[str, Set[str]] = {}
    for name, pmids in query_results.items():
        for pmid in pmids:
            pmid_sources.setdefault(pmid, set()).add(name)
    all_pmids = sorted(pmid_sources, key=int)

    raw_total = sum(len(v) for v in query_results.values())
    print(
        f"\n{raw_total} raw match(es) across {len(args.queries)} "
        f"quer{'y' if len(args.queries) == 1 else 'ies'}, "
        f"{len(all_pmids)} unique PMID(s) after dedup."
    )

    already_done = _load_done_pmids(records_path, failures_path)
    remaining = [p for p in all_pmids if p not in already_done]
    print(
        f"{len(already_done)} already recorded from a prior run (resuming), "
        f"{len(remaining)} to fetch now."
    )

    full_text_count = 0
    oa_count = 0
    fetched = 0
    failed = 0

    with (
        open(records_path, "a", encoding="utf-8") as records_file,
        open(failures_path, "a", encoding="utf-8") as failures_file,
    ):
        for i, pmid in enumerate(remaining, 1):
            sources = sorted(pmid_sources[pmid])
            try:
                paper = retriever.get_full_paper_data(pmid)
            except Exception as exc:  # defensive: get_full_paper_data already
                # catches its own network/parse errors internally and returns
                # an {"error": ...} dict - this only guards truly unexpected
                # failures so one bad PMID can't kill a 10k-article run.
                failures_file.write(
                    json.dumps(
                        {
                            "pmid": pmid,
                            "source_queries": sources,
                            "reason": mask_exception_message(exc),
                        }
                    )
                    + "\n"
                )
                failures_file.flush()
                failed += 1
                continue

            if paper.get("error"):
                failures_file.write(
                    json.dumps(
                        {
                            "pmid": pmid,
                            "source_queries": sources,
                            "reason": paper["error"],
                        }
                    )
                    + "\n"
                )
                failures_file.flush()
                failed += 1
                continue

            has_full_text = bool(paper.get("has_full_text"))
            is_oa: Optional[bool] = None
            if args.check_oa and has_full_text:
                pmc_id = retriever._get_pmc_id_from_pmid(pmid)
                if pmc_id:
                    is_oa = _check_oa(retriever, pmc_id)
                    if is_oa:
                        oa_count += 1

            if has_full_text:
                full_text_count += 1

            records_file.write(
                json.dumps(
                    {
                        "pmid": pmid,
                        "source_queries": sources,
                        "title": paper.get("title", ""),
                        "journal": paper.get("journal", ""),
                        "publication_date": paper.get("publication_date", ""),
                        "has_full_text": has_full_text,
                        "is_pmc_oa": is_oa,
                        "full_text_chars": len(paper.get("full_text", "") or ""),
                    }
                )
                + "\n"
            )
            records_file.flush()
            fetched += 1

            if i % 100 == 0 or i == len(remaining):
                print(f"  {i}/{len(remaining)} fetched ({failed} failure(s) so far)...")

    inventory = {
        "queries": {name: len(pmids) for name, pmids in query_results.items()},
        "raw_matches_pre_dedup": raw_total,
        "unique_pmids": len(all_pmids),
        "already_done_before_this_run": len(already_done),
        "fetched_this_run": fetched,
        "failed_this_run": failed,
        "full_text_available_this_run": full_text_count,
        "pmc_oa_confirmed_this_run": oa_count if args.check_oa else None,
    }
    inventory_path = outdir / "inventory.json"
    inventory_path.write_text(json.dumps(inventory, indent=2), encoding="utf-8")

    print(f"\nWrote {records_path}")
    if failed:
        print(f"Wrote {failures_path} ({failed} failure(s))")
    print(f"Wrote {inventory_path}")
    print(json.dumps(inventory, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
