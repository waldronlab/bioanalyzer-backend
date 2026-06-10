"""Taxonomic rank normalization aligned with BugSigDB curation vocabulary."""

from __future__ import annotations

import re

from app.normalization.types import NormalizedTerm

BUGSIGDB_TAXA_VOCAB = [
    "kingdom",
    "phylum",
    "class",
    "order",
    "family",
    "genus",
    "species",
    "strain",
    "OTU",
    "ASV",
    "operational taxonomic unit",
    "amplicon sequence variant",
]

TAXA_LEVEL_LOOKUP = {
    "operational taxonomic unit": "OTU",
    "operational taxonomic units": "OTU",
    "otu": "OTU",
    "otus": "OTU",
    "amplicon sequence variant": "ASV",
    "amplicon sequence variants": "ASV",
    "asv": "ASV",
    "asvs": "ASV",
    "kingdom": "kingdom",
    "phylum": "phylum",
    "phyla": "phylum",
    "class": "class",
    "order": "order",
    "family": "family",
    "families": "family",
    "genus": "genus",
    "genera": "genus",
    "species": "species",
    "strain": "strain",
    "subspecies": "species",
    "16s v": "genus",
    "v3-v4": "genus",
    "v4 region": "genus",
}


def _best_match(lowered: str) -> tuple[str, int] | None:
    matched = None
    matched_len = 0
    for key, value in TAXA_LEVEL_LOOKUP.items():
        if key in lowered and len(key) > matched_len:
            matched = value
            matched_len = len(key)
    if matched is None:
        return None
    return matched, matched_len


def _found_vocab_types(lowered: str) -> set[str]:
    return {value for key, value in TAXA_LEVEL_LOOKUP.items() if key in lowered}


def normalize_taxa_level(raw_text: str) -> NormalizedTerm:
    """Return normalized taxonomic rank (text vocab only, no ontology ID)."""
    if not raw_text or not str(raw_text).strip():
        return NormalizedTerm.absent()

    lowered = str(raw_text).lower()
    hit = _best_match(lowered)
    if not hit:
        stripped = str(raw_text).strip()
        if stripped in BUGSIGDB_TAXA_VOCAB:
            return NormalizedTerm(stripped, "", "PRESENT", 1.0)
        if re.search(r"\b(rank|taxonomic level|taxa level)\b", lowered):
            return NormalizedTerm(stripped, "", "PARTIALLY_PRESENT", 0.5)
        return NormalizedTerm(stripped, "", "PARTIALLY_PRESENT", 0.5)

    matched, _ = hit
    found_types = _found_vocab_types(lowered)
    if len(found_types) <= 1:
        return NormalizedTerm(matched, "", "PRESENT", 1.0)

    # Multiple distinct ranks mentioned (e.g. genus and species)
    return NormalizedTerm(matched, "", "PARTIALLY_PRESENT", 0.85)
