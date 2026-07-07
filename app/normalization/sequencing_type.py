"""Sequencing type normalization aligned with BugSigDB controlled vocabulary."""

from __future__ import annotations

from app.normalization.types import NormalizedTerm, best_lookup_match, found_vocab_types

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


def normalize_sequencing_type(raw_text: str) -> NormalizedTerm:
    """Return normalized sequencing type (text vocab only, no ontology ID).

    A value that doesn't match any known phrasing still resolves to a
    vocabulary member ("other") rather than leaking free text into the
    "Sequencing Type" column — the original wording is preserved on
    `.raw` for callers that want it (not currently exported as its own
    curator-desk CSV column, but still available in the API's FieldDict).
    PARTIALLY_PRESENT is reserved for genuinely ambiguous multi-method
    mentions, not the "other" catch-all.
    """
    if not raw_text or raw_text.strip() == "":
        return NormalizedTerm.absent()

    stripped = raw_text.strip()
    lowered = raw_text.lower()
    hit = best_lookup_match(lowered, SEQUENCING_LOOKUP)
    if not hit:
        if stripped in BUGSIGDB_SEQ_VOCAB:
            return NormalizedTerm(stripped, "", "PRESENT", 1.0, raw=stripped)
        return NormalizedTerm("other", "", "PRESENT", 0.5, raw=stripped)

    matched, _ = hit
    found_types = found_vocab_types(lowered, SEQUENCING_LOOKUP)
    if len(found_types) <= 1:
        return NormalizedTerm(matched, "", "PRESENT", 1.0, raw=stripped)

    groups_hit = [g for g in COMPATIBLE_GROUPS if found_types & g]
    if len(groups_hit) == 1 and found_types <= groups_hit[0]:
        return NormalizedTerm(matched, "", "PRESENT", 1.0, raw=stripped)

    return NormalizedTerm(matched, "", "PARTIALLY_PRESENT", 0.9, raw=stripped)
