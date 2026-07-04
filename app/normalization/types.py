"""Shared types and lookup-matching helpers for ontology-aligned field
normalization."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, Tuple


@dataclass(frozen=True)
class NormalizedTerm:
    """Label, ontology ID, extraction status, and mapping confidence."""

    label: str
    ontology_id: str
    status: str
    mapping_confidence: float
    raw: str = ""
    # Up to 2 runner-up (label, ontology_id) pairs from the same lookup dict,
    # surfaced so curators can pick an alternative when the mapping tier isn't
    # "auto" (see app.normalization.grounding). Empty for API-resolved terms,
    # which only ever produce a single candidate.
    candidates: Tuple[Tuple[str, str], ...] = field(default_factory=tuple)

    @classmethod
    def absent(cls) -> NormalizedTerm:
        return cls(label="", ontology_id="", status="ABSENT", mapping_confidence=0.0)


def best_lookup_match(lowered: str, lookup: Dict[str, str]) -> tuple[str, int] | None:
    """
    Find the longest lookup key that's a substring of `lowered`, returning
    its mapped value and the matched key's length (used to break ties
    between overlapping keys, e.g. "16s" vs "16s rrna").

    Shared by sequencing_type.py and taxa_level.py, which each have their
    own controlled-vocabulary lookup dict but need identical matching logic.
    """
    matched = None
    matched_len = 0
    for key, value in lookup.items():
        if key in lowered and len(key) > matched_len:
            matched = value
            matched_len = len(key)
    if matched is None:
        return None
    return matched, matched_len


def found_vocab_types(lowered: str, lookup: Dict[str, str]) -> set[str]:
    """Return the set of distinct vocab values whose lookup key appears in `lowered`."""
    return {value for key, value in lookup.items() if key in lowered}
