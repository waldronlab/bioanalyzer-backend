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
import logging
import random
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

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

        # Comma-split like Body site above: BugSigDB packs multiple conditions
        # into one cell, and leaving them joined made a correct single-value
        # prediction unmatchable (e.g. "nicotine dependence,smoking behavior").
        condition_raw = (row.get("Condition") or "").strip()
        if condition_raw and condition_raw != "NA":
            for label in condition_raw.split(","):
                label = _norm(label)
                if label and label != "na":
                    gt["condition_labels"].add(label)
        efo_raw = (row.get("EFO ID") or "").strip()
        if efo_raw and efo_raw != "NA":
            for oid in efo_raw.split(","):
                oid = _norm_id(oid)
                if oid:
                    gt["condition_ids"].add(oid)

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
    """Serialize the per-PMID ground-truth sets to sorted JSON lists.

    Each field is an unordered *set* of every distinct value BugSigDB curated
    across that PMID's experiments, sorted only to keep the file diffable.
    The `*_labels` and `*_ids` lists are therefore sorted independently and
    are NOT positional pairs - `body_site_labels[0]` need not be the label of
    `body_site_ids[0]`. Scoring never pairs them (a prediction is a hit if it
    matches any member of the relevant set), so this is correct as written,
    but do not read the file as if the two lists lined up.
    """
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
    """Agreement among papers where BioAnalyzer gave a value (`pct`), plus
    `n_blank`: papers where BugSigDB has a value but BioAnalyzer gave none.

    `pct` alone silently drops blank predictions from its denominator, which
    flatters any field BioAnalyzer often leaves blank - e.g. the 2026-08
    benchmark reported Condition ontology-ID agreement as 48/79 = 60.8%,
    leaving out 20 papers BugSigDB has a Condition ID for but BioAnalyzer
    gave none; counted as misses it is 48/99 = 48.5%. `pct_blank_as_miss`
    reports that view.
    """

    def __init__(self, name: str):
        self.name = name
        self.n_compared = 0
        self.n_agree = 0
        self.n_blank = 0

    def record(self, agree: bool) -> None:
        self.n_compared += 1
        if agree:
            self.n_agree += 1

    def record_blank(self) -> None:
        self.n_blank += 1

    @property
    def pct(self) -> Optional[float]:
        if self.n_compared == 0:
            return None
        return 100.0 * self.n_agree / self.n_compared

    @property
    def pct_blank_as_miss(self) -> Optional[float]:
        total = self.n_compared + self.n_blank
        if total == 0:
            return None
        return 100.0 * self.n_agree / total


class IoUTally:
    def __init__(self, name: str):
        self.name = name
        self.n_compared = 0
        self.total_iou = 0.0
        self.n_blank = 0

    def record(self, iou: float) -> None:
        self.n_compared += 1
        self.total_iou += iou

    def record_blank(self) -> None:
        self.n_blank += 1

    @property
    def mean(self) -> Optional[float]:
        if self.n_compared == 0:
            return None
        return self.total_iou / self.n_compared

    @property
    def mean_blank_as_miss(self) -> Optional[float]:
        total = self.n_compared + self.n_blank
        if total == 0:
            return None
        return self.total_iou / total


def _jaccard(predicted: Set[str], ground_truth: Set[str]) -> float:
    """Intersection-over-union between a predicted value set and the
    ground-truth set.

    BioAnalyzer predicts one value per field per paper - except Sequencing
    Type, which lists every method the paper used - so `predicted` is
    normally a singleton here and this reduces to 1/|ground_truth| when the
    prediction is a member, 0 otherwise. Still more informative than exact
    match for PMIDs where BugSigDB curates multiple distinct values per
    field (see classification "G" in benchmark_results/forensic_table.csv),
    since it reflects how large the ground-truth set was rather than just
    hit/miss. For the single-value fields this is a bounded proxy, not a
    measure of multi-value extraction capability; for Sequencing Type it is
    a real set overlap.
    """
    union = predicted | ground_truth
    if not union:
        return 0.0
    return len(predicted & ground_truth) / len(union)


# --- optional ontology-equivalence scoring (--synonym-scoring) --------------
# Exact string matching scores "Parkinson disease" against the curated
# "parkinson's disease" as a miss even though both name MONDO:0005180. This
# reports that agreement as an ADDITIONAL metric beside the strict one - never
# replacing it - and takes equivalence from the ontology's own label/synonym
# sets via the same strict lookup production uses, so it is not a similarity
# threshold anyone can tune until a run looks better.
_EQUIVALENCE_ENABLED = False
_EQUIVALENCE_ONTOLOGIES = {
    "condition": (("efo", "EFO"), ("mondo", "MONDO")),
    "body_site": (("uberon", "UBERON"),),
    "host_species": (("ncbitaxon", "NCBITaxon"),),
}
_CURIE_MEMO: Dict[Tuple[str, str], Optional[str]] = {}


def _resolve_curie(label: str, ontologies: Tuple[Tuple[str, str], ...]) -> Optional[str]:
    """CURIE for *label* if an ontology lists it as a term name/synonym."""
    for ontology, prefix in ontologies:
        key = (ontology, label)
        if key not in _CURIE_MEMO:
            from app.normalization.ols import ols_search  # lazy: needs network

            hit = ols_search(label, ontology, prefix)
            _CURIE_MEMO[key] = hit[1] if hit else None
        if _CURIE_MEMO[key]:
            return _CURIE_MEMO[key]
    return None


def _ontology_equivalent(field: str, pred_labels: Set[str], gt_labels: Set[str]) -> bool:
    ontologies = _EQUIVALENCE_ONTOLOGIES.get(field)
    if not ontologies:
        return False
    pred_ids = {c for c in (_resolve_curie(p, ontologies) for p in pred_labels) if c}
    if not pred_ids:
        return False
    gt_ids = {c for c in (_resolve_curie(g, ontologies) for g in gt_labels) if c}
    return bool(pred_ids & gt_ids)


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
    iou_tallies: Dict[str, IoUTally],
    discrepancies: List[Dict[str, str]],
    pmid: str,
    predicted_label: str,
    ground_truth_labels: Set[str],
    predicted_id: Optional[str] = None,
    ground_truth_ids: Optional[Set[str]] = None,
    multi_value_predicted: bool = False,
) -> None:
    # Sequencing Type lists every method a paper used, joined with "; "
    # (see app.normalization.sequencing_type); it agrees if any of them is
    # in the ground-truth set, and its IoU is a real set overlap.
    if multi_value_predicted:
        parts = (predicted_label or "").split(";")
        pred_set = {v for v in (_norm(p) for p in parts) if v}
    else:
        pred_set = {_norm(predicted_label)} - {""}
    label_key = f"{field}_label"
    syn_key = f"{label_key}_synonym_aware"
    if ground_truth_labels and not pred_set:
        tallies.setdefault(label_key, FieldTally(label_key)).record_blank()
        iou_tallies.setdefault(label_key, IoUTally(label_key)).record_blank()
        if _EQUIVALENCE_ENABLED:
            tallies.setdefault(syn_key, FieldTally(syn_key)).record_blank()
    elif pred_set and ground_truth_labels:
        agree = bool(pred_set & ground_truth_labels)
        tallies.setdefault(label_key, FieldTally(label_key)).record(agree)
        iou_tallies.setdefault(label_key, IoUTally(label_key)).record(
            _jaccard(pred_set, ground_truth_labels)
        )
        if not agree:
            discrepancies.append(
                {
                    "PMID": pmid,
                    "field": label_key,
                    "predicted": predicted_label,
                    "ground_truth": "; ".join(sorted(ground_truth_labels)),
                }
            )
        if _EQUIVALENCE_ENABLED:
            tallies.setdefault(syn_key, FieldTally(syn_key)).record(
                agree or _ontology_equivalent(field, pred_set, ground_truth_labels)
            )

    if predicted_id is not None and ground_truth_ids is not None:
        pred_id_norm = _norm_id(predicted_id)
        id_key = f"{field}_ontology_id"
        if ground_truth_ids and not pred_id_norm:
            tallies.setdefault(id_key, FieldTally(id_key)).record_blank()
            iou_tallies.setdefault(id_key, IoUTally(id_key)).record_blank()
        elif pred_id_norm and ground_truth_ids:
            agree = pred_id_norm in ground_truth_ids
            tallies.setdefault(id_key, FieldTally(id_key)).record(agree)
            iou_tallies.setdefault(id_key, IoUTally(id_key)).record(
                _jaccard({pred_id_norm}, ground_truth_ids)
            )
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
    global _EQUIVALENCE_ENABLED
    _EQUIVALENCE_ENABLED = bool(getattr(args, "synonym_scoring", False))
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
    iou_tallies: Dict[str, IoUTally] = {}
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
            iou_tallies,
            discrepancies,
            pmid,
            pred.get(PRED_LABEL_COL["host_species"], ""),
            set(gt.get("host_species", [])),
        )
        _compare_field(
            "body_site",
            tallies,
            iou_tallies,
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
            iou_tallies,
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
            iou_tallies,
            discrepancies,
            pmid,
            pred.get(PRED_LABEL_COL["sequencing_type"], ""),
            set(gt.get("sequencing_type", [])),
            multi_value_predicted=True,
        )

        # sample_size: numeric membership, not string membership.
        pred_size_raw = (pred.get(PRED_LABEL_COL["sample_size"], "") or "").strip()
        gt_sizes = set(gt.get("sample_size", []))
        if gt_sizes and not pred_size_raw:
            tallies.setdefault("sample_size", FieldTally("sample_size")).record_blank()
        elif pred_size_raw and gt_sizes:
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

    def _rounded(value: Optional[float], digits: int) -> Any:
        return round(value, digits) if value is not None else ""

    summary_rows = []
    for key in sorted(tallies):
        t = tallies[key]
        iou_t = iou_tallies.get(key)
        summary_rows.append(
            {
                "field": key,
                "n_compared": t.n_compared,
                "n_agree": t.n_agree,
                "agreement_pct": _rounded(t.pct, 1),
                "mean_iou": _rounded(iou_t.mean if iou_t else None, 3),
                "n_blank_prediction": t.n_blank,
                "agreement_pct_blank_as_miss": _rounded(t.pct_blank_as_miss, 1),
                "mean_iou_blank_as_miss": _rounded(
                    iou_t.mean_blank_as_miss if iou_t else None, 3
                ),
            }
        )

    summary_csv = outdir / "summary.csv"
    with open(summary_csv, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(
            f,
            fieldnames=[
                "field",
                "n_compared",
                "n_agree",
                "agreement_pct",
                "mean_iou",
                "n_blank_prediction",
                "agreement_pct_blank_as_miss",
                "mean_iou_blank_as_miss",
            ],
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
            'similarity - e.g. "gut" vs "feces" counts as disagreement. '
            "Each field's first figure covers only papers where BioAnalyzer "
            "gave a value; where it left the field blank for papers BugSigDB "
            "has a value for, a second figure counts those blanks as misses.\n\n"
        )
        if _EQUIVALENCE_ENABLED:
            f.write(
                "A `*_synonym_aware` row accompanies each label field below. It "
                "scores agreement when the predicted and curated values resolve "
                "to the *same ontology term*, taking equivalence from that "
                "ontology's own label and synonym lists rather than from a "
                "similarity threshold - so it credits "
                '"Parkinson disease" vs "parkinson\'s disease" (both '
                "MONDO:0005180) without being tunable to flatter a run. It is "
                "reported *in addition to* the exact-string figure, which is "
                "unchanged and remains the headline number.\n\n"
            )
        for row in summary_rows:
            field_label = row["field"].replace("_", " ")
            if row["agreement_pct"] == "":
                f.write(f"- **{field_label}**: no comparable data.\n")
                continue
            f.write(
                f"- When comparing BioAnalyzer's extracted **{field_label}** to "
                f"the human curated value, they agree **{row['agreement_pct']}%** "
                f"of the time (n={row['n_compared']})."
            )
            if row["n_blank_prediction"]:
                f.write(
                    f" Counting the {row['n_blank_prediction']} paper(s) "
                    "BioAnalyzer left blank as misses: "
                    f"**{row['agreement_pct_blank_as_miss']}%** "
                    f"(n={row['n_compared'] + row['n_blank_prediction']})."
                )
            f.write("\n")

        f.write("\n## Jaccard / IoU scoring (multi-value ground truth)\n\n")
        f.write(
            "BugSigDB often curates multiple experiments per PMID with distinct "
            "field values (e.g. different conditions per experiment). The "
            "agreement percentages above score a match if BioAnalyzer's single "
            "paper-level prediction matches *any* member of that set (full "
            "credit or none). Jaccard/IoU below is a stricter, additional lens: "
            "intersection-over-union between the predicted value and the full "
            "ground-truth set. BioAnalyzer predicts one value per field per "
            "paper - except Sequencing Type, which lists every method the "
            "paper used - so for the single-value fields this is a bounded "
            "proxy - 1/|ground truth set| when the prediction is correct, 0 "
            "when it isn't - that rewards matching a *small* ground-truth set "
            "more than a large one, not a measure of multi-value extraction "
            "capability. For Sequencing Type it is a real set overlap.\n\n"
        )
        for row in summary_rows:
            field_label = row["field"].replace("_", " ")
            if row["mean_iou"] == "":
                continue
            f.write(
                f"- **{field_label}**: mean IoU **{row['mean_iou']}** "
                f"(n={row['n_compared']})."
            )
            if row["n_blank_prediction"]:
                f.write(
                    " Counting blank predictions as 0: "
                    f"**{row['mean_iou_blank_as_miss']}**."
                )
            f.write("\n")

    print(f"\nWrote {summary_csv}")
    print(f"Wrote {discrepancies_csv} ({len(discrepancies)} mismatches)")
    print(f"Wrote {summary_md}")
    print("\n" + summary_md.read_text())
    return 0


# ---------------------------------------------------------------------------
# search-recall
# ---------------------------------------------------------------------------
#
# Question: "if a user searched for the curated term, would this paper be
# found?" A search for curated term X finds the paper when some predicted tag
# Y has ID == X, or X is an ontology ancestor of Y (a general search finds
# specific papers), or (label fallback) Y's label equals a curated label.
#
# Host species ground truth has labels only, so each curated label is mapped
# to an NCBITaxon ID with app.normalization.host_species.normalize_host_species
# and the label comparison is kept as a fallback. Ancestors come from OLS via
# app.normalization.ols.ancestor_ontologies: for MONDO/EFO/Orphanet/HP tags EFO
# is queried first (it imports those hierarchies) and then the prefix's own
# ontology, results unioned; other prefixes use their own ontology only.

SEARCH_FIELDS = ("condition", "body_site", "host_species")
SEARCH_LEVELS = ("top1", "tags_exact", "tags_hierarchy")
DEFAULT_ANCESTOR_CACHE = "cache/ontology_ancestors.json"
_ANCESTOR_SLEEP_SECONDS = 0.2


class AncestorCache:
    """JSON-file-backed CURIE -> ancestor-CURIE list. Failed lookups (None)
    are not stored, so a rerun retries them."""

    def __init__(self, path: Optional[Path] = None, fetcher: Any = None):
        self.path = path
        self._fetcher = fetcher
        self._data: Dict[str, List[str]] = {}
        self._dirty = False
        self._failed: Set[str] = set()  # in-memory only, never persisted
        if path and path.exists():
            try:
                self._data = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                self._data = {}

    @staticmethod
    def _key(curie: str) -> str:
        """CURIE plus the OLS ontologies that were queried for it, so a cache
        built with different ontology rules is never reused silently."""
        from app.normalization.ols import ancestor_ontologies

        return f"v3|{_norm_id(curie)}@{','.join(ancestor_ontologies(curie))}"

    def ancestors(self, curie: str) -> Set[str]:
        if not _norm_id(curie):
            return set()
        key = self._key(curie)
        if key in self._failed:
            return set()
        if key not in self._data:
            fetcher = self._fetcher
            if fetcher is None:
                from app.normalization.ols import fetch_ancestor_ids as fetcher

                time.sleep(_ANCESTOR_SLEEP_SECONDS)
            found = fetcher(curie.strip())  # original case: IRIs are case-sensitive
            if found is None:
                self._failed.add(key)
                return set()
            self._data[key] = sorted(_norm_id(a) for a in found)
            self._dirty = True
        return set(self._data[key])

    def save(self) -> None:
        if self.path and self._dirty:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            self.path.write_text(json.dumps(self._data, indent=1), encoding="utf-8")
            self._dirty = False


def _load_analyze_results(path: Path) -> Dict[str, Dict[str, Any]]:
    """PMID -> result dict from `analyze --format json` output (a list of
    results, one result, or {"results": [...]})."""
    data = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(data, dict) and isinstance(data.get("results"), list):
        data = data["results"]
    if isinstance(data, dict):
        data = [data]
    out: Dict[str, Dict[str, Any]] = {}
    for item in data if isinstance(data, list) else []:
        if isinstance(item, dict) and item.get("pmid") not in (None, ""):
            out[str(item["pmid"]).strip()] = item
    return out


def _predicted_tags(result: Optional[Dict[str, Any]], field: str):
    """(primary, tags) as lists of (label, id). Falls back to the primary
    value when a result predates `tags`."""
    fd = ((result or {}).get("fields") or {}).get(field) or {}
    primary = []
    if str(fd.get("status", "")).upper() != "ABSENT" and (
        fd.get("value") or fd.get("ontology_id")
    ):
        primary = [(fd.get("value") or "", fd.get("ontology_id") or "")]
    tags = [
        (t.get("label") or "", t.get("ontology_id") or "")
        for t in (fd.get("tags") or [])
        if isinstance(t, dict)
    ]
    return primary, (tags or primary)


def _resolve_host_label(label: str, host_resolver: Any, memo: Dict[str, str]) -> str:
    """NCBITaxon ID for a curated host label, memoized per label. A failing or
    empty resolution is remembered as "" (counted by the caller)."""
    if label not in memo:
        try:
            memo[label] = host_resolver(label) or ""
        except Exception as e:
            from app.utils.credential_masking import mask_exception_message

            logging.getLogger(__name__).debug(
                "Host label %r not resolved: %s", label, mask_exception_message(e)
            )
            memo[label] = ""
    return memo[label]


def _curated_terms(
    gt: Dict[str, Any],
    field: str,
    host_resolver: Any,
    host_memo: Optional[Dict[str, str]] = None,
):
    """(labels, ids) of normalized curated values for *field*."""
    if field == "host_species":
        memo = host_memo if host_memo is not None else {}
        labels = {_norm(v) for v in gt.get("host_species") or []} - {""}
        ids = set()
        for label in sorted(labels):
            oid = _resolve_host_label(label, host_resolver, memo)
            if oid:
                ids.add(_norm_id(oid))
        return labels, ids
    labels = {_norm(v) for v in gt.get(f"{field}_labels") or []} - {""}
    ids = {_norm_id(v) for v in gt.get(f"{field}_ids") or []} - {""}
    return labels, ids


def _host_resolver_default(label: str) -> str:
    from app.normalization.host_species import normalize_host_species

    return normalize_host_species(label).ontology_id


def _found(
    field: str,
    terms,
    labels: Set[str],
    ids: Set[str],
    hierarchy: bool,
    cache: Optional[AncestorCache],
    synonym_scoring: bool = False,
) -> bool:
    tag_ids = {_norm_id(i) for _, i in terms if i}
    original_case = {_norm_id(i): i.strip() for _, i in terms if i}
    tag_labels = {_norm(lab) for lab, _ in terms if lab}
    if tag_ids & ids or tag_labels & labels:
        return True
    if synonym_scoring and tag_labels and labels:
        if _ontology_equivalent(field, tag_labels, labels):
            return True
    if hierarchy and cache is not None and ids:
        for tid in sorted(tag_ids):
            if cache.ancestors(original_case[tid]) & ids:
                return True
    return False


def compute_search_recall(
    results: Dict[str, Dict[str, Any]],
    ground_truth: Dict[str, Dict[str, Any]],
    cache: Optional[AncestorCache] = None,
    host_resolver: Any = None,
    synonym_scoring: bool = False,
):
    """Returns (counts, misses). counts[field_or_'all'] = {"n": denominator,
    "top1": hits, "tags_exact": hits, "tags_hierarchy": hits}."""
    host_resolver = host_resolver or _host_resolver_default
    host_memo: Dict[str, str] = {}
    no_tags = 0
    counts = {f: {"n": 0, **{lv: 0 for lv in SEARCH_LEVELS}} for f in SEARCH_FIELDS}
    counts["all"] = {"n": 0, **{lv: 0 for lv in SEARCH_LEVELS}}
    misses: List[Dict[str, str]] = []
    for pmid, gt in ground_truth.items():
        result = results.get(str(pmid))
        per_field: Dict[str, Dict[str, bool]] = {}
        lacks_tags = False
        for field in SEARCH_FIELDS:
            labels, ids = _curated_terms(gt, field, host_resolver, host_memo)
            if not labels and not ids:
                continue
            fd = ((result or {}).get("fields") or {}).get(field)
            if isinstance(fd, dict) and "tags" not in fd:
                lacks_tags = True
            primary, tags = _predicted_tags(result, field)
            hit = {
                "top1": _found(
                    field, primary, labels, ids, False, None, synonym_scoring
                ),
                "tags_exact": _found(
                    field, tags, labels, ids, False, None, synonym_scoring
                ),
            }
            hit["tags_hierarchy"] = hit["tags_exact"] or _found(
                field, tags, labels, ids, True, cache, synonym_scoring
            )
            counts[field]["n"] += 1
            for lv in SEARCH_LEVELS:
                counts[field][lv] += int(hit[lv])
            per_field[field] = hit
            if not hit["tags_hierarchy"]:
                misses.append(
                    {
                        "PMID": str(pmid),
                        "field": field,
                        "curated": "; ".join(sorted(ids | labels)),
                        "predicted_tags": "; ".join(
                            f"{lab}|{i}" for lab, i in tags
                        )
                        if result is not None
                        else "(paper missing from results)",
                    }
                )
        no_tags += int(lacks_tags)
        if len(per_field) == len(SEARCH_FIELDS):
            counts["all"]["n"] += 1
            for lv in SEARCH_LEVELS:
                counts["all"][lv] += int(all(per_field[f][lv] for f in SEARCH_FIELDS))
    unresolved = sorted(label for label, oid in host_memo.items() if not oid)
    if unresolved:
        logging.getLogger(__name__).warning(
            "%d curated host label(s) did not resolve to an NCBITaxon ID "
            "(label match only): %s",
            len(unresolved),
            "; ".join(unresolved[:10]),
        )
    counts["_meta"] = {
        "results_without_tags": no_tags,
        "unresolved_host_labels": len(unresolved),
    }
    return counts, misses


def cmd_search_recall(args: argparse.Namespace) -> int:
    results = _load_analyze_results(Path(args.results))
    ground_truth = json.loads(Path(args.ground_truth).read_text(encoding="utf-8"))
    cache = AncestorCache(Path(args.ancestor_cache))
    counts, misses = compute_search_recall(
        results, ground_truth, cache, synonym_scoring=args.synonym_scoring
    )
    cache.save()
    meta = counts["_meta"]
    if meta["results_without_tags"]:
        print(
            f"WARNING: {meta['results_without_tags']} paper(s) have results "
            "without `tags` (cached older results); their primary value was "
            "used as the only tag. Re-run analysis for a true tag score.",
            file=sys.stderr,
        )
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)

    def _pct(hits: int, n: int) -> str:
        return f"{hits / n:.3f}" if n else ""

    rows = []
    for field in (*SEARCH_FIELDS, "all"):
        c = counts[field]
        rows.append(
            {
                "field": field,
                "n_papers": c["n"],
                **{f"recall_{lv}": _pct(c[lv], c["n"]) for lv in SEARCH_LEVELS},
                **{f"hits_{lv}": c[lv] for lv in SEARCH_LEVELS},
            }
        )
    with open(out / "summary.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)
    with open(out / "misses.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(
            f, fieldnames=["PMID", "field", "curated", "predicted_tags"]
        )
        w.writeheader()
        w.writerows(misses)
    lines = [
        "# Search recall",
        "",
        f"Results: {len(results)} papers; ground truth: {len(ground_truth)} papers.",
        "A paper counts if ANY curated ID is found. Denominator: ground-truth "
        "papers with a curated value for the field (papers missing from the "
        "results count as misses). `all` = papers curated for all three fields, "
        "found on all three.",
        "Host species ground truth is labels only: labels are mapped to "
        "NCBITaxon with normalize_host_species, label match is a fallback "
        f"({meta['unresolved_host_labels']} curated host label(s) did not resolve).",
        f"Papers whose results lack a `tags` key (primary used as the only "
        f"tag): {meta['results_without_tags']}.",
        "",
        "| field | n | top1 | tags exact | tags hierarchy |",
        "|---|---|---|---|---|",
    ]
    for r in rows:
        lines.append(
            f"| {r['field']} | {r['n_papers']} | {r['recall_top1']} | "
            f"{r['recall_tags_exact']} | {r['recall_tags_hierarchy']} |"
        )
    (out / "summary.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("\n".join(lines))
    print(f"\nWrote {out}/summary.md, summary.csv, misses.csv ({len(misses)} misses)")
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
    p_compare.add_argument(
        "--synonym-scoring",
        action="store_true",
        help=(
            "Additionally report label agreement where prediction and curated "
            "value resolve to the same ontology term (needs network: live OLS "
            "lookups). Reported beside the exact-string figure, never instead."
        ),
    )
    p_compare.set_defaults(func=cmd_compare)

    p_recall = sub.add_parser(
        "search-recall",
        help="Would a search for the curated term find the paper? (tags + hierarchy)",
    )
    p_recall.add_argument(
        "--results", required=True, help="`BioAnalyzer analyze --format json` output"
    )
    p_recall.add_argument(
        "--ground-truth", required=True, help="*.ground_truth.json from `prepare`"
    )
    p_recall.add_argument("--out", required=True, help="Output directory")
    p_recall.add_argument(
        "--ancestor-cache",
        default=DEFAULT_ANCESTOR_CACHE,
        help="JSON cache of OLS ancestors (default %(default)s)",
    )
    p_recall.add_argument(
        "--synonym-scoring",
        action="store_true",
        help="Also count label matches that resolve to the same ontology term "
        "(live OLS lookups)",
    )
    p_recall.set_defaults(func=cmd_search_recall)

    args = parser.parse_args()
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
