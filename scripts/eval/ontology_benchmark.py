#!/usr/bin/env python3
"""
Ontology mapping benchmark (long-term vision: 90%+ precision target).

Evaluates BioAnalyzer normalizers against a gold-standard fixture.
Extend GOLD_CASES with BugSigDB-validated term pairs for production benchmarking.

Usage:
  python scripts/eval/ontology_benchmark.py
"""

from __future__ import annotations

import sys
from dataclasses import dataclass
from pathlib import Path

project_root = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(project_root))

from app.normalization.body_site import normalize_body_site
from app.normalization.condition import normalize_condition
from app.normalization.host_species import normalize_host_species
from app.normalization.sequencing_type import normalize_sequencing_type


@dataclass(frozen=True)
class GoldCase:
    field: str
    raw: str
    expected_label: str
    expected_ontology_id: str = ""


GOLD_CASES = [
    GoldCase("host_species", "humans", "Homo sapiens", "NCBITaxon:9606"),
    GoldCase("host_species", "mice", "Mus musculus", "NCBITaxon:10090"),
    GoldCase("body_site", "stool samples", "feces", "UBERON:0001988"),
    GoldCase("body_site", "saliva", "saliva", "UBERON:0001836"),
    GoldCase("condition", "Parkinson's disease", "Parkinson disease", "MONDO:0005180"),
    GoldCase(
        "condition", "type 2 diabetes", "type 2 diabetes mellitus", "MONDO:0005148"
    ),
    GoldCase("condition", "obese adults", "obesity disorder", "MONDO:0011122"),
    GoldCase("sequencing_type", "16S rRNA gene sequencing", "16S", ""),
    # shotgun and metagenomics are in the same BugSigDB-compatible family
    GoldCase("sequencing_type", "shotgun metagenomics", "metagenomics", ""),
]


NORMALIZERS = {
    "host_species": normalize_host_species,
    "body_site": normalize_body_site,
    "condition": normalize_condition,
    "sequencing_type": normalize_sequencing_type,
}


def main() -> int:
    correct = 0
    total = len(GOLD_CASES)
    failures: list[str] = []

    for case in GOLD_CASES:
        term = NORMALIZERS[case.field](case.raw)
        label_ok = term.label == case.expected_label
        id_ok = (case.expected_ontology_id == "" and term.ontology_id == "") or (
            term.ontology_id == case.expected_ontology_id
        )
        if label_ok and id_ok:
            correct += 1
        else:
            failures.append(
                f"{case.field}({case.raw!r}): got {term.label!r}/{term.ontology_id!r}, "
                f"expected {case.expected_label!r}/{case.expected_ontology_id!r}"
            )

    precision = correct / total if total else 0.0
    print(f"Ontology benchmark: {correct}/{total} correct ({precision:.1%})")
    for line in failures:
        print(f"  FAIL {line}")

    target = 0.90
    if precision < target:
        print(f"Below target precision {target:.0%} — expand GOLD_CASES and lookup tables.")
        return 1
    print(f"Meets target precision {target:.0%}.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
