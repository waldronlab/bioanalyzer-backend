#!/usr/bin/env python3
"""Grounding-engine benchmark: precision/recall/F1/ambiguity/review-rate/
latency for `app.normalization.grounding.ground()` - the four-step
round-trip/obsolete/branch discipline, not the LLM extraction pipeline.

Deliberately does not touch BugSigDB's ground-truth corpus or make any LLM
call (see `scripts/eval/bugsigdb_ground_truth_benchmark.py` for that, a
separate, heavier, human-in-the-loop benchmark that costs real API money
and validates PRESENT/ABSENT/PARTIALLY_PRESENT *status* extraction, not
ontology-ID correctness). This script is fully offline and deterministic:
it exercises `ground()` directly against real static-dict entries (known-
good) and a hand-curated set of known-bad CURIEs (fabricated, real-
obsolete, wrong-branch), so re-running it always produces the same numbers
against the same local ontology store - see docs/GROUNDING_ARCHITECTURE.md
for why that reproducibility property matters to this subsystem.

Framing: at the tier-assignment gate, "auto" is a positive prediction
("safe to apply without curator review") and "review"/"none" is negative.
A known-good static-dict entry (the ~110 hand-curated, previously-audited
(label, curie) pairs in SPECIES_LOOKUP/BODY_SITE_LOOKUP/CONDITION_LOOKUP)
staying "auto" is a true positive; landing on "review" is a false negative
(over-cautious, annoying but not dangerous). A known-bad injected case
(fabricated CURIE, real obsolete CURIE, or a real term from the wrong
ontology branch) correctly landing on "review" is a true negative;
incorrectly staying "auto" is a false positive - the dangerous case this
whole subsystem exists to prevent (see the 2026-07 incident referenced in
tiering.py's module docstring).

Usage:
    python scripts/eval/grounding_benchmark.py
    python scripts/eval/grounding_benchmark.py --db-path ontology_store/ontology_store.db
"""

from __future__ import annotations

import argparse
import statistics
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import List

project_root = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(project_root))

from app.normalization.body_site import BODY_SITE_LOOKUP  # noqa: E402
from app.normalization.condition import CONDITION_LOOKUP  # noqa: E402
from app.normalization.grounding import TIER_AUTO, ground  # noqa: E402
from app.normalization.host_species import SPECIES_LOOKUP  # noqa: E402
from app.normalization.types import NormalizedTerm  # noqa: E402


@dataclass(frozen=True)
class Case:
    group: str  # which static dict / injected-bad category
    label: str
    ontology_id: str
    expect_auto: bool  # True = known-good (should stay auto), False = known-bad


def _static_dict_cases() -> List[Case]:
    cases: List[Case] = []
    for group, lookup in (
        ("host_species", SPECIES_LOOKUP),
        ("body_site", BODY_SITE_LOOKUP),
        ("condition", CONDITION_LOOKUP),
    ):
        seen = set()
        for _key, (label, curie) in lookup.items():
            if not curie or curie in seen:
                continue  # entries with no ontology_id (e.g. "healthy") aren't a grounding case
            seen.add(curie)
            cases.append(Case(group, label, curie, expect_auto=True))
    return cases


# Hand-curated known-bad cases: fabricated CURIEs (never real), real
# obsolete CURIEs (confirmed obsolete in the actual synced dumps - see
# docs/GROUNDING_ARCHITECTURE.md for how each was found), and real terms
# from a technically-real but semantically-wrong branch of their ontology.
# Every "real" CURIE below was verified against the actual local store
# before being hardcoded here - not guessed.
_INJECTED_BAD_CASES: List[Case] = [
    Case("fabricated", "fake disease", "MONDO:9999999", expect_auto=False),
    Case("fabricated", "fake taxon", "NCBITaxon:99999999999", expect_auto=False),
    Case("fabricated", "fake body site", "UBERON:9999999", expect_auto=False),
    Case("fabricated", "fake chemical", "CHEBI:99999999", expect_auto=False),
    Case("fabricated", "fake disease (doid)", "DOID:9999999", expect_auto=False),
    Case(
        "real_obsolete",
        "obsolete 2-hydroxyglutaric aciduria",
        "MONDO:0000360",
        expect_auto=False,
    ),
    Case(
        "real_obsolete",
        "obsolete Batten Turner congenital myopathy",
        "DOID:0080100",
        expect_auto=False,
    ),
    Case(
        "real_obsolete",
        "obsolete_asthma",
        "EFO:0000270",
        expect_auto=False,
    ),
    Case(
        "wrong_branch",
        "Escherichia coli (bacterium, not a valid Eukaryota host species)",
        "NCBITaxon:562",
        expect_auto=False,
    ),
    Case(
        "wrong_branch",
        "antimicrobial agent (CHEBI role branch, not a chemical entity)",
        "CHEBI:33281",
        expect_auto=False,
    ),
]


def _make_term(case: Case) -> NormalizedTerm:
    return NormalizedTerm(
        label=case.label,
        ontology_id=case.ontology_id,
        status="PRESENT",
        mapping_confidence=1.0,
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--db-path", default=None, help="override LOCAL_ONTOLOGY_DB_PATH"
    )
    args = parser.parse_args()

    if args.db_path:
        import os

        os.environ["LOCAL_ONTOLOGY_DB_PATH"] = args.db_path

    cases = _static_dict_cases() + _INJECTED_BAD_CASES
    tp = fp = tn = fn = 0
    tier_counts = {"auto": 0, "review": 0, "none": 0}
    latencies_ms: List[float] = []
    failures: List[str] = []

    for case in cases:
        term = _make_term(case)
        start = time.perf_counter()
        decision = ground(term)
        latencies_ms.append((time.perf_counter() - start) * 1000)
        tier_counts[decision.tier] = tier_counts.get(decision.tier, 0) + 1

        predicted_auto = decision.tier == TIER_AUTO
        if case.expect_auto and predicted_auto:
            tp += 1
        elif case.expect_auto and not predicted_auto:
            fn += 1
            failures.append(
                f"FALSE NEGATIVE [{case.group}] {case.ontology_id} ({case.label!r}) "
                f"-> {decision.tier}: {decision.reason}"
            )
        elif not case.expect_auto and not predicted_auto:
            tn += 1
        else:  # not case.expect_auto and predicted_auto
            fp += 1
            failures.append(
                f"FALSE POSITIVE [{case.group}] {case.ontology_id} ({case.label!r}) "
                f"-> {decision.tier}: {decision.reason}"
            )

    total = len(cases)
    precision = tp / (tp + fp) if (tp + fp) else float("nan")
    recall = tp / (tp + fn) if (tp + fn) else float("nan")
    f1 = (
        2 * precision * recall / (precision + recall)
        if (precision + recall) and precision == precision and recall == recall
        else float("nan")
    )
    review_rate = tier_counts.get("review", 0) / total
    ambiguity_rate = (
        total - tier_counts.get("auto", 0) - tier_counts.get("none", 0)
    ) / total
    latencies_ms.sort()
    p50 = statistics.median(latencies_ms)
    p95 = latencies_ms[int(len(latencies_ms) * 0.95) - 1]
    p99 = latencies_ms[int(len(latencies_ms) * 0.99) - 1]

    print(
        f"Grounding benchmark - {total} cases "
        f"({len(_static_dict_cases())} known-good static-dict entries, "
        f"{len(_INJECTED_BAD_CASES)} injected known-bad cases)"
    )
    print()
    print(f"Confusion matrix: TP={tp} FP={fp} TN={tn} FN={fn}")
    print(f"Tier distribution: {tier_counts}")
    print()
    print(f"Precision (of 'auto' calls, how many are truly good): {precision:.1%}")
    print(f"Recall (of known-good cases, how many stayed 'auto'):  {recall:.1%}")
    print(f"F1: {f1:.3f}" if f1 == f1 else "F1: n/a")
    print(f"Review rate (all cases landing on 'review'): {review_rate:.1%}")
    print(f"Ambiguity rate (not auto, not none): {ambiguity_rate:.1%}")
    print(f"False positive rate: {fp}/{total} ({fp/total:.1%}) - the dangerous case")
    print()
    print(
        f"Latency: p50={p50:.2f}ms  p95={p95:.2f}ms  p99={p99:.2f}ms  "
        f"max={max(latencies_ms):.2f}ms"
    )
    print()

    if failures:
        print(f"{len(failures)} case(s) did not match expectation:")
        for line in failures:
            print(f"  {line}")
        print()

    # The only hard failure condition: a false positive (a known-bad case
    # incorrectly auto-applied) - that's the exact incident class this
    # subsystem exists to prevent. False negatives (known-good cases
    # downgraded to review) are logged but don't fail the run - they're
    # over-caution, not a safety defect, and can legitimately happen if an
    # upstream ontology genuinely changes.
    if fp > 0:
        print(f"FAIL: {fp} false positive(s) - a known-bad case was auto-applied.")
        return 1
    print("PASS: zero false positives.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
