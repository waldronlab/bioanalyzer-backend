"""Sequencing type normalization to BugSigDB's own controlled vocabulary.

BugSigDB's "Sequencing type" is a single-select dropdown with exactly the
five values in BUGSIGDB_SEQ_VOCAB (bugsigdb.org's `Property:Sequencing type`;
the same list as seandavi/bugsigdb-curation-tools' `SEQUENCING_TYPE_VALUES`,
and the only values in BugSigDB's `full_dump.csv` besides "NA"). This module
emits those exact strings rather than a vocabulary of its own, so a
prediction can be compared with - or imported into - BugSigDB without a
translation step. An earlier, BioAnalyzer-only vocabulary ("shotgun",
"metagenomics", "amplicon", "other", ...) had no "WMS" at all and mapped
18S to ITS, which alone accounted for 20 of the 30 Sequencing Type defects
in the 2026-08 99-PMID ground-truth benchmark.

BugSigDB records one method per Experiment, but BioAnalyzer works per paper,
so a paper that used several methods (e.g. 16S for some experiments, WMS for
others) gets all of them, joined with MULTI_VALUE_SEPARATOR in vocabulary
order.

A stated method with no BugSigDB value (RNA-seq, DGGE, culture, ...) leaves
the label blank rather than inventing one; the paper's own wording is kept
on `.raw`, which the API's FieldDict exposes as `raw`.
"""

from __future__ import annotations

import re
from typing import Dict, List, Tuple

from app.normalization.types import NormalizedTerm, is_null_like

BUGSIGDB_SEQ_VOCAB = ["16S", "18S", "WMS", "ITS / ITS2", "PCR"]

MULTI_VALUE_SEPARATOR = "; "

# mapping_confidence levels. Anything below _CONFIDENT is a best guess that
# comes back PARTIALLY_PRESENT, so a curator confirms it.
_CONFIDENT = 1.0
_GUESS = 0.7
_UNMAPPED = 0.5

_MARKER_GENES = frozenset({"16S", "18S", "ITS / ITS2"})

# Whole-word matching throughout: the previous plain-substring lookup matched
# "its" inside "results"/"limits" (and the pronoun), reporting ITS for papers
# that never used it.
_METHOD_PATTERNS: List[Tuple[re.Pattern[str], str]] = [
    (re.compile(r"\b16\s?S\b", re.IGNORECASE), "16S"),
    # A named 16S hypervariable region means 16S even when "16S" isn't
    # written. A bare "v3" is not enough - "MiSeq Reagent Kit v3" is common.
    (re.compile(r"\bv[1-9]\s*(?:[-–/]|to)\s*v?[1-9]\b", re.IGNORECASE), "16S"),
    (re.compile(r"\bv[1-9]\s+(?:hyper)?variable\s+region", re.IGNORECASE), "16S"),
    (re.compile(r"\bv[1-9]\s+region", re.IGNORECASE), "16S"),
    (re.compile(r"\b18\s?S\b", re.IGNORECASE), "18S"),
    # Upper-case only: lower-case "its" is almost always the pronoun.
    (re.compile(r"\bITS\s?[12]?\b"), "ITS / ITS2"),
    (re.compile(r"\bits\s?[12]\b", re.IGNORECASE), "ITS / ITS2"),
    (re.compile(r"\binternal transcribed spacer", re.IGNORECASE), "ITS / ITS2"),
    (re.compile(r"\bshotgun\b", re.IGNORECASE), "WMS"),
    (re.compile(r"\bwhole[\s-]metagenom", re.IGNORECASE), "WMS"),
    (re.compile(r"\bwms\b", re.IGNORECASE), "WMS"),
]

# "Metagenomics" is also used loosely for 16S surveys ("16S rRNA
# metagenomics"), so it only means WMS when no marker gene is named.
_LOOSE_METAGENOMIC = re.compile(r"\bmetagenom(?:e|es|ic|ics)\b", re.IGNORECASE)

# In microbiome papers "WGS" almost always means shotgun metagenomics, but it
# can also mean isolate genome sequencing, which BugSigDB has no value for.
_WHOLE_GENOME = re.compile(r"\bwgs\b|\bwhole[\s-]genome\s+sequenc", re.IGNORECASE)

# Amplicon sequencing with no gene named: 98.8% of BugSigDB's amplicon
# experiments are 16S (11,445 of 16S + 18S + ITS / ITS2 = 11,578).
_GENERIC_AMPLICON = re.compile(
    r"\bamplicon|\bmarker[\s-]genes?\b|\brrna\b|\bribosomal\s+rna\b",
    re.IGNORECASE,
)

# BugSigDB's "PCR" is targeted qPCR/PCR of specific taxa. Nearly every
# amplicon paper also mentions "PCR amplification", so a plain PCR mention
# only counts when no other method is found.
_PCR = re.compile(r"pcr\b", re.IGNORECASE)
_TARGETED_PCR = re.compile(
    r"\b(?:q|dd)pcr\b|\bqrt-pcr\b|\breal[\s-]time\b|\bquantitative\b",
    re.IGNORECASE,
)
_SEQUENCING = re.compile(
    r"sequenc|\bshotgun\b|\bmetagenom|\bamplicon|\billumina\b"
    r"|\b(?:mi|hi|next|nova)seq\b|\bion torrent\b|\bnanopore\b|\bpacbio\b",
    re.IGNORECASE,
)


def _find_methods(text: str) -> Dict[str, float]:
    """BugSigDB value -> mapping confidence, for every method named in `text`."""
    sequencing_named = bool(_SEQUENCING.search(text))
    if _PCR.search(text) and _TARGETED_PCR.search(text) and not sequencing_named:
        # qPCR with 16S/ITS primers is still BugSigDB's "PCR": the marker
        # gene names the primer target, not a sequencing method.
        return {"PCR": _CONFIDENT}

    found: Dict[str, float] = {}
    for pattern, value in _METHOD_PATTERNS:
        if pattern.search(text):
            found[value] = _CONFIDENT

    marker_gene_named = bool(found.keys() & _MARKER_GENES)
    if "WMS" not in found:
        if _LOOSE_METAGENOMIC.search(text) and not marker_gene_named:
            found["WMS"] = _CONFIDENT
        elif _WHOLE_GENOME.search(text):
            found["WMS"] = _GUESS
    if not marker_gene_named and _GENERIC_AMPLICON.search(text):
        found["16S"] = _GUESS

    if not found and _PCR.search(text):
        # A plain "PCR" mention, or PCR alongside unspecified sequencing.
        found["PCR"] = _GUESS
    return found


def normalize_sequencing_type(raw_text: str) -> NormalizedTerm:
    """Map a free-text method description to BugSigDB's vocabulary.

    PRESENT when every method found maps confidently; PARTIALLY_PRESENT
    when any of them is a best guess, or when a method is stated but has no
    BugSigDB value (blank label, wording kept on `.raw`). No ontology ID -
    this is a text vocabulary only.
    """
    if not raw_text or is_null_like(raw_text):
        return NormalizedTerm.absent()

    stripped = raw_text.strip()
    found = _find_methods(stripped)
    if not found:
        return NormalizedTerm("", "", "PARTIALLY_PRESENT", _UNMAPPED, raw=stripped)

    label = MULTI_VALUE_SEPARATOR.join(v for v in BUGSIGDB_SEQ_VOCAB if v in found)
    confidence = min(found.values())
    status = "PRESENT" if confidence == _CONFIDENT else "PARTIALLY_PRESENT"
    return NormalizedTerm(label, "", status, confidence, raw=stripped)
