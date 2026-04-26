"""Sequencing type normalization aligned with BugSigDB vocabulary."""

from __future__ import annotations

from typing import Tuple

BUGSIGDB_SEQ_VOCAB = ["16S", "shotgun", "WGS", "ITS", "amplicon", "RNA-seq", "other"]

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
    "metagenomics": "shotgun",
    "metagenomic": "shotgun",
}


def normalize_sequencing_type(raw_text: str) -> Tuple[str, str]:
    """Return normalized sequencing type and extraction status."""
    if not raw_text or raw_text.strip() == "":
        return "", "ABSENT"

    lowered = raw_text.lower()
    matched = None
    matched_len = 0
    for key, value in SEQUENCING_LOOKUP.items():
        if key in lowered and len(key) > matched_len:
            matched = value
            matched_len = len(key)

    if matched:
        found_types = {value for key, value in SEQUENCING_LOOKUP.items() if key in lowered}
        if len(found_types) > 1:
            return matched, "PARTIALLY_PRESENT"
        return matched, "PRESENT"

    return raw_text.strip(), "PARTIALLY_PRESENT"

