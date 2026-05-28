"""Sequencing type normalization aligned with BugSigDB controlled vocabulary."""

from __future__ import annotations

from app.normalization.types import NormalizedTerm

BUGSIGDB_SEQ_VOCAB = [
    "16S",
    "shotgun",
    "WGS",
    "metagenomics",
    "ITS",
    "amplicon",
    "RNA-seq",
    "other",
]

SEQUENCING_LOOKUP = {
    "16s rrna": "16S",
    "16s ribosomal": "16S",
    "16s amplicon": "16S",
    "v3-v4": "16S",
    "v4 region": "16S",
    "16s": "16S",
    "its1": "ITS",
    "its2": "ITS",
    "internal transcribed spacer": "ITS",
    "18s": "ITS",
    "its": "ITS",
    "whole metagenome": "shotgun",
    "whole-metagenome": "shotgun",
    "metagenomic shotgun": "shotgun",
    "shotgun sequencing": "shotgun",
    "shotgun": "shotgun",
    "whole genome sequencing": "WGS",
    "whole-genome sequencing": "WGS",
    "wgs": "WGS",
    "metatranscriptomics": "RNA-seq",
    "metatranscriptomic": "RNA-seq",
    "transcriptomic": "RNA-seq",
    "rnaseq": "RNA-seq",
    "rna-seq": "RNA-seq",
    "amplicon sequencing": "amplicon",
    "next-generation sequencing": "amplicon",
    "ngs": "amplicon",
    "amplicon": "amplicon",
    "metagenomics": "metagenomics",
    "metagenomic": "metagenomics",
}

# Methods in the same family (e.g. shotgun + metagenomics) are not ambiguous.
COMPATIBLE_GROUPS = [
    {"16S"},
    {"shotgun", "metagenomics", "WGS"},
    {"ITS"},
    {"amplicon"},
    {"RNA-seq"},
]


def _found_vocab_types(lowered: str) -> set[str]:
    return {value for key, value in SEQUENCING_LOOKUP.items() if key in lowered}


def _best_match(lowered: str) -> tuple[str, int] | None:
    matched = None
    matched_len = 0
    for key, value in SEQUENCING_LOOKUP.items():
        if key in lowered and len(key) > matched_len:
            matched = value
            matched_len = len(key)
    if matched is None:
        return None
    return matched, matched_len


def normalize_sequencing_type(raw_text: str) -> NormalizedTerm:
    """Return normalized sequencing type (text vocab only, no ontology ID)."""
    if not raw_text or raw_text.strip() == "":
        return NormalizedTerm.absent()

    lowered = raw_text.lower()
    hit = _best_match(lowered)
    if not hit:
        stripped = raw_text.strip()
        if stripped in BUGSIGDB_SEQ_VOCAB:
            return NormalizedTerm(stripped, "", "PRESENT", 1.0)
        return NormalizedTerm(stripped, "", "PARTIALLY_PRESENT", 0.5)

    matched, _ = hit
    found_types = _found_vocab_types(lowered)
    if len(found_types) <= 1:
        return NormalizedTerm(matched, "", "PRESENT", 1.0)

    groups_hit = [g for g in COMPATIBLE_GROUPS if found_types & g]
    if len(groups_hit) == 1 and found_types <= groups_hit[0]:
        return NormalizedTerm(matched, "", "PRESENT", 1.0)

    return NormalizedTerm(matched, "", "PARTIALLY_PRESENT", 0.9)
