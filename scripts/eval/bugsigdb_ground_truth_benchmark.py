#!/usr/bin/env python3
"""
BugSigDB ground-truth accuracy benchmark.

Per Levi Waldron / Chloe's guidance (see docs/BUGSIGDB_ACCURACY_BENCHMARK.md):
before investing further in curator-facing UI/feedback work, establish how
well BioAnalyzer's extractions agree with BugSigDB's own existing curated
signatures (not curator_table's feedback CSV — this compares against the
real BugSigDB corpus, downloaded as `full_dump.csv` from
waldronlab/BugSigDBExports).

This is a two-step, human-in-the-loop workflow (LLM calls are real money/time,
so this script never triggers them itself):

  1. `prepare`  - parse full_dump.csv, sample PMIDs, write a plain PMID list
                  (consumable by `BioAnalyzer analyze --file`) plus a
                  ground-truth JSON snapshot of that exact sample.
  2. (you run)    BioAnalyzer analyze --file <pmids.txt> --format csv -o <predictions.csv>
  3. `compare`  - merge predictions against the ground-truth snapshot and
                  report per-field agreement.

Does not replace scripts/eval/confusion_matrix_analysis.py (validates
internal PRESENT/PARTIALLY_PRESENT/ABSENT status against curator_table
feedback) or ontology_benchmark.py (spot-checks the static lookup dicts) -
this is a third, independent check: real curated *values*, from BugSigDB
itself, compared against BioAnalyzer's curator-desk CSV output.
"""

from __future__ import annotations

import argparse
import csv
import json
import random
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Set

# Reuse the same dump URL as app.services.bugsigdb_check rather than
# duplicating it, in case a caller wants --dump to fall back to a fresh
# download instead of the local snapshot.
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from app.services.bugsigdb_check import BUGSIGDB_DUMP_URL  # noqa: E402

# BioAnalyzer curator-desk CSV column name -> ground-truth dict key.
PRED_LABEL_COL = {
    "host_species": "Host Species",
    "body_site": "Body Site",
    "condition": "Condition",
    "sequencing_type": "Sequencing Type",
    "sample_size": "Sample Size",
}
PRED_ONTOLOGY_COL = {
    "body_site": "Body Site Ontology ID",
    "condition": "Condition Ontology ID",
}


def _norm(value: Optional[str]) -> str:
    """Lowercase/strip normalization used for all label-level comparisons."""
    return (value or "").strip().lower()


def _norm_id(value: Optional[str]) -> str:
    """Uppercase/strip normalization for ontology ID comparisons (IDs like
    EFO:0002508/MONDO:0005180 are case-stable but stray whitespace isn't)."""
    return (value or "").strip().upper()


# ---------------------------------------------------------------------------
# prepare
# ---------------------------------------------------------------------------


def _parse_full_dump(dump_path: Path) -> Dict[str, Dict[str, Any]]:
    """
    Parse full_dump.csv into a per-PMID ground-truth structure.

    Most PMIDs have many experiment rows (96% of PMIDs in a 2026-07 snapshot
    have >1; one had 200) - these are deduplicated into sets per field so a
    single BioAnalyzer extraction can be checked for membership rather than
    forcing a one-experiment-to-one-row comparison BioAnalyzer's v1/v2
    pipelines (one field-set per PMID, not per-experiment) can't support.
    """
    ground_truth: Dict[str, Dict[str, Any]] = {}

    with open(dump_path, encoding="utf-8") as f:
        first_line = f.readline()
        if not first_line.startswith("#"):
            f.seek(0)
        reader = csv.DictReader(f)
        rows = list(reader)

    for row in rows:
        pmid = (row.get("PMID") or "").strip()
        if not pmid or pmid == "NA":
            continue

        gt = ground_truth.setdefault(
            pmid,
            {
                "host_species": set(),
                "body_site_labels": set(),
                "body_site_ids": set(),
                "condition_labels": set(),
                "condition_ids": set(),
                "sequencing_type": set(),
                "sample_size": set(),
            },
        )

        host = _norm(row.get("Host species"))
        if host and host != "na":
            gt["host_species"].add(host)

        body_site_raw = (row.get("Body site") or "").strip()
        uberon_raw = (row.get("UBERON ID") or "").strip()
        if body_site_raw and body_site_raw != "NA":
            for label in body_site_raw.split(","):
                label = _norm(label)
                if label:
                    gt["body_site_labels"].add(label)
        if uberon_raw and uberon_raw != "NA":
            for oid in uberon_raw.split(","):
                oid = _norm_id(oid)
                if oid:
                    gt["body_site_ids"].add(oid)

        condition = _norm(row.get("Condition"))
        if condition and condition != "na":
            gt["condition_labels"].add(condition)
        efo_id = _norm_id(row.get("EFO ID"))
        if efo_id and efo_id != "NA":
            gt["condition_ids"].add(efo_id)

        seq_type = _norm(row.get("Sequencing type"))
        if seq_type and seq_type != "na":
            gt["sequencing_type"].add(seq_type)

        g0, g1 = row.get("Group 0 sample size"), row.get("Group 1 sample size")
        try:
            total = int(str(g0).strip()) + int(str(g1).strip())
            gt["sample_size"].add(total)
        except (TypeError, ValueError):
            pass

    return ground_truth


def _has_any_ground_truth(gt: Dict[str, Any]) -> bool:
    return any(len(v) > 0 for v in gt.values())


def _jsonable(ground_truth: Dict[str, Dict[str, Any]]) -> Dict[str, Dict[str, List]]:
    return {
        pmid: {k: sorted(v) for k, v in fields.items()}
        for pmid, fields in ground_truth.items()
    }


def cmd_prepare(args: argparse.Namespace) -> int:
    dump_path = Path(args.dump)
    if not dump_path.exists():
        print(f"Error: dump file not found: {dump_path}", file=sys.stderr)
        print(f"(download it from {BUGSIGDB_DUMP_URL})", file=sys.stderr)
        return 1

    print(f"Parsing {dump_path} ...")
    ground_truth = _parse_full_dump(dump_path)
    eligible = [pmid for pmid, gt in ground_truth.items() if _has_any_ground_truth(gt)]
    print(
        f"  {len(ground_truth)} distinct PMIDs, {len(eligible)} with usable ground truth"
    )

    if args.all:
        sample = sorted(eligible)
    else:
        rng = random.Random(args.seed)
        sample = sorted(rng.sample(eligible, min(args.limit, len(eligible))))
    print(f"  sampled {len(sample)} PMID(s) (seed={args.seed}, all={args.all})")

    out_path = Path(args.output)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        f.write("\n".join(sample) + "\n")

    gt_path = out_path.with_suffix("")
    gt_path = gt_path.with_name(gt_path.name + ".ground_truth.json")
    sampled_gt = {pmid: ground_truth[pmid] for pmid in sample}
    with open(gt_path, "w", encoding="utf-8") as f:
        json.dump(_jsonable(sampled_gt), f, indent=2)

    predictions_path = out_path.with_name("predictions.csv")
    print(f"\nWrote {out_path} ({len(sample)} PMIDs)")
    print(f"Wrote {gt_path}")
    print("\nNext step - run this yourself (real LLM/PubMed calls):")
    print(f"  BioAnalyzer analyze --file {out_path} --format csv -o {predictions_path}")
    print("\nThen:")
    print(
        f"  python {Path(__file__).name} compare --predictions {predictions_path} "
        f"--ground-truth {gt_path} -o {out_path.parent}"
    )
    return 0


# ---------------------------------------------------------------------------
# compare
# ---------------------------------------------------------------------------


class FieldTally:
    def __init__(self, name: str):
        self.name = name
        self.n_compared = 0
        self.n_agree = 0

    def record(self, agree: bool) -> None:
        self.n_compared += 1
        if agree:
            self.n_agree += 1

    @property
    def pct(self) -> Optional[float]:
        if self.n_compared == 0:
            return None
        return 100.0 * self.n_agree / self.n_compared


def _load_predictions(predictions_path: Path) -> Dict[str, Dict[str, str]]:
    with open(predictions_path, encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    by_pmid: Dict[str, Dict[str, str]] = {}
    for row in rows:
        pmid = (row.get("PMID") or "").strip()
        if pmid:
            by_pmid[pmid] = row
    return by_pmid


def _compare_field(
    field: str,
    tallies: Dict[str, FieldTally],
    discrepancies: List[Dict[str, str]],
    pmid: str,
    predicted_label: str,
    ground_truth_labels: Set[str],
    predicted_id: Optional[str] = None,
    ground_truth_ids: Optional[Set[str]] = None,
) -> None:
    pred_norm = _norm(predicted_label)
    if pred_norm and ground_truth_labels:
        label_key = f"{field}_label"
        agree = pred_norm in ground_truth_labels
        tallies.setdefault(label_key, FieldTally(label_key)).record(agree)
        if not agree:
            discrepancies.append(
                {
                    "PMID": pmid,
                    "field": label_key,
                    "predicted": predicted_label,
                    "ground_truth": "; ".join(sorted(ground_truth_labels)),
                }
            )

    if predicted_id is not None and ground_truth_ids is not None:
        pred_id_norm = _norm_id(predicted_id)
        if pred_id_norm and ground_truth_ids:
            id_key = f"{field}_ontology_id"
            agree = pred_id_norm in ground_truth_ids
            tallies.setdefault(id_key, FieldTally(id_key)).record(agree)
            if not agree:
                discrepancies.append(
                    {
                        "PMID": pmid,
                        "field": id_key,
                        "predicted": predicted_id,
                        "ground_truth": "; ".join(sorted(ground_truth_ids)),
                    }
                )


def cmd_compare(args: argparse.Namespace) -> int:
    predictions_path = Path(args.predictions)
    gt_path = Path(args.ground_truth)
    if not predictions_path.exists():
        print(f"Error: predictions file not found: {predictions_path}", file=sys.stderr)
        return 1
    if not gt_path.exists():
        print(f"Error: ground-truth file not found: {gt_path}", file=sys.stderr)
        return 1

    predictions = _load_predictions(predictions_path)
    with open(gt_path, encoding="utf-8") as f:
        ground_truth: Dict[str, Dict[str, List[str]]] = json.load(f)

    tallies: Dict[str, FieldTally] = {}
    discrepancies: List[Dict[str, str]] = []

    matched_pmids = set(predictions) & set(ground_truth)
    print(f"Predictions: {len(predictions)} PMID(s)")
    print(f"Ground truth: {len(ground_truth)} PMID(s)")
    print(f"Overlap: {len(matched_pmids)} PMID(s)")
    if not matched_pmids:
        print(
            "Error: no overlapping PMIDs between predictions and ground truth.",
            file=sys.stderr,
        )
        return 1

    for pmid in sorted(matched_pmids):
        pred = predictions[pmid]
        gt = ground_truth[pmid]

        _compare_field(
            "host_species",
            tallies,
            discrepancies,
            pmid,
            pred.get(PRED_LABEL_COL["host_species"], ""),
            set(gt.get("host_species", [])),
        )
        _compare_field(
            "body_site",
            tallies,
            discrepancies,
            pmid,
            pred.get(PRED_LABEL_COL["body_site"], ""),
            set(gt.get("body_site_labels", [])),
            predicted_id=pred.get(PRED_ONTOLOGY_COL["body_site"], ""),
            ground_truth_ids=set(gt.get("body_site_ids", [])),
        )
        _compare_field(
            "condition",
            tallies,
            discrepancies,
            pmid,
            pred.get(PRED_LABEL_COL["condition"], ""),
            set(gt.get("condition_labels", [])),
            predicted_id=pred.get(PRED_ONTOLOGY_COL["condition"], ""),
            ground_truth_ids=set(gt.get("condition_ids", [])),
        )
        _compare_field(
            "sequencing_type",
            tallies,
            discrepancies,
            pmid,
            pred.get(PRED_LABEL_COL["sequencing_type"], ""),
            set(gt.get("sequencing_type", [])),
        )

        # sample_size: numeric membership, not string membership.
        pred_size_raw = (pred.get(PRED_LABEL_COL["sample_size"], "") or "").strip()
        gt_sizes = set(gt.get("sample_size", []))
        if pred_size_raw and gt_sizes:
            try:
                pred_size = int(float(pred_size_raw))
                agree = pred_size in gt_sizes
                tallies.setdefault("sample_size", FieldTally("sample_size")).record(
                    agree
                )
                if not agree:
                    discrepancies.append(
                        {
                            "PMID": pmid,
                            "field": "sample_size",
                            "predicted": pred_size_raw,
                            "ground_truth": "; ".join(str(s) for s in sorted(gt_sizes)),
                        }
                    )
            except ValueError:
                pass

    outdir = Path(args.output)
    outdir.mkdir(parents=True, exist_ok=True)

    summary_rows = []
    for key in sorted(tallies):
        t = tallies[key]
        summary_rows.append(
            {
                "field": key,
                "n_compared": t.n_compared,
                "n_agree": t.n_agree,
                "agreement_pct": round(t.pct, 1) if t.pct is not None else "",
            }
        )

    summary_csv = outdir / "summary.csv"
    with open(summary_csv, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(
            f, fieldnames=["field", "n_compared", "n_agree", "agreement_pct"]
        )
        w.writeheader()
        w.writerows(summary_rows)

    discrepancies_csv = outdir / "discrepancies.csv"
    with open(discrepancies_csv, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=["PMID", "field", "predicted", "ground_truth"])
        w.writeheader()
        w.writerows(discrepancies)

    summary_md = outdir / "summary.md"
    with open(summary_md, "w", encoding="utf-8") as f:
        f.write("# BioAnalyzer vs. BugSigDB ground-truth accuracy\n\n")
        f.write(
            f"Methodology: {len(matched_pmids)} PMID(s) compared, BioAnalyzer v1 "
            "(analyze_paper_simple) predictions vs. BugSigDB's existing curated "
            "signatures (full_dump.csv). Most PMIDs have multiple experiments in "
            "BugSigDB; a BioAnalyzer prediction is scored as agreement if it "
            "matches *any* of that PMID's distinct ground-truth values for that "
            "field (BioAnalyzer's v1/v2 pipelines extract one field-set per "
            "PMID, not per-experiment). Label comparisons are "
            "case/whitespace-normalized exact string matches, not semantic "
            'similarity - e.g. "gut" vs "feces" counts as disagreement.\n\n'
        )
        for row in summary_rows:
            field_label = row["field"].replace("_", " ")
            if row["agreement_pct"] == "":
                f.write(f"- **{field_label}**: no comparable data.\n")
            else:
                f.write(
                    f"- When comparing BioAnalyzer's extracted **{field_label}** to "
                    f"the human curated value, they agree **{row['agreement_pct']}%** "
                    f"of the time (n={row['n_compared']}).\n"
                )

    print(f"\nWrote {summary_csv}")
    print(f"Wrote {discrepancies_csv} ({len(discrepancies)} mismatches)")
    print(f"Wrote {summary_md}")
    print("\n" + summary_md.read_text())
    return 0


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)

    p_prepare = sub.add_parser(
        "prepare", help="Sample PMIDs + ground truth from full_dump.csv"
    )
    p_prepare.add_argument(
        "--dump", default="full_dump.csv", help="Path to full_dump.csv"
    )
    p_prepare.add_argument(
        "--limit", type=int, default=100, help="Number of PMIDs to sample (default 100)"
    )
    p_prepare.add_argument(
        "--all", action="store_true", help="Use every eligible PMID instead of sampling"
    )
    p_prepare.add_argument("--seed", type=int, default=42, help="Random sample seed")
    p_prepare.add_argument(
        "-o",
        "--output",
        default="results/bugsigdb_benchmark/pmids.txt",
        help="Output path for the plain PMID list",
    )
    p_prepare.set_defaults(func=cmd_prepare)

    p_compare = sub.add_parser(
        "compare", help="Compare BioAnalyzer predictions against sampled ground truth"
    )
    p_compare.add_argument(
        "--predictions", required=True, help="BioAnalyzer --format csv output"
    )
    p_compare.add_argument(
        "--ground-truth", required=True, help="*.ground_truth.json from `prepare`"
    )
    p_compare.add_argument(
        "-o", "--output", default="results/bugsigdb_benchmark", help="Output directory"
    )
    p_compare.set_defaults(func=cmd_compare)

    args = parser.parse_args()
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
