"""Body site normalization aligned with UBERON labels and IDs."""

from __future__ import annotations

from typing import Dict, Optional, Tuple

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

# The subset of BODY_SITE_LOOKUP's keys eligible for
# `_resolve_structure_override()` below: a generic anatomical word that a
# real, more specific compound phrase can and should override - either a
# *casual specimen alias* standing in for the specimen most commonly
# collected from/near it in loose paper text ("gut microbiome" -> feces,
# "oral microbiome" -> saliva; "oral", "mouth", "dental", "intestine",
# "intestinal", "gut"), or a generic structure that a more specific real
# sibling structure/specimen shares a substring with ("nasal" -> "nasal
# cavity", overridden by "Middle nasal meatus"/"Nasal mucus" - both real,
# different UBERON terms). Every key here was individually confirmed
# (against BugSigDB's real dump and/or the local UBERON store) to have at
# least one real phrasing that was silently mismatched before this
# override existed. "sputum" is deliberately excluded even though it's
# also a generic-word-to-specimen-adjacent mapping: it maps to "lung" (a
# structure, not a specimen), and no confirmed bug involves it.
_OVERRIDABLE_GENERIC_KEYS = frozenset(
    {"oral", "mouth", "dental", "intestine", "intestinal", "gut", "nasal"}
)

# Confidence floor for `_resolve_structure_override()`'s local_lookup()
# check - calibrated against real cases found in the 2026-08-09 semantic-
# hardening pass's evaluation, not guessed: "mouth"/"dental plaque"/
# "intestinal mucosa"/"intestine" all resolve at exactly 0.9 (local_lookup's
# hard confidence cap - see its module docstring), the highest confidence
# that function can ever report; "gut" alone resolves far weaker (0.558,
# two competing candidates - "digestive tract" is too coarse a guess to
# prefer over the existing "feces" casual-alias default). Requiring the cap
# itself (not some lower threshold) means only a genuinely unambiguous-or-
# cleanly-ranked local match can override a casual alias.
_OVERRIDE_CONFIDENCE_FLOOR = 0.9


def _resolve_structure_override(raw_text: str) -> Optional[NormalizedTerm]:
    """When an overridable generic key (see `_OVERRIDABLE_GENERIC_KEYS`)
    is the *only* static-dict match, check whether the full raw text is
    actually naming a more specific real UBERON structure that the generic
    alias key steamrolled - e.g. "Dental plaque" contains "dental" (->
    saliva) but is itself a real, different UBERON term
    (`UBERON:0016482`), not a kind of saliva.

    Deliberately keyed off `local_lookup()` against the *complete* local
    UBERON store (thousands of real terms/synonyms) rather than hand-adding
    a dict key for every phrasing this might come up in - see
    docs/GROUNDING_ARCHITECTURE.md's 2026-08-09 semantic-hardening section
    for why "add more dictionary exceptions" was explicitly rejected as the
    general fix here (it only ever covers the specific phrasings someone
    happened to test).

    Returns the override term only when local_lookup's match is at its
    confidence ceiling (see `_OVERRIDE_CONFIDENCE_FLOOR`) - a weak/uncertain
    local match never overrides the existing, already-reasonable casual-
    alias default. Returns None (keep the casual alias) otherwise,
    including when local_lookup itself is ambiguous between two real
    structures (e.g. "mouth" vs "oral opening") - that ambiguity still
    surfaces to the caller as the overriding term's own `candidates`, which
    is strictly more informative than a confident-but-wrong specimen
    answer, just not a case this function needs special-case logic for.

    Deliberately does NOT reject an override whose target is itself in
    UBERON's "organism substance" branch (a real check - is_a-only
    ancestry against UBERON:0000463 - that was built and tried here during
    the 2026-08-09 semantic-hardening pass, then removed once it was
    checked against real data): "Dental plaque" (UBERON:0016482) is itself
    a real is_a descendant of "organism
    substance" in UBERON's actual graph, exactly like "saliva" is - but
    real BugSigDB ground truth curates "Dental plaque"/"Subgingival dental
    plaque"/"Supragingival dental plaque" as their own distinct, correct,
    common body-site values (322 combined real occurrences), not as
    "saliva". A structure-vs-specimen filter would have blocked this exact
    fix. The real signal that matters here isn't which side of that
    ontological line the answer falls on - it's whether the *fuller, more
    specific* text resolves to a *different, well-evidenced* real term than
    the generic alias word alone does, which the confidence floor above
    already establishes on its own."""
    local_hit = local_lookup(normalize_spelling(raw_text.strip()), ("uberon",))
    if local_hit is None or not local_hit.ontology_id:
        return None
    if local_hit.mapping_confidence < _OVERRIDE_CONFIDENCE_FLOOR:
        return None
    return local_hit


def normalize_body_site(raw_text: str) -> NormalizedTerm:
    """Return normalized body site label, UBERON ID, status, and mapping confidence."""
    if not raw_text or raw_text.strip() == "":
        return NormalizedTerm.absent()

    lowered = normalize_spelling(raw_text.lower())
    matched = _MATCHER.match_all(lowered)

    if len(matched) == 1:
        key, (label, uberon_id) = matched[0]
        if key in _OVERRIDABLE_GENERIC_KEYS:
            override = _resolve_structure_override(raw_text)
            if override is not None:
                return override
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
