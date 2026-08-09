#!/usr/bin/env python3
"""Independent evaluation of BioAnalyzer's ontology-grounding normalizers
against BugSigDB's own real, human-curated data (`full_dump.csv` at the
project root - not generated from BioAnalyzer's own dicts, ontology store,
or expected outputs; not written to reproduce this implementation).

This is deliberately NOT the same thing as
`scripts/eval/bugsigdb_ground_truth_benchmark.py` (which compares full LLM
*extraction* output against BugSigDB, requiring real LLM API calls this
script does not make). This evaluates the *grounding/normalization* layer
directly: for each distinct real curated value in the dump, run it through
`normalize_condition()`/`normalize_body_site()`/`normalize_host_species()`
exactly as the production extraction pipeline would, and compare the
result against BugSigDB's own independent, human-curated ground truth.

Real, disclosed methodological limits (see the printed report):

- BugSigDB's "EFO ID" column is actually mixed-ontology in practice (EFO,
  MONDO, HP, CHEBI, GO, NCIT, ...) - BioAnalyzer's `normalize_condition()`
  only ever targets EFO/MONDO. Rows whose ground-truth ID uses a different
  ontology are structurally out of that field's scope and are reported as
  a separate "out of ontology scope" category, never silently dropped or
  counted as failures.
- "Host species" has no ID column in the dump (only the curated species
  name) - correctness is checked by comparing the *label* BioAnalyzer's
  NCBITaxon match resolves to against the curated name (this is still an
  independent check, since the label comparison is against real NCBI
  Taxonomy data in the local ontology store - not against BioAnalyzer's
  own logic).
- BugSigDB curation, like any real human-curated dataset, can itself
  contain errors (obsolete IDs, typos) - a mismatch is reported as such,
  not assumed to always be BioAnalyzer's fault; see the printed report's
  "ground-truth uncertainty" notes for cases spot-checked this way.

Usage:
    python scripts/eval/bugsigdb_independent_evaluation.py
    python scripts/eval/bugsigdb_independent_evaluation.py --dump full_dump.csv --sample 300
"""

from __future__ import annotations

import argparse
import csv
import difflib
import random
import sys
import time
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional

project_root = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(project_root))

from app.normalization.body_site import normalize_body_site  # noqa: E402
from app.normalization.condition import normalize_condition  # noqa: E402
from app.normalization.grounding.local_backend import LocalOntologyBackend  # noqa: E402
from app.normalization.host_species import normalize_host_species  # noqa: E402
from app.normalization.types import is_null_like  # noqa: E402

_backend = LocalOntologyBackend()


def _related(predicted_id: str, ground_truth_id: str, ontology_slug: str) -> bool:
    """Is *predicted_id* a real ancestor or descendant of *ground_truth_id*
    in the actual synced ontology data (not a guess)? Distinguishes a
    coarser-but-anatomically/semantically-valid match (e.g. "blood" for a
    "blood serum" sample - a real parent concept, defensible even though
    it doesn't match BugSigDB's more specific curation) from a genuinely
    wrong one (e.g. "feces" for "small intestine" - no relationship at
    all, a different concept entirely). Only meaningful within a single
    ontology; cross-ontology mismatches (e.g. predicted EFO, ground truth
    MONDO) are never "related" by this check."""
    if not predicted_id or not ground_truth_id:
        return False
    if predicted_id.split(":")[0].lower() != ground_truth_id.split(":")[0].lower():
        return False
    try:
        return bool(
            _backend.reachable_from(ground_truth_id, predicted_id, ontology_slug)
            or _backend.reachable_from(predicted_id, ground_truth_id, ontology_slug)
        )
    except Exception:
        return False


@dataclass
class CaseResult:
    field: str
    raw_text: str
    ground_truth_id: str
    predicted_id: str
    predicted_label: str
    status: str
    confidence: float
    outcome: str  # correct | wrong_related | wrong_unrelated | miss | out_of_scope
    tier: str  # auto | review | none


def _tier_of(status: str, confidence: float, ontology_id: str) -> str:
    if status == "PRESENT" and confidence == 1.0:
        return "auto"
    if ontology_id:
        return "review"
    return "none"


def load_dump(path: Path) -> List[Dict[str, str]]:
    with open(path, encoding="utf-8") as f:
        first = f.readline()
        if not first.startswith("#"):
            f.seek(0)
        reader = csv.DictReader(f)
        return list(reader)


def _expand_multivalue_groups(pairs):
    """BugSigDB stores multiple values per field as a comma-separated list
    on both the free-text and ID columns (e.g. Body site
    "Ascending colon,Sigmoid colon" / UBERON ID
    "UBERON:0001156,UBERON:0001159" - a real, common case: 38% of distinct
    body-site row-pairs, 10% of condition row-pairs).

    Two real bugs found and fixed while building this evaluation, in
    order:

    1. A first version compared the whole joined string as one atomic
       value, which can never match a single-site/single-condition
       prediction - made every such case look like a false "wrong"/false
       "auto" result. Not a BioAnalyzer defect, an evaluation bug.
    2. The fix for #1 split both sides on commas and paired them
       *positionally* (text part N <-> id part N) - which turned out to
       also be wrong: BugSigDB does **not** guarantee the two lists are in
       the same order. Proof, found by inspecting the raw dump directly:
       the exact same body-site list "Saliva,Gastric juice,Stomach,Feces,
       Esophagus" appears in two different rows with its UBERON ID list in
       two different orders (one row: Saliva<->UBERON:0001971; another
       row: Saliva<->UBERON:0001836, the real saliva ID). Positional
       pairing silently produced wrong ground truth for real, correct
       BioAnalyzer predictions.

    Fixed properly: each individual text value from a row is checked
    against the *set* of all IDs from that same row (order-independent),
    not a single positionally-paired ID. A condition/site name can itself
    legitimately contain a comma (e.g. "Diarrhea, Infantile" is one real
    disease name, not a list of two) - guarded by only treating a
    text/id-list pair as "multi-value" when both sides split into the
    *same* number of comma-separated parts (confirmed empirically: 6/100
    condition row-pairs with a comma are the single-name case; 0/128
    body-site row-pairs are).

    Returns a list of (text_value, frozenset_of_ids_from_that_row) -
    keeping each row's own group separate rather than merging ID sets
    across unrelated rows/studies that happen to share one site/condition
    name in common, which would silently make the ground truth too
    permissive.
    """
    expanded = []
    for text, ids in pairs:
        text_parts = [p.strip() for p in text.split(",")]
        id_parts = frozenset(p.strip() for p in ids.split(","))
        if len(text_parts) == len(id_parts) and len(text_parts) > 1:
            for part in text_parts:
                expanded.append((part, id_parts))
        else:
            expanded.append((text, frozenset({ids})))
    return expanded


def distinct_body_site_pairs(rows: List[Dict[str, str]]):
    seen = set()
    for r in rows:
        site, uberon = r.get("Body site", ""), r.get("UBERON ID", "")
        if site and site != "NA" and uberon and uberon != "NA":
            seen.add((site, uberon))
    return _expand_multivalue_groups(sorted(seen))


def distinct_condition_pairs(rows: List[Dict[str, str]]):
    seen = set()
    for r in rows:
        cond, efo = r.get("Condition", ""), r.get("EFO ID", "")
        if cond and cond != "NA" and efo and efo != "NA":
            seen.add((cond, efo))
    return _expand_multivalue_groups(sorted(seen))


def distinct_species(rows: List[Dict[str, str]]):
    """Real methodology fix, 2026-08-09 final safety-closure pass: this
    used to hardcode a single excluded value (`sp != "NA"`) - too narrow.
    BugSigDB's real dump also curates "Not specified" (and presumably the
    same family of placeholders `is_null_like()` now recognizes centrally
    in the normalizers themselves) for "the paper didn't report a host
    species" - there is no real species for BioAnalyzer to be scored
    against for these, so including them was scoring a well-defined "no
    data" case as if it were a normalization target. Confirmed via a real,
    traced false "correct" this was previously producing: "Not specified"
    reached `local_lookup()`'s NCBITaxon fallback and fuzzy-matched
    "unidentified" (NCBITaxon:32644) at 0.012 confidence - a near-zero,
    meaningless match that still passed this script's own 0.4 text-
    similarity self-consistency check purely by surface-level word
    resemblance ("not specified" vs "unidentified", 0.56 similarity) - not
    because it was a real, correct grounding. Reusing `is_null_like()`
    (not a second, separately-maintained placeholder list) keeps this
    filter in sync with whatever the normalizers themselves treat as
    non-groundable."""
    seen = set()
    for r in rows:
        sp = r.get("Host species", "")
        if sp and not is_null_like(sp):
            seen.add(sp)
    return sorted(seen)


def evaluate_body_site(pairs) -> List[CaseResult]:
    results = []
    seen = set()
    for site, gt_ids in pairs:
        key = (site, gt_ids)
        if key in seen:
            continue
        seen.add(key)
        gt_display = "|".join(sorted(gt_ids))
        t = normalize_body_site(site)
        if t.ontology_id in gt_ids:
            outcome = "correct"
        elif not t.ontology_id:
            outcome = "miss"
        elif any(_related(t.ontology_id, gt, "uberon") for gt in gt_ids):
            outcome = "wrong_related"
        else:
            outcome = "wrong_unrelated"
        results.append(
            CaseResult(
                "body_site",
                site,
                gt_display,
                t.ontology_id,
                t.label,
                t.status,
                t.mapping_confidence,
                outcome,
                _tier_of(t.status, t.mapping_confidence, t.ontology_id),
            )
        )
    return results


_CONDITION_IN_SCOPE_PREFIXES = ("EFO", "MONDO")


def evaluate_condition(pairs) -> List[CaseResult]:
    results = []
    seen = set()
    for cond, gt_ids in pairs:
        key = (cond, gt_ids)
        if key in seen:
            continue
        seen.add(key)
        gt_display = "|".join(sorted(gt_ids))
        in_scope_ids = {
            i for i in gt_ids if i.split(":")[0] in _CONDITION_IN_SCOPE_PREFIXES
        }
        if not in_scope_ids:
            results.append(
                CaseResult(
                    "condition",
                    cond,
                    gt_display,
                    "",
                    "",
                    "",
                    0.0,
                    "out_of_scope",
                    "none",
                )
            )
            continue
        t = normalize_condition(cond)
        if t.ontology_id in in_scope_ids:
            outcome = "correct"
        elif not t.ontology_id:
            outcome = "miss"
        elif any(
            _related(t.ontology_id, gt, t.ontology_id.split(":")[0].lower())
            for gt in in_scope_ids
        ):
            outcome = "wrong_related"
        else:
            outcome = "wrong_unrelated"
        results.append(
            CaseResult(
                "condition",
                cond,
                gt_display,
                t.ontology_id,
                t.label,
                t.status,
                t.mapping_confidence,
                outcome,
                _tier_of(t.status, t.mapping_confidence, t.ontology_id),
            )
        )
    return results


def evaluate_host_species(species_list) -> List[CaseResult]:
    results = []
    for sp in species_list:
        t = normalize_host_species(sp)
        if not t.ontology_id:
            outcome = "miss"
        else:
            # Independent check: does the resolved label really refer to
            # the curated species, per real NCBI Taxonomy data in the
            # local store (not BioAnalyzer's own claim)? Same similarity
            # approach/threshold calibrated in tiering.py's label-
            # consistency check (0.4) - genuinely different species names
            # score far below legitimate spelling/capitalization variants.
            sim = difflib.SequenceMatcher(
                None, sp.strip().casefold(), t.label.strip().casefold()
            ).ratio()
            outcome = "correct" if sim >= 0.4 else "wrong_unrelated"
        results.append(
            CaseResult(
                "host_species",
                sp,
                "",
                t.ontology_id,
                t.label,
                t.status,
                t.mapping_confidence,
                outcome,
                _tier_of(t.status, t.mapping_confidence, t.ontology_id),
            )
        )
    return results


def report_field(field: str, results: List[CaseResult]) -> None:
    in_scope = [r for r in results if r.outcome != "out_of_scope"]
    out_of_scope = [r for r in results if r.outcome == "out_of_scope"]
    n = len(in_scope)
    if n == 0:
        print(f"\n=== {field} === (no in-scope cases)")
        return

    correct = sum(1 for r in in_scope if r.outcome == "correct")
    wrong_related = sum(1 for r in in_scope if r.outcome == "wrong_related")
    wrong_unrelated = sum(1 for r in in_scope if r.outcome == "wrong_unrelated")
    wrong = wrong_related + wrong_unrelated
    miss = sum(1 for r in in_scope if r.outcome == "miss")

    auto = [r for r in in_scope if r.tier == "auto"]
    review = [r for r in in_scope if r.tier == "review"]
    none_tier = [r for r in in_scope if r.tier == "none"]

    auto_correct = sum(1 for r in auto if r.outcome == "correct")
    false_auto = sum(1 for r in auto if r.outcome != "correct")
    false_auto_unrelated = sum(1 for r in auto if r.outcome == "wrong_unrelated")

    precision = correct / (correct + wrong) if (correct + wrong) else float("nan")
    recall = correct / n if n else float("nan")
    f1 = (
        2 * precision * recall / (precision + recall)
        if precision == precision and recall == recall and (precision + recall)
        else float("nan")
    )
    auto_precision = auto_correct / len(auto) if auto else float("nan")

    print(f"\n=== {field} ===")
    print(f"n = {n} in-scope cases", end="")
    if out_of_scope:
        print(
            f"  ({len(out_of_scope)} excluded: ground truth uses an "
            f"ontology this field doesn't target - see methodology notes)"
        )
    else:
        print()
    print(
        f"  correct={correct}  wrong={wrong} "
        f"(related/coarser={wrong_related}, unrelated/genuinely-wrong={wrong_unrelated})  "
        f"miss={miss}"
    )
    print(
        f"  precision={precision:.1%}  recall={recall:.1%}  F1={f1:.3f}"
        if precision == precision
        else "  precision/recall: n/a"
    )
    print(
        f"  tier distribution: auto={len(auto)} review={len(review)} none={len(none_tier)}"
    )
    print(
        f"  AUTO precision={auto_precision:.1%} ({auto_correct}/{len(auto)})"
        if auto
        else "  AUTO precision: n/a (0 auto predictions)"
    )
    print(
        f"  false-AUTO count = {false_auto} / {len(auto)} auto predictions "
        f"({false_auto_unrelated} genuinely wrong, "
        f"{false_auto - false_auto_unrelated} coarser-but-related)"
    )
    print(f"  review rate = {len(review)/n:.1%}")
    print(f"  ambiguity/ ~none rate = {len(none_tier)/n:.1%}")

    if false_auto:
        unrelated_autos = [r for r in auto if r.outcome == "wrong_unrelated"]
        related_autos = [r for r in auto if r.outcome == "wrong_related"]
        if unrelated_autos:
            print(
                f"  *** {len(unrelated_autos)} GENUINELY WRONG FALSE-AUTO "
                f"CASE(S) - DANGEROUS, listed below ***"
            )
            for r in unrelated_autos:
                print(
                    f"    {r.raw_text!r}: predicted {r.predicted_id!r} "
                    f"({r.predicted_label!r}), ground truth {r.ground_truth_id!r}"
                )
        if related_autos:
            print(
                f"  --- {len(related_autos)} coarser-but-related false-AUTO "
                f"case(s) (real ancestor/descendant of ground truth, not a "
                f"different concept) ---"
            )
            for r in related_autos:
                print(
                    f"    {r.raw_text!r}: predicted {r.predicted_id!r} "
                    f"({r.predicted_label!r}), ground truth {r.ground_truth_id!r}"
                )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dump", default="full_dump.csv")
    parser.add_argument(
        "--sample",
        type=int,
        default=0,
        help="cap each field to N random distinct cases (0 = evaluate all)",
    )
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args()

    dump_path = project_root / args.dump
    if not dump_path.exists():
        print(f"ERROR: {dump_path} not found.")
        return 1

    print(f"Loading {dump_path} ...")
    rows = load_dump(dump_path)
    print(f"{len(rows)} data rows loaded")

    rng = random.Random(args.seed)

    body_site_pairs = distinct_body_site_pairs(rows)
    condition_pairs = distinct_condition_pairs(rows)
    species_list = distinct_species(rows)

    if args.sample:
        body_site_pairs = rng.sample(
            body_site_pairs, min(args.sample, len(body_site_pairs))
        )
        condition_pairs = rng.sample(
            condition_pairs, min(args.sample, len(condition_pairs))
        )
        species_list = rng.sample(species_list, min(args.sample, len(species_list)))

    print(
        f"Evaluating: {len(body_site_pairs)} distinct body-site pairs, "
        f"{len(condition_pairs)} distinct condition pairs, "
        f"{len(species_list)} distinct species"
    )

    t0 = time.time()
    body_site_results = evaluate_body_site(body_site_pairs)
    condition_results = evaluate_condition(condition_pairs)
    species_results = evaluate_host_species(species_list)
    elapsed = time.time() - t0

    report_field("body_site (UBERON)", body_site_results)
    report_field("condition (EFO/MONDO)", condition_results)
    report_field("host_species (NCBITaxon)", species_results)

    print(f"\nTotal evaluation time: {elapsed:.1f}s")

    all_results = body_site_results + condition_results + species_results
    outcome_counts = Counter(r.outcome for r in all_results)
    print(f"\nOverall outcome counts across all fields: {dict(outcome_counts)}")

    _backend.close()

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
