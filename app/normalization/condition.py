"""Condition normalization aligned with EFO canonical labels and IDs."""

from __future__ import annotations

import re
from dataclasses import replace
from typing import Dict, Optional, Tuple

from app.normalization import embedding_match
from app.normalization.bugsigdb_vocabulary import BugSigDBVocabulary, get_vocabulary
from app.normalization.local_lookup import _get_backend as local_lookup_backend
from app.normalization.local_lookup import local_lookup
from app.normalization.ols import ols_search
from app.normalization.types import (
    LookupMatcher,
    NormalizedTerm,
    is_null_like,
    normalize_spelling,
)

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
    "type ii diabetes": ("type 2 diabetes mellitus", "MONDO:0005148"),
    "type i diabetes": ("type 1 diabetes mellitus", "MONDO:0005147"),
    "gestational diabetes": ("gestational diabetes", "MONDO:0005406"),
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
    # MAFLD / MASLD are renamings of NAFLD: BugSigDB curates all of them as
    # MONDO:0013209. Without these keys, word-dropping lands on the parent
    # "fatty liver disease" (MONDO:0004790). Longer keys win in match_longest.
    "mafld": (
        "metabolic dysfunction-associated steatotic liver disease",
        "MONDO:0013209",
    ),
    "masld": (
        "metabolic dysfunction-associated steatotic liver disease",
        "MONDO:0013209",
    ),
    "metabolic associated fatty liver disease": (
        "metabolic dysfunction-associated steatotic liver disease",
        "MONDO:0013209",
    ),
    "metabolic dysfunction associated fatty liver disease": (
        "metabolic dysfunction-associated steatotic liver disease",
        "MONDO:0013209",
    ),
    "metabolic dysfunction associated steatotic liver disease": (
        "metabolic dysfunction-associated steatotic liver disease",
        "MONDO:0013209",
    ),
    "metabolic-associated fatty liver disease": (
        "metabolic dysfunction-associated steatotic liver disease",
        "MONDO:0013209",
    ),
    "metabolic dysfunction-associated fatty liver disease": (
        "metabolic dysfunction-associated steatotic liver disease",
        "MONDO:0013209",
    ),
    "metabolic dysfunction-associated steatotic liver disease": (
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


# Leading qualifiers that describe a subtype/severity/course of a condition
# rather than naming a different one. Stripped only when the full phrase has
# no exact ontology match (so "chronic kidney disease" and "acute myeloid
# leukemia", which do match exactly, are never touched).
_QUALIFIER_WORDS = frozenset(
    {
        "severe",
        "mild",
        "moderate",
        "refractory",
        "generalized",
        "generalised",
        "uncontrolled",
        "active",
        "recurrent",
        "chronic",
        "acute",
        "early-onset",
        "late-onset",
        "early onset",
        "late onset",
        "advanced",
    }
)
_RESISTANT_RE = re.compile(r"^[\w-]+-resistant$")

# Confidence for a match reached through the fallbacks below; < 1.0, so the
# result is always "review" tier.
_FALLBACK_CONFIDENCE = 0.8


def _exact_live_hit(query: str) -> Optional[NormalizedTerm]:
    """An exact (label/synonym) local EFO/MONDO hit for *query* that is not
    obsolete, else None."""
    hit = local_lookup(query, ("efo", "mondo"))
    if hit is None or not hit.ontology_id or hit.status == "ABSENT":
        return None
    if not _is_live(hit.ontology_id):
        return None
    return hit


def _strip_leading_qualifiers(query: str) -> str:
    words = query.split()
    while len(words) > 1:
        two = " ".join(words[:2]).lower()
        if two in _QUALIFIER_WORDS:
            words = words[2:]
        elif words[0].lower() in _QUALIFIER_WORDS or _RESISTANT_RE.match(
            words[0].lower()
        ):
            words = words[1:]
        else:
            break
    return " ".join(words)


def _exact_fallback(query: str, raw_text: str) -> Optional[NormalizedTerm]:
    """Last offline resorts before a live search / giving up, both exact
    lookups against live ontology terms:

    (a) EFO names many traits "<X> measurement" ("smoking status measurement"),
        so a near-synonym like "smoking status" finds it by appending that.
    (b) A leading severity/course qualifier ("severe periodontitis") is
        dropped and the bare entity looked up. The original phrase stays in
        `raw` so a curator sees what was dropped.

    Both cap mapping_confidence below 1.0 (review tier)."""
    query = (query or "").strip()
    if not query:
        return None
    raw = raw_text.strip()
    candidates = []
    stripped = _strip_leading_qualifiers(query)
    if not query.lower().endswith("measurement"):
        candidates.append(f"{query} measurement")
    if stripped and stripped != query:
        candidates.append(stripped)
    for candidate in candidates:
        hit = _exact_live_hit(candidate)
        if hit is not None:
            return replace(
                hit,
                mapping_confidence=min(hit.mapping_confidence, _FALLBACK_CONFIDENCE),
                raw=raw,
            )
    return None


def _ground_condition(raw_text: str) -> NormalizedTerm:
    """Ground free text to an EFO/MONDO term: static dict -> local ontology
    store -> live OLS. Labels here are the ontology's own; see
    `normalize_condition()` for the BugSigDB-vocabulary steps applied after."""
    lowered = normalize_spelling(raw_text.lower())
    hit = _MATCHER.match_longest(lowered)
    if hit:
        matched_key, (label, efo_id) = hit
        if matched_key in _HEALTHY_KEYS:
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

    clean_term = _extract_clean_disease_name(normalize_spelling(raw_text))
    query = clean_term or raw_text.strip()
    for candidate in _progressive_queries(query):
        local_hit = local_lookup(candidate, ("efo", "mondo"))
        if local_hit:
            return local_hit

    fallback = _exact_fallback(query, raw_text)
    if fallback is not None:
        return fallback

    for candidate in _progressive_queries(query):
        hit = ols_search(candidate, "efo", "EFO", mapping_confidence=0.9)
        if not hit:
            hit = ols_search(candidate, "mondo", "MONDO", mapping_confidence=0.9)
        if hit:
            label, efo_id, conf = hit
            return NormalizedTerm(label, efo_id, "PRESENT", conf)

    stripped = raw_text.strip()
    return NormalizedTerm(stripped, "", "PARTIALLY_PRESENT", 0.5)


# Static-dict outcomes that deliberately carry no ontology ID ("healthy",
# "antibiotic exposure"): never snap these to a vocabulary term.
_NO_ID_LABELS = frozenset(
    label.casefold() for label, curie in CONDITION_LOOKUP.values() if not curie
)

# Below this cosine, nearest vocabulary terms aren't even offered as
# candidates - they're noise (e.g. "FGT inflammation" -> "gingivitis", 0.57).
_CANDIDATE_FLOOR = 0.6


def _bugsigdb_equivalent(curie: str, vocab: BugSigDBVocabulary) -> Optional[str]:
    """A CURIE in BugSigDB's vocabulary that the local ontology store
    declares equivalent to *curie* (an EFO<->MONDO cross-reference), or None.

    Reused from metacurator's grounding audit, which treats a match in a
    sibling ontology ("CROSS-ONTO") as the same concept rather than a
    disagreement. Example: "posttraumatic stress disorder" is an exact EFO
    synonym of EFO:0001358, while BugSigDB records MONDO:0005146 for the same
    disease; MONDO:0005146 lists EFO:0001358 as a cross-reference."""
    try:
        backend = local_lookup_backend()
        neighbours = list(backend.get_xrefs(curie.split(":")[0].lower(), curie))
        neighbours += [c for _, c in backend.find_by_xref(curie)]
    except Exception:
        return None
    for other in neighbours:
        if (
            other.split(":")[0].upper() in ("EFO", "MONDO")
            and vocab.contains(other)
            and _is_live(other)
        ):
            return other.upper()
    return None


def _is_live(curie: str) -> bool:
    """False only when the local ontology store says *curie* is obsolete.

    BugSigDB's own records still carry a few retired IDs - "SARS-CoV-2-related
    disease" is MONDO:0100318, obsolete in MONDO with no replacement - so a
    vocabulary term is never adopted on the vocabulary's word alone. IDs from
    ontologies the store doesn't hold (OBA, GO, ...) can't be checked and are
    allowed, as before."""
    try:
        prefix = curie.split(":")[0].lower()
        return local_lookup_backend().is_obsolete(curie, prefix) is not True
    except Exception:
        return True


def _retired_term_replacement(
    raw_text: str, vocab: BugSigDBVocabulary
) -> Optional[str]:
    """When the text exactly names an *obsolete* EFO/MONDO term, the live
    BugSigDB-vocabulary term that replaced it, or None.

    metacurator's grounding rejects obsolete terms and surfaces `replaced_by`
    rather than keeping a dead ID. EFO retired many disease terms in favour
    of MONDO ones without filling `replaced_by` - "posttraumatic stress
    disorder" is an exact synonym only of obsolete EFO:0001358, and "HPV
    infection" only of obsolete EFO:0001668 - so the replacement is found
    through the ontology's own cross-references too. Exact label/synonym
    matches only, and the target must be live and one BugSigDB has used."""
    cleaned = _extract_clean_disease_name(normalize_spelling(raw_text)) or raw_text
    try:
        backend = local_lookup_backend()
        for ontology in ("efo", "mondo"):
            for retired, replaced_by in backend.lookup_obsolete(cleaned, ontology):
                targets = [replaced_by] if replaced_by else []
                targets += backend.get_xrefs(ontology, retired)
                targets += [c for _, c in backend.find_by_xref(retired)]
                for target in targets:
                    prefix = target.split(":")[0].lower()
                    if prefix not in ("efo", "mondo") or not vocab.contains(target):
                        continue
                    if backend.is_obsolete(target, prefix) is not True:
                        return target.upper()
    except Exception:
        return None
    return None


def _relabel(term: NormalizedTerm, vocab: BugSigDBVocabulary) -> NormalizedTerm:
    """Swap the ontology's label for BugSigDB's label of the same ID, on the
    term and its candidates. The ID itself never changes."""
    label = vocab.label_for(term.ontology_id) or term.label
    candidates = tuple(
        (vocab.label_for(cid) or clabel, cid) for clabel, cid in term.candidates
    )
    if label == term.label and candidates == term.candidates:
        return term
    return replace(term, label=label, candidates=candidates)


def normalize_condition(raw_text: str) -> NormalizedTerm:
    """Return normalized condition label, ontology ID, status, and mapping
    confidence, expressed in BugSigDB's own Condition vocabulary wherever
    the paper's condition is one BugSigDB has curated before.

    Steps, in order (each measured on the 2026-11-12 100-paper benchmark;
    see CONDITION_FIELD_FINDINGS.md):

    1. Ground to EFO/MONDO as before (`_ground_condition`).
    2. Exact BugSigDB label: if the whole text *is* a BugSigDB label, that
       curated label-to-ID pairing beats a keyword or search hit.
    3. Cross-ontology equivalence: an EFO ID BugSigDB doesn't use is swapped
       for the equivalent MONDO ID it does use, or vice versa (metacurator).
    4. Embedding match: still nothing in BugSigDB's vocabulary - take the
       nearest BugSigDB term by SapBERT cosine if it clears the threshold
       (MetaHarmonizer stage 2); otherwise attach the nearest terms as
       candidates for a curator (and for LLM disambiguation, see
       app/services/bugsigdb_analyzer/condition_disambiguation.py).
    5. Relabel: show BugSigDB's label for the final ID.

    Steps 2-4 never produce mapping_confidence 1.0, so anything they decide
    lands in "review" tier, never "auto".
    """
    if is_null_like(raw_text):
        return NormalizedTerm.absent()

    vocab = get_vocabulary()
    term = _ground_condition(raw_text)
    if len(vocab) == 0:
        return term

    exact = vocab.match_label(normalize_spelling(raw_text).strip())
    if exact is None:
        exact = vocab.match_label(
            _extract_clean_disease_name(normalize_spelling(raw_text))
        )
    if (
        exact is not None
        and exact[1].upper() != term.ontology_id.upper()
        and _is_live(exact[1])
    ):
        displaced = ((term.label, term.ontology_id),) if term.ontology_id else ()
        term = NormalizedTerm(exact[0], exact[1], "PRESENT", 0.95, candidates=displaced)

    if not term.ontology_id:
        replacement = _retired_term_replacement(raw_text, vocab)
        if replacement is not None:
            term = NormalizedTerm(
                vocab.label_for(replacement) or "", replacement, "PRESENT", 0.85
            )

    if term.ontology_id and not vocab.contains(term.ontology_id):
        equivalent = _bugsigdb_equivalent(term.ontology_id, vocab)
        if equivalent:
            term = replace(
                term,
                ontology_id=equivalent,
                mapping_confidence=min(term.mapping_confidence, 0.9),
            )

    needs_vocab_term = not term.ontology_id or not vocab.contains(term.ontology_id)
    if needs_vocab_term and term.label.casefold() not in _NO_ID_LABELS:
        neighbours = [
            n
            for n in embedding_match.nearest(term.label, k=5, vocab=vocab)
            if _is_live(n[1])
        ]
        if neighbours and neighbours[0][2] >= embedding_match.threshold():
            best_label, best_curie, score = neighbours[0]
            others = [(lbl, cid) for lbl, cid, _ in neighbours[1:]]
            if term.ontology_id:
                others.insert(0, (term.label, term.ontology_id))
            term = NormalizedTerm(
                best_label,
                best_curie,
                "PRESENT",
                min(round(score, 3), embedding_match.MAX_SNAP_CONFIDENCE),
                candidates=tuple(others[:4]),
            )
        elif neighbours and neighbours[0][2] >= _CANDIDATE_FLOOR:
            extra = tuple(
                (lbl, cid)
                for lbl, cid, _ in neighbours
                if cid.upper() != term.ontology_id.upper()
            )
            term = replace(term, candidates=tuple(term.candidates) + extra)

    term = _relabel(term, vocab)
    if term.label.strip() != raw_text.strip() and not term.raw:
        term = replace(term, raw=raw_text.strip())
    return term
