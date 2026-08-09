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

# Confidence floor for `_resolve_structure_override()`'s local_lookup()
# check - calibrated against real cases, not guessed: every genuine fix
# this mechanism was built for ("Dental plaque", "Intestinal mucosa",
# "Ascending colon", "Left lung", "Skin of forehead", "Middle nasal
# meatus", ...) resolves at exactly 0.9, local_lookup's hard confidence
# ceiling (see its module docstring - "never auto"); every case checked
# where overriding would have been wrong or unhelpful resolves measurably
# below it ("gut" alone: 0.558, two competing candidates - "digestive
# tract" is too coarse a guess to prefer over "feces"; "skin" alone: 0.85,
# resolves to the unhelpfully generic "zone of skin" rather than a real
# specific region). Requiring the ceiling itself (not some lower
# threshold) means only a genuinely unambiguous-or-cleanly-ranked local
# match can ever override a static-dict default.
_OVERRIDE_CONFIDENCE_FLOOR = 0.9


def _resolve_structure_override(
    raw_text: str, generic_ontology_id: str
) -> Optional[NormalizedTerm]:
    """When a static-dict key is the *only* match for `raw_text`, check
    whether the full raw text is actually naming a more specific real
    UBERON term that the shorter, more generic key steamrolled - e.g.
    "Ascending colon" contains "colon" (-> generic UBERON:0001155) but is
    itself a real, different, more specific UBERON term
    (`UBERON:0001156`); "Dental plaque" contains "dental" (-> saliva) but
    is itself a real, different UBERON term (`UBERON:0016482`), not a kind
    of saliva.

    Deliberately keyed off `local_lookup()` against the *complete* local
    UBERON store (thousands of real terms/synonyms) rather than hand-adding
    a dict key for every phrasing this might come up in - see
    docs/GROUNDING_ARCHITECTURE.md's 2026-08-09 semantic-hardening section
    for why "add more dictionary exceptions" was explicitly rejected as the
    general fix here (it only ever covers the specific phrasings someone
    happened to test).

    Applied unconditionally to every single static match, not a curated
    subset of "eligible" keys (an earlier version of this function - see
    git history / the semantic-hardening doc section - restricted this to
    a hand-picked `_OVERRIDABLE_GENERIC_KEYS` set; removed once an audit of
    every key in `BODY_SITE_LOOKUP` against the real local store confirmed
    the two guards below are sufficient on their own, and that the
    allowlist was only adding maintenance burden, not safety: every bare
    dict key's own local_lookup result is either the *same* CURIE as the
    dict already returns - guard 1 below makes that a no-op - or below the
    confidence ceiling - guard 2 below makes that a no-op too).

    Two guards, both required, both load-bearing:

    1. **Confidence must be at the local_lookup ceiling** (see
       `_OVERRIDE_CONFIDENCE_FLOOR`'s docstring for the real calibration
       evidence) - a weak/ambiguous/uncertain local match never overrides
       the existing default. This is also what keeps a *generic* input
       ("Colon" alone) from ever being pushed *toward* an over-specific
       guess: `local_lookup("colon")` resolves to the same generic
       `UBERON:0001155` the dict already returns, and even where a local
       match exists for a shorter/looser generic word ("skin" -> "zone of
       skin" at 0.85, "gut" -> "digestive tract" at 0.56) it lands below
       the ceiling and is correctly ignored - "deepest node always wins"
       is never this function's behavior; only "the input text itself
       names a different, exactly-matched real term" is.
    2. **The local match's CURIE must differ from what the static dict
       already returned** (`generic_ontology_id`) - otherwise a plain,
       already-correct exact match (e.g. "Nasal cavity" hitting the
       "nasal" key) would be needlessly re-wrapped through `local_lookup`'s
       confidence cap and downgraded from "auto" (1.0) to "review" (0.9)
       for zero actual information gain. A real bug of exactly this shape,
       found by tracing this function's own behavior against every dict
       key rather than assumed, is what prompted adding this guard.

    Returns None (keep the static dict's answer) whenever either guard
    fails - including when local_lookup itself is ambiguous between two
    real structures (e.g. "mouth" vs "oral opening") but still passes both
    guards; that ambiguity surfaces to the caller as the overriding term's
    own `candidates`, which is strictly more informative than a confident-
    but-wrong or confidently-too-coarse answer, not a case this function
    needs special-case logic for.

    Deliberately does NOT reject an override whose target is itself in
    UBERON's "organism substance" branch (a real check - is_a-only
    ancestry against UBERON:0000463 - that was built and tried here during
    an earlier semantic-hardening pass, then removed once it was checked
    against real data): "Dental plaque" (UBERON:0016482) is itself a real
    is_a descendant of "organism substance" in UBERON's actual graph,
    exactly like "saliva" is - but real BugSigDB ground truth curates
    "Dental plaque"/"Subgingival dental plaque"/"Supragingival dental
    plaque" as their own distinct, correct, common body-site values (322
    combined real occurrences), not as "saliva". A structure-vs-specimen
    filter would have blocked this exact fix. The real signal that matters
    here isn't which side of that ontological line the answer falls on -
    it's whether the *fuller, more specific* text resolves to a
    *different, well-evidenced* real term than the shorter key alone does,
    which the two guards above already establish on their own."""
    local_hit = local_lookup(normalize_spelling(raw_text.strip()), ("uberon",))
    if local_hit is None or not local_hit.ontology_id:
        return None
    if local_hit.mapping_confidence < _OVERRIDE_CONFIDENCE_FLOOR:
        return None
    if local_hit.ontology_id == generic_ontology_id:
        return None
    return local_hit


def normalize_body_site(raw_text: str) -> NormalizedTerm:
    """Return normalized body site label, UBERON ID, status, and mapping confidence."""
    if not raw_text or raw_text.strip() == "":
        return NormalizedTerm.absent()

    lowered = normalize_spelling(raw_text.lower())
    matched = _MATCHER.match_all(lowered)

    if len(matched) == 1:
        _key, (label, uberon_id) = matched[0]
        override = _resolve_structure_override(raw_text, uberon_id)
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
