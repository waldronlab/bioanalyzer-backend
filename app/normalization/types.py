"""Shared types and lookup-matching helpers for ontology-aligned field
normalization."""

from __future__ import annotations

import re
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

    Shared by sequencing_type.py and the other field normalizers, which each
    have their own controlled-vocabulary lookup dict but need identical
    matching logic.
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


# British -> American spelling variants that show up in scientific papers and
# would otherwise miss both our static lookup dicts and live OLS/MONDO
# queries (e.g. a paper saying "faecal" scores as a mismatch against our
# "feces" entries even though it's the same site) - ported from
# MetaHarmonizer's _BRITISH_TO_AMERICAN list after a benchmark against
# BugSigDB's real curated corpus found this exact gap (see
# docs/METACURATOR_METAHARMONIZER_ANALYSIS.md). Applied before matching, not
# as a lookup-dict key, so it benefits the normalizers that call it today
# (body_site.py, condition.py — and their live search fallback) without
# duplicating entries.
_BRITISH_TO_AMERICAN = (
    (re.compile(r"faeces", re.IGNORECASE), "feces"),
    (re.compile(r"faecal", re.IGNORECASE), "fecal"),
    (re.compile(r"oesophag", re.IGNORECASE), "esophag"),
    (re.compile(r"leukaemia", re.IGNORECASE), "leukemia"),
    (re.compile(r"tumour", re.IGNORECASE), "tumor"),
    (re.compile(r"haemato", re.IGNORECASE), "hemato"),
    (re.compile(r"haemoglobin", re.IGNORECASE), "hemoglobin"),
    (re.compile(r"haemorrhag", re.IGNORECASE), "hemorrhag"),
    (re.compile(r"anaemia", re.IGNORECASE), "anemia"),
    (re.compile(r"oedema", re.IGNORECASE), "edema"),
    (re.compile(r"paediatric", re.IGNORECASE), "pediatric"),
    (re.compile(r"foetal", re.IGNORECASE), "fetal"),
    (re.compile(r"foetus", re.IGNORECASE), "fetus"),
    (re.compile(r"gynaecolog", re.IGNORECASE), "gynecolog"),
    (re.compile(r"diarrhoea", re.IGNORECASE), "diarrhea"),
    (re.compile(r"colour", re.IGNORECASE), "color"),
)


def normalize_spelling(text: str) -> str:
    """Rewrite British spelling variants to American, case-insensitively.

    Called by body_site.py and condition.py before dict/keyword matching and
    before building a live OLS/MONDO search query, so a British-spelled term
    in the source paper matches the same lookup entries and search results an
    American-spelled one would. Not currently called by host_species.py or
    sequencing_type.py.
    """
    for pattern, replacement in _BRITISH_TO_AMERICAN:
        text = pattern.sub(replacement, text)
    return text
