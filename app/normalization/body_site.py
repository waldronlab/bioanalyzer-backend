"""Body site normalization aligned with UBERON labels and IDs."""

from __future__ import annotations

from typing import Dict, Tuple

from app.normalization.ols import ols_search
from app.normalization.types import NormalizedTerm

# keyword -> (canonical label, UBERON ID)
#
# Exhaustively checked against the live EBI OLS API on 2026-07-12 as part of
# a wider ontology-mapping audit (see docs/PROJECT_AUDIT.md / ONTOLOGY_AUDIT.md).
# Two entries were wrong and corrected: "rectum" pointed at a non-existent ID
# (UBERON:0000096, now UBERON:0001052), and "vagina" pointed at ovary
# (UBERON:0000992, now UBERON:0000996, the actual vagina term). Every other
# entry in this dict resolves to the label claimed here.
BODY_SITE_LOOKUP: Dict[str, Tuple[str, str]] = {
    "feces": ("feces", "UBERON:0001988"),
    "fecal": ("feces", "UBERON:0001988"),
    "stool": ("feces", "UBERON:0001988"),
    "gut": ("feces", "UBERON:0001988"),
    "intestine": ("feces", "UBERON:0001988"),
    "intestinal": ("feces", "UBERON:0001988"),
    "colon": ("colon", "UBERON:0001155"),
    "colonic": ("colon", "UBERON:0001155"),
    "rectal": ("rectum", "UBERON:0001052"),
    "rectum": ("rectum", "UBERON:0001052"),
    "saliva": ("saliva", "UBERON:0001836"),
    "salivary": ("saliva", "UBERON:0001836"),
    "oral": ("saliva", "UBERON:0001836"),
    "mouth": ("saliva", "UBERON:0001836"),
    "dental": ("saliva", "UBERON:0001836"),
    "tongue": ("tongue", "UBERON:0001723"),
    "buccal": ("cheek", "UBERON:0001567"),
    "vagina": ("vagina", "UBERON:0000996"),
    "vaginal": ("vagina", "UBERON:0000996"),
    "cervical": ("uterine cervix", "UBERON:0000002"),
    "uterine": ("uterus", "UBERON:0000995"),
    "skin": ("skin", "UBERON:0002097"),
    "cutaneous": ("skin", "UBERON:0002097"),
    "dermal": ("skin", "UBERON:0002097"),
    "lung": ("lung", "UBERON:0002048"),
    "pulmonary": ("lung", "UBERON:0002048"),
    "bronchial": ("bronchus", "UBERON:0002185"),
    "nasal": ("nasal cavity", "UBERON:0001707"),
    "nasopharyngeal": ("nasopharynx", "UBERON:0001728"),
    "sputum": ("lung", "UBERON:0002048"),
    "blood": ("blood", "UBERON:0000178"),
    "serum": ("blood", "UBERON:0000178"),
    "plasma": ("blood", "UBERON:0000178"),
    "urine": ("urine", "UBERON:0001088"),
    "urinary": ("urinary bladder", "UBERON:0001255"),
    "bladder": ("urinary bladder", "UBERON:0001255"),
}


def normalize_body_site(raw_text: str) -> NormalizedTerm:
    """Return normalized body site label, UBERON ID, status, and mapping confidence."""
    if not raw_text or raw_text.strip() == "":
        return NormalizedTerm.absent()

    lowered = raw_text.lower()
    matched: list[Tuple[str, str]] = []
    for key, pair in BODY_SITE_LOOKUP.items():
        if key in lowered and pair not in matched:
            matched.append(pair)

    if len(matched) == 1:
        label, uberon_id = matched[0]
        return NormalizedTerm(label, uberon_id, "PRESENT", 1.0)
    if len(matched) > 1:
        label, uberon_id = matched[0]
        return NormalizedTerm(
            label, uberon_id, "PARTIALLY_PRESENT", 0.9, candidates=tuple(matched[1:3])
        )

    hit = ols_search(raw_text.strip(), "uberon", "UBERON", mapping_confidence=0.9)
    if hit:
        label, uberon_id, conf = hit
        return NormalizedTerm(label, uberon_id, "PRESENT", conf)

    stripped = raw_text.strip()
    return NormalizedTerm(stripped, "", "PARTIALLY_PRESENT", 0.5)
