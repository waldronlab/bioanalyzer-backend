"""Condition normalization aligned with EFO canonical labels and IDs."""

from __future__ import annotations

from typing import Dict, Optional, Tuple

from app.normalization.local_lookup import local_lookup
from app.normalization.ols import ols_search
from app.normalization.types import (
    LookupMatcher,
    NormalizedTerm,
    is_null_like,
    normalize_spelling,
)

# keyword -> (canonical label, ontology ID)
#
# Every ID below was verified against the live EBI OLS API (the same source
# ols_search() below falls back to) on 2026-07-12, after an audit found most
# of a prior version of this dict pointed at wrong or obsolete EFO terms
# (fabricated-looking IDs that didn't survive a live lookup - see
# docs/PROJECT_AUDIT.md). EFO is used where a live EFO term exists; MONDO is
# used where EFO has retired the term in favor of MONDO (OLS reports this as
# the term's replacement). A handful of non-disease comparator-arm/exposure
# concepts ("healthy"/"control"/"normal", "antibiotic") have no clean
# disease-ontology equivalent and are intentionally left with ontology_id=""
# rather than force a fabricated ID - normalize_condition() still returns
# their label, just with mapping_tier="none" (see grounding.py).
CONDITION_LOOKUP: Dict[str, Tuple[str, str]] = {
    "parkinson disease": ("Parkinson disease", "MONDO:0005180"),
    "parkinson's": ("Parkinson disease", "MONDO:0005180"),
    "parkinson": ("Parkinson disease", "MONDO:0005180"),
    "alzheimer disease": ("Alzheimer disease", "MONDO:0004975"),
    "alzheimer's": ("Alzheimer disease", "MONDO:0004975"),
    "alzheimer": ("Alzheimer disease", "MONDO:0004975"),
    "inflammatory bowel": ("inflammatory bowel disease", "MONDO:0005265"),
    "ibd": ("inflammatory bowel disease", "MONDO:0005265"),
    "crohn's": ("Crohn disease", "MONDO:0005011"),
    "crohn": ("Crohn disease", "MONDO:0005011"),
    "ulcerative colitis": ("ulcerative colitis", "MONDO:0005101"),
    "colorectal cancer": ("colorectal cancer", "MONDO:0005575"),
    "colon cancer": ("colorectal cancer", "MONDO:0005575"),
    "obesity": ("obesity disorder", "MONDO:0011122"),
    "obese": ("obesity disorder", "MONDO:0011122"),
    "overweight": ("obesity disorder", "MONDO:0011122"),
    "type 2 diabetes": ("type 2 diabetes mellitus", "MONDO:0005148"),
    "t2d": ("type 2 diabetes mellitus", "MONDO:0005148"),
    "type 1 diabetes": ("type 1 diabetes mellitus", "MONDO:0005147"),
    "t1d": ("type 1 diabetes mellitus", "MONDO:0005147"),
    # Real gap found in a 2026-08 independent BugSigDB evaluation: "type 2"/
    # "type 1" above only match the digit spelling, so real curated text
    # using roman numerals ("Type II diabetes mellitus", 5 real occurrences
    # in BugSigDB's dump) missed these keys entirely and fell through to
    # the much shorter, generic "diabetes" key instead, confidently
    # returning the wrong (too-generic) MONDO:0005015 "diabetes mellitus"
    # rather than the correct type-specific term - not dangerous (still a
    # real, non-obsolete, branch-valid MONDO term, so it round-tripped
    # clean and graded "auto"), but a real, avoidable accuracy loss.
    "type ii diabetes": ("type 2 diabetes mellitus", "MONDO:0005148"),
    "type i diabetes": ("type 1 diabetes mellitus", "MONDO:0005147"),
    # Real gap found in the 2026-08-09 semantic-hardening pass: "gestational
    # diabetes"/"gestational diabetes mellitus" fell through the type-1/
    # type-2 keys above (neither is a substring match) straight to the
    # short, generic "diabetes" key, confidently returning the wrong
    # (too-generic) MONDO:0005015 "diabetes mellitus" instead of the real,
    # non-obsolete, branch-valid MONDO:0005406 "gestational diabetes" -
    # verified against the live local MONDO store, not guessed. Listed
    # before "diabetes" so `match_longest()` (this dict's matcher) prefers
    # the longer, more specific key, same precedence the roman-numeral keys
    # above rely on.
    "gestational diabetes": ("gestational diabetes", "MONDO:0005406"),
    # EFO:0000400 was the original mapping here; the 2026-08-09 grounding
    # benchmark (scripts/eval/grounding_benchmark.py) caught it as a real
    # stale ID - it's obsolete in EFO's current release with no recorded
    # replacement (`obsolete_diabetes mellitus`, replaced_by=None). Switched
    # to MONDO:0005015, verified against the real synced MONDO data: exists,
    # not obsolete, label "diabetes mellitus", reachable from MONDO:0000001.
    "diabetes": ("diabetes mellitus", "MONDO:0005015"),
    "autism": ("autism spectrum disorder", "MONDO:0005258"),
    "asd": ("autism spectrum disorder", "MONDO:0005258"),
    "multiple sclerosis": ("multiple sclerosis", "MONDO:0005301"),
    "depression": ("major depressive disorder", "MONDO:0002009"),
    "anxiety": ("anxiety disorder", "MONDO:0005618"),
    "covid-19": ("COVID-19", "MONDO:0100096"),
    "sars-cov-2": ("COVID-19", "MONDO:0100096"),
    "covid": ("COVID-19", "MONDO:0100096"),
    "hiv": ("HIV infectious disease", "MONDO:0005109"),
    "hepatitis": ("hepatitis", "MONDO:0002251"),
    "liver cirrhosis": ("cirrhosis of liver", "MONDO:0005155"),
    "nonalcoholic fatty liver": (
        "metabolic dysfunction-associated steatotic liver disease",
        "MONDO:0013209",
    ),
    "nafld": (
        "metabolic dysfunction-associated steatotic liver disease",
        "MONDO:0013209",
    ),
    "celiac": ("celiac disease", "MONDO:0005130"),
    "coeliac": ("celiac disease", "MONDO:0005130"),
    "asthma": ("asthma", "MONDO:0004979"),
    "allergy": ("allergic disease", "MONDO:0005271"),
    "rheumatoid arthritis": ("rheumatoid arthritis", "MONDO:0008383"),
    "lupus": ("systemic lupus erythematosus", "MONDO:0007915"),
    "psoriasis": ("psoriasis", "MONDO:0005083"),
    # Real gap found in the 2026-08-09 semantic-hardening pass: unlike "egg
    # allergy" (the only real MONDO terms for that are both obsolete with
    # no replacement - "allergic disease" below is genuinely the best
    # available answer), "food allergy" has a real, non-obsolete, branch-
    # valid MONDO term (MONDO:0700226) that the old "allergy" catch-all
    # below was silently overriding with a too-generic answer.
    "food allergy": ("food allergy", "MONDO:0700226"),
    "antibiotic": ("antibiotic exposure", ""),
    "healthy": ("healthy", ""),
    "control": ("healthy", ""),
    "normal": ("healthy", ""),
}


def _extract_clean_disease_name(raw_text: str) -> str:
    strip_phrases = [
        "patients with",
        "patient with",
        "subjects with",
        "individuals with",
        "diagnosis of",
        "diagnosed with",
        "suffering from",
        "history of",
        "associated with",
        "related to",
        "study of",
        "analysis of",
    ]
    text = raw_text.lower()
    for phrase in strip_phrases:
        text = text.replace(phrase, "")
    return text.strip()


# "control"/"normal"/"healthy" describe the comparator arm of a case-control
# study, not a diagnosis - and they're frequently *longer* than the disease
# abbreviation they're being contrasted with ("IBD patients vs healthy
# controls", "HIV patients compared to controls"). Plain longest-match-wins
# would pick "control(s)" over "IBD"/"HIV"/"ASD"/"T2D" and misreport the
# actual studied condition as "healthy". These three keys are only used as
# a last resort, never over a real disease-name match.
_HEALTHY_KEYS = frozenset({"healthy", "control", "normal"})

_MATCHER = LookupMatcher(CONDITION_LOOKUP, deferred_keys=_HEALTHY_KEYS)


def _progressive_queries(query: str, max_extra: int = 2):
    """Yield ``query``, then progressively shorter variants: trailing-word-
    dropped first, then leading-word-dropped.

    Leading-word-dropping found via a live cross-check against real MONDO
    grounding results: a clinical modifier
    prefix like "diarrhea-predominant" or "early-onset" often precedes the
    core condition name in extracted text, and OLS/MONDO search can miss
    the full modifier-heavy phrase even though the bare condition name
    resolves cleanly (e.g. "diarrhea-predominant irritable bowel syndrome"
    found nothing, but "irritable bowel syndrome" resolved to
    MONDO:0005052).

    Trailing-word-dropping added after a real bug found in a 2026-08-09
    adversarial review: leading-word-dropping *alone* degrades a phrase
    like "parkinsons disease cohort" (a generic descriptor trailing the
    actual condition name - "cohort"/"patients"/"study" are common in
    extracted text) down to just "cohort", which found a real but
    completely wrong EFO term (EFO:0004445, literally "cohort") - the
    condition name itself was discarded first because it happened to be at
    the front. Trying trailing-drops first fixes this common case cheaply
    ("parkinsons disease cohort" -> "parkinsons disease" on the very next
    attempt) while leaving the original leading-drop behavior intact as a
    fallback for the modifier-prefix case it was built for.

    Capped at a couple of extra attempts *per direction* so a long,
    unrelated sentence can't turn into an unbounded number of live lookups
    - `mapping_confidence` for anything found this way is already capped
    at 0.9 (never "auto"), so a wrong guess here costs a curator's review
    attention, not a silent bad mapping.
    """
    yield query
    words = query.split()
    if len(words) <= 2:
        return

    yielded = {query}
    suffix_words = list(words)
    prefix_words = list(words)
    for _ in range(max_extra):
        if len(suffix_words) > 2:
            suffix_words = suffix_words[:-1]
            candidate = " ".join(suffix_words)
            if candidate not in yielded:
                yielded.add(candidate)
                yield candidate
        if len(prefix_words) > 2:
            prefix_words = prefix_words[1:]
            candidate = " ".join(prefix_words)
            if candidate not in yielded:
                yielded.add(candidate)
                yield candidate


def _resolve_more_specific_override(
    raw_text: str, generic_ontology_id: str
) -> Optional[NormalizedTerm]:
    """When a static-dict key matches only because it's a substring of a
    longer, more specific phrase ("Alzheimer's" inside "Alzheimer's disease
    biomarker measurement"; "hepatitis" inside "Hepatitis virus-related
    hepatocellular carcinoma" - a different disease, not a hepatitis
    subtype), check whether the *complete* raw text is itself a real, exact
    EFO/MONDO label or synonym - and if so, prefer it over the generic
    substring match.

    Real, confirmed gap found in this pass's independent evaluation: EFO
    has real, exact terms for disease-specific *measurements* ("Alzheimer's
    disease biomarker measurement" EFO:0006514, "COVID-19 symptoms
    measurement" EFO:0600019, "Parkinson's disease symptom measurement"
    EFO:0600011, "Obese/Overweight body mass index status"), specific
    infection subtypes ("HIV-1 infection" EFO:0000180), and specific
    disease subtypes ("Atopic asthma", "Psoriasis vulgaris", "Metastatic
    colorectal cancer") that the static dict's generic disease keys were
    silently overriding at "auto" tier.

    The safety criterion is deliberately "the full raw text is an exact
    (case/whitespace-insensitive) match to a real ontology label", not a
    numeric confidence cutoff picked to make known cases pass:
    `local_lookup()`'s EFO confidence for many of these lands at 0.7, not
    because the match is weak (it's scope=exact, 100% textual similarity -
    the strongest signal that function can report) but because
    `rank_candidates_explained()` correctly penalizes it for not being
    reachable from EFO's "disease" root - exactly right for a term that
    genuinely isn't a disease, but not a reason to distrust an otherwise
    perfect full-text match here (see docs/GROUNDING_ARCHITECTURE.md's
    2026-08-09 semantic-hardening section for why BugSigDB's Condition
    field legitimately covers EFO's full "experimental factor" breadth,
    not disease alone - the same finding that ruled out a blanket
    disease-only category filter for this field). Requiring an *exact*
    label match (not just "any hit") is what keeps this from ever
    replacing a real static-dict answer with a weaker guess: "Type 2
    diabetes" and "obesity" both return real local hits that are NOT exact
    matches to the raw text ("type 2 diabetes mellitus", "obesity
    disorder") and correctly do not override anything."""
    cleaned = normalize_spelling(raw_text).strip()
    if not cleaned:
        return None
    local_hit = local_lookup(cleaned, ("efo", "mondo"))
    if local_hit is None or not local_hit.ontology_id:
        return None
    if local_hit.ontology_id == generic_ontology_id:
        return None
    if local_hit.status != "PRESENT":
        return None
    if local_hit.label.strip().casefold() != cleaned.casefold():
        return None
    return local_hit


def normalize_condition(raw_text: str) -> NormalizedTerm:
    """Return normalized condition label, EFO ID, status, and mapping confidence."""
    if is_null_like(raw_text):
        return NormalizedTerm.absent()

    lowered = normalize_spelling(raw_text.lower())
    hit = _MATCHER.match_longest(lowered)
    if hit:
        matched_key, (label, efo_id) = hit
        if matched_key in _HEALTHY_KEYS:
            # A comparator-arm/exposure key only ever wins when nothing
            # else matched (LookupMatcher's deferred-key rule) - no
            # candidates in that case, matching the original behavior.
            return NormalizedTerm(label, efo_id, "PRESENT", 1.0)
        override = _resolve_more_specific_override(raw_text, efo_id)
        if override is not None:
            return override
        candidates = _MATCHER.candidates(lowered, matched_key, (label, efo_id))
        if candidates:
            return NormalizedTerm(
                label, efo_id, "PARTIALLY_PRESENT", 0.9, candidates=candidates
            )
        return NormalizedTerm(label, efo_id, "PRESENT", 1.0)

    # Nothing in the static dict matched. Before any network call: try the
    # local ontology store - real, complete EFO/MONDO data (2026-08
    # adversarial review found this had no production caller at all; see
    # app.normalization.local_lookup's module docstring for why and what
    # changed). Same EFO-then-MONDO precedence as the live fallback below,
    # same progressive-query shortening, but offline and sub-millisecond -
    # for any term the complete local ontology already covers, this now
    # answers instead of ever reaching the network.
    clean_term = _extract_clean_disease_name(normalize_spelling(raw_text))
    query = clean_term or raw_text.strip()
    for candidate in _progressive_queries(query):
        local_hit = local_lookup(candidate, ("efo", "mondo"))
        if local_hit:
            return local_hit

    # Live fallback for anything the local store also doesn't have: try
    # EFO first (matches this module's documented convention), then
    # MONDO - EFO has retired most disease terms in favor of MONDO (see
    # the dict's docstring), so a term absent from EFO is often still live
    # in MONDO. Both providers go through ols_search()'s persistent cache
    # (see app.normalization.ontology_cache), so a term only needs a live
    # lookup once - subsequent calls for the same term are served from
    # that cache.
    for candidate in _progressive_queries(query):
        hit = ols_search(candidate, "efo", "EFO", mapping_confidence=0.9)
        if not hit:
            hit = ols_search(candidate, "mondo", "MONDO", mapping_confidence=0.9)
        if hit:
            label, efo_id, conf = hit
            return NormalizedTerm(label, efo_id, "PRESENT", conf)

    stripped = raw_text.strip()
    return NormalizedTerm(stripped, "", "PARTIALLY_PRESENT", 0.5)
