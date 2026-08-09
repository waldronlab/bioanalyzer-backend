"""Body site normalization aligned with UBERON labels and IDs."""

from __future__ import annotations

from typing import Dict, Tuple

from app.normalization.local_lookup import local_lookup
from app.normalization.ols import ols_search
from app.normalization.types import LookupMatcher, NormalizedTerm, normalize_spelling

# keyword -> (canonical label, UBERON ID)
#
# Exhaustively checked against the live EBI OLS API on 2026-07-12 as part of
# a wider ontology-mapping audit (see docs/PROJECT_AUDIT.md / ONTOLOGY_AUDIT.md).
# Two entries were wrong and corrected: "rectum" pointed at a non-existent ID
# (UBERON:0000096, now UBERON:0001052), and "vagina" pointed at ovary
# (UBERON:0000992, now UBERON:0000996, the actual vagina term). Every other
# entry in this dict resolves to the label claimed here.
BODY_SITE_LOOKUP: Dict[str, Tuple[str, str]] = {
    # "small intestine"/"large intestine"/"oral cavity" are listed *before*
    # the generic "intestine"/"oral" family below deliberately -
    # LookupMatcher.match_all() (used by normalize_body_site() below) takes
    # whichever matching key it encounters *first* in dict-iteration order
    # as the primary/displayed answer when more than one distinct value
    # matches, so ordering the more specific, more precisely-verified real
    # UBERON term first means a curator sees the *correct* interpretation
    # at "review" tier, not the wrong specimen-type guess. See the
    # 2026-08 note below "dental" for the full story (real, independent
    # BugSigDB evaluation found this exact false-AUTO defect).
    "small intestine": ("small intestine", "UBERON:0002108"),
    "large intestine": ("large intestine", "UBERON:0000059"),
    "oral cavity": ("oral cavity", "UBERON:0000167"),
    "feces": ("feces", "UBERON:0001988"),
    "fecal": ("feces", "UBERON:0001988"),
    "stool": ("feces", "UBERON:0001988"),
    "gut": ("feces", "UBERON:0001988"),
    "intestine": ("feces", "UBERON:0001988"),
    "intestinal": ("feces", "UBERON:0001988"),
    # "intestine"/"intestinal" above are deliberately kept as specimen-type
    # aliases for "feces" (loose/casual paper text like "gut microbiome" or
    # "intestinal samples" overwhelmingly means a fecal sample, since that's
    # how gut microbiome is non-invasively collected) - but a 2026-08
    # independent evaluation against BugSigDB's own precise anatomical
    # curation (see docs/GROUNDING_ARCHITECTURE.md) found this conflates the
    # SPECIMEN with the ANATOMICAL SITE when the input is itself already a
    # precise site name, not casual text: "Small intestine"/"Large
    # intestine" both confidently matched "intestine" -> feces at "auto"
    # tier, which is wrong (confirmed: neither is a real UBERON ancestor/
    # descendant of "feces"). Fixed by adding the specific site names above
    # as their own keys (real, verified UBERON labels) - this doesn't
    # change or remove the original "intestine"/"intestinal" entries (the
    # casual-text case still works), it makes body_site.py's existing
    # ambiguity machinery (LookupMatcher.match_all() -> more than one
    # distinct value matched -> "review", not "auto") correctly catch the
    # conflict instead of silently picking the wrong one, for the specific
    # phrasings real curated data showed this actually happening for.
    "colon": ("colon", "UBERON:0001155"),
    "colonic": ("colon", "UBERON:0001155"),
    "rectal": ("rectum", "UBERON:0001052"),
    "rectum": ("rectum", "UBERON:0001052"),
    "saliva": ("saliva", "UBERON:0001836"),
    "salivary": ("saliva", "UBERON:0001836"),
    "oral": ("saliva", "UBERON:0001836"),
    "mouth": ("saliva", "UBERON:0001836"),
    "dental": ("saliva", "UBERON:0001836"),
    # Same reasoning and fix as "intestine" above: "oral"/"mouth"/"dental"
    # stay as specimen-type aliases for "saliva" (casual text like "oral
    # samples"/"oral microbiome" usually means saliva), but "Oral cavity" as
    # a precise site name is a real, different UBERON concept (confirmed:
    # not a real ancestor/descendant of "saliva") that was silently
    # mismatched to saliva at "auto" tier against real BugSigDB curation.
    "oral cavity": ("oral cavity", "UBERON:0000167"),
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


_MATCHER = LookupMatcher(BODY_SITE_LOOKUP)


def normalize_body_site(raw_text: str) -> NormalizedTerm:
    """Return normalized body site label, UBERON ID, status, and mapping confidence."""
    if not raw_text or raw_text.strip() == "":
        return NormalizedTerm.absent()

    lowered = normalize_spelling(raw_text.lower())
    matched = _MATCHER.match_all(lowered)

    if len(matched) == 1:
        _key, (label, uberon_id) = matched[0]
        return NormalizedTerm(label, uberon_id, "PRESENT", 1.0)
    if len(matched) > 1:
        winning_key, (label, uberon_id) = matched[0]
        candidates = _MATCHER.candidates(lowered, winning_key, (label, uberon_id))
        return NormalizedTerm(
            label, uberon_id, "PARTIALLY_PRESENT", 0.9, candidates=candidates
        )

    # Nothing in the static dict matched. Before any network call: try the
    # local ontology store - real, complete UBERON data (2026-08
    # adversarial review found this had no production caller at all; see
    # app.normalization.local_lookup's module docstring). Offline,
    # sub-millisecond, and covers real UBERON terms/synonyms far beyond
    # this module's ~36-entry static dict.
    local_hit = local_lookup(normalize_spelling(raw_text.strip()), ("uberon",))
    if local_hit:
        return local_hit

    hit = ols_search(
        normalize_spelling(raw_text.strip()), "uberon", "UBERON", mapping_confidence=0.9
    )
    if hit:
        label, uberon_id, conf = hit
        return NormalizedTerm(label, uberon_id, "PRESENT", conf)

    stripped = raw_text.strip()
    return NormalizedTerm(stripped, "", "PARTIALLY_PRESENT", 0.5)
