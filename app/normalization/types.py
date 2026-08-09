"""Shared types and lookup-matching helpers for ontology-aligned field
normalization."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Dict, Tuple


@dataclass(frozen=True)
class NormalizedTerm:
    """Label, ontology ID, extraction status, and mapping confidence."""

    label: str
    ontology_id: str
    status: str
    mapping_confidence: float
    raw: str = ""
    # Up to 2 runner-up (label, ontology_id) pairs from the same lookup dict,
    # surfaced so curators can pick an alternative when the mapping tier isn't
    # "auto" (see app.normalization.grounding). Empty for API-resolved terms,
    # which only ever produce a single candidate.
    candidates: Tuple[Tuple[str, str], ...] = field(default_factory=tuple)

    @classmethod
    def absent(cls) -> NormalizedTerm:
        return cls(label="", ontology_id="", status="ABSENT", mapping_confidence=0.0)


def best_lookup_match(lowered: str, lookup: Dict[str, str]) -> tuple[str, int] | None:
    """
    Find the longest lookup key that's a substring of `lowered`, returning
    its mapped value and the matched key's length (used to break ties
    between overlapping keys, e.g. "16s" vs "16s rrna").

    Shared by sequencing_type.py and the other field normalizers, which each
    have their own controlled-vocabulary lookup dict but need identical
    matching logic.
    """
    matched = None
    matched_len = 0
    for key, value in lookup.items():
        if key in lowered and len(key) > matched_len:
            matched = value
            matched_len = len(key)
    if matched is None:
        return None
    return matched, matched_len


def found_vocab_types(lowered: str, lookup: Dict[str, str]) -> set[str]:
    """Return the set of distinct vocab values whose lookup key appears in `lowered`."""
    return {value for key, value in lookup.items() if key in lowered}


class LookupMatcher:
    """One shared implementation of "match free text against a
    keyword -> (label, ontology_id) dict" - the pattern host_species.py,
    body_site.py, and condition.py each independently reimplemented (three
    separate longest-match loops, one with its own bespoke deferred-key and
    candidate-filtering logic) before a 2026-08 production-readiness audit
    found the duplication and consolidated it here.

    Two matching modes, because the three call sites didn't actually agree
    on one: `match_longest()` (host_species.py's and condition.py's rule -
    the single longest matching key wins) and `match_all()` (body_site.py's
    rule - every distinct matching value, since body_site.py treats *any*
    plural match as reportable ambiguity rather than picking one). Both are
    kept as explicit, named methods rather than collapsed into one "mode"
    flag - the two rules produce genuinely different results and a caller
    should have to say which one it means.

    `deferred_keys` generalizes condition.py's `_HEALTHY_KEYS`: keys in this
    set only win if nothing else matches at all. Empty by default, which
    makes `match_longest()` identical to host_species.py's original
    `_lookup_species()` with no behavior change.

    Matching against the input text is word-boundary-aware (`\\bkey\\b`),
    not raw substring (`key in text`). **Real, severe false-positive bug
    found in a 2026-08-09 adversarial review**: raw substring matching made
    "rat" (-> Rattus norvegicus, confidence 1.0, "auto" tier - no curator
    review) match inside the word "laboratory" ("labo-RAT-ory"), and
    "colon" (-> UBERON:0001155, confidence 1.0) match inside "semicolon".
    Confirmed reproducible: `normalize_host_species("samples were
    processed in the laboratory")` returned Rattus norvegicus at "auto"
    tier before this fix. "laboratory" is one of the most common words in
    scientific writing - this was not a contrived edge case. Fixed by
    requiring the key to appear as a whole word (or whole phrase, for
    multi-word keys like "mus musculus") in the input, not merely as a
    character sequence anywhere in it. Key-to-key relationships (e.g.
    "diabetes" being a substring of the phrase "type 2 diabetes" in
    `candidates()` below) are a different, legitimate concept - phrase
    nesting between dictionary entries, not text matching - and are
    deliberately left as plain substring checks.
    """

    def __init__(
        self,
        lookup: Dict[str, Tuple[str, str]],
        *,
        deferred_keys: frozenset[str] = frozenset(),
    ):
        self._lookup = lookup
        self._deferred_keys = deferred_keys
        self._patterns = {
            key: re.compile(r"\b" + re.escape(key) + r"\b") for key in lookup
        }

    def _matches(self, key: str, lowered: str) -> bool:
        return self._patterns[key].search(lowered) is not None

    def match_longest(self, lowered: str) -> Tuple[str, Tuple[str, str]] | None:
        """The single longest non-deferred matching key, or - only if
        nothing else matched - the first matching deferred key. Returns
        `(matched_key, value)` or None."""
        best_key = ""
        best_value: Tuple[str, str] | None = None
        deferred_match: Tuple[str, Tuple[str, str]] | None = None
        for key, value in self._lookup.items():
            if not self._matches(key, lowered):
                continue
            if key in self._deferred_keys:
                if deferred_match is None:
                    deferred_match = (key, value)
                continue
            if len(key) > len(best_key):
                best_key, best_value = key, value
        if best_value is not None:
            return best_key, best_value
        return deferred_match

    def match_all(self, lowered: str) -> list[Tuple[str, Tuple[str, str]]]:
        """Every distinct matching `(key, value)` pair, deduplicated by
        value, in dict-iteration order (body_site.py's "collect everything"
        rule - it treats multiple distinct matches as ambiguity to report,
        not something to pick a single winner from by length)."""
        found: list[Tuple[str, Tuple[str, str]]] = []
        seen_values: set = set()
        for key, value in self._lookup.items():
            if self._matches(key, lowered) and value not in seen_values:
                found.append((key, value))
                seen_values.add(value)
        return found

    def candidates(
        self,
        lowered: str,
        winning_key: str,
        winning_value: Tuple[str, str],
        *,
        limit: int = 2,
    ) -> Tuple[Tuple[str, str], ...]:
        """Other distinct matches to surface as curator-facing alternatives
        when a match isn't clean enough for "auto" tier - generalizes
        condition.py's `_other_condition_candidates` and host_species.py's
        `_lookup_species_candidates`. Excludes the winning value itself and
        any key that's a substring or superstring of `winning_key` (the
        same mention at a different specificity - "diabetes" is not a
        distinct candidate from a winning "type 2 diabetes" match - not a
        second condition). This substring/superstring exclusion was
        previously only in condition.py; body_site.py's inline candidate
        logic didn't have it (an inconsistency the 2026-08 audit found and
        fixed here) - verified against BODY_SITE_LOOKUP's actual content
        that no existing multi-match test case depended on the old,
        unfiltered behavior (every same-concept key pair in that dict
        already collapses to one shared value, deduplicated above `value not
        in found`, before this filter would ever apply)."""
        found: list[Tuple[str, str]] = []
        for key, value in self._lookup.items():
            if not self._matches(key, lowered) or key in self._deferred_keys:
                continue
            if value == winning_value:
                continue
            if key in winning_key or winning_key in key:
                continue
            if value not in found:
                found.append(value)
            if len(found) >= limit:
                break
        return tuple(found)


# British -> American spelling variants that show up in scientific papers and
# would otherwise miss both our static lookup dicts and live OLS/MONDO
# queries (e.g. a paper saying "faecal" scores as a mismatch against our
# "feces" entries even though it's the same site) - ported from
# MetaHarmonizer's _BRITISH_TO_AMERICAN list after a benchmark against
# BugSigDB's real curated corpus found this exact gap (see
# docs/METACURATOR_METAHARMONIZER_ANALYSIS.md). Applied before matching, not
# as a lookup-dict key, so it benefits the normalizers that call it today
# (body_site.py, condition.py — and their live search fallback) without
# duplicating entries.
_BRITISH_TO_AMERICAN = (
    (re.compile(r"faeces", re.IGNORECASE), "feces"),
    (re.compile(r"faecal", re.IGNORECASE), "fecal"),
    (re.compile(r"oesophag", re.IGNORECASE), "esophag"),
    (re.compile(r"leukaemia", re.IGNORECASE), "leukemia"),
    (re.compile(r"tumour", re.IGNORECASE), "tumor"),
    (re.compile(r"haemato", re.IGNORECASE), "hemato"),
    (re.compile(r"haemoglobin", re.IGNORECASE), "hemoglobin"),
    (re.compile(r"haemorrhag", re.IGNORECASE), "hemorrhag"),
    (re.compile(r"anaemia", re.IGNORECASE), "anemia"),
    (re.compile(r"oedema", re.IGNORECASE), "edema"),
    (re.compile(r"paediatric", re.IGNORECASE), "pediatric"),
    (re.compile(r"foetal", re.IGNORECASE), "fetal"),
    (re.compile(r"foetus", re.IGNORECASE), "fetus"),
    (re.compile(r"gynaecolog", re.IGNORECASE), "gynecolog"),
    (re.compile(r"diarrhoea", re.IGNORECASE), "diarrhea"),
    (re.compile(r"colour", re.IGNORECASE), "color"),
)


def normalize_spelling(text: str) -> str:
    """Rewrite British spelling variants to American, case-insensitively.

    Called by body_site.py and condition.py before dict/keyword matching and
    before building a live OLS/MONDO search query, so a British-spelled term
    in the source paper matches the same lookup entries and search results an
    American-spelled one would. Not currently called by host_species.py or
    sequencing_type.py.
    """
    for pattern, replacement in _BRITISH_TO_AMERICAN:
        text = pattern.sub(replacement, text)
    return text
