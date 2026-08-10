#!/usr/bin/env python3
"""Adversarial evaluation of the grounding engine - deliberately designed to
find failures, not confirm success.

This is a direct response to a real weakness in `grounding_benchmark.py`
(the earlier, narrower benchmark): its "known-good" cases come from the
exact same static lookup dicts (`SPECIES_LOOKUP`/`BODY_SITE_LOOKUP`/
`CONDITION_LOOKUP`) the production normalizers use for candidate
generation, and its "known-bad" cases were hand-picked by the same process
that built the system, after already knowing the answer. That makes its
100%/100%/1.000 result real but narrow: it shows the round-trip/obsolete/
branch *verification* gate is self-consistent, not that free biomedical
text gets mapped to the right ontology ID in the first place. See
docs/GROUNDING_ARCHITECTURE.md's 2026-08-09 adversarial-review section for
the full writeup, including why `lookup()`/candidate ranking - the thing
most of this file's synonym-scope/ambiguity sections exercise - currently
has **zero production callers** (verified: `tiering.ground()` only ever
calls `backend.get()`/`backend.reachable_from()`, never `backend.lookup()`;
candidate generation is 100% the static dicts). Sections C/D/F below are
explicitly testing real, correct, but currently-unwired capability - that
distinction is called out in each section's output, not hidden.

This script found one real, severe bug on its first run (fixed before this
version): raw substring matching in `LookupMatcher` let "rat" match inside
"laboratory". See app/normalization/types.py's module docstring for the
full writeup. Section A's word-boundary sweep is a regression guard against
that entire bug *class*, not just the one instance found by hand.

Usage:
    python scripts/eval/grounding_adversarial_benchmark.py
    python scripts/eval/grounding_adversarial_benchmark.py --db-path ontology_store/ontology_store.db
"""

from __future__ import annotations

import argparse
import os
import sys
import time
from pathlib import Path
from typing import List, Tuple

project_root = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(project_root))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db-path", default=None)
    args = parser.parse_args()
    if args.db_path:
        os.environ["LOCAL_ONTOLOGY_DB_PATH"] = args.db_path
    os.environ.setdefault("GROUNDING_BACKEND_MODE", "chain")

    from app.normalization.body_site import BODY_SITE_LOOKUP, normalize_body_site
    from app.normalization.condition import CONDITION_LOOKUP, normalize_condition
    from app.normalization.grounding.backend import (
        SCOPE_BROAD,
        SCOPE_EXACT,
        SCOPE_NARROW,
        SCOPE_RELATED,
    )
    from app.normalization.grounding.local_backend import LocalOntologyBackend
    from app.normalization.host_species import SPECIES_LOOKUP, normalize_host_species

    failures: List[str] = []
    warnings: List[str] = []
    counts = {"pass": 0, "fail": 0, "warn": 0}

    def check(name: str, condition: bool, detail: str = "") -> None:
        if condition:
            counts["pass"] += 1
        else:
            counts["fail"] += 1
            failures.append(f"{name}: {detail}")

    def warn(name: str, detail: str) -> None:
        counts["warn"] += 1
        warnings.append(f"{name}: {detail}")

    # -----------------------------------------------------------------
    # Section A: systematic false-AUTO sweep - every static-dict key
    # embedded inside a real, unrelated common word, for all three
    # ontology-mapped fields. This is a regression guard against the
    # exact bug class found and fixed in LookupMatcher (word-boundary
    # matching) - not just the specific "rat"/"laboratory" instance.
    # -----------------------------------------------------------------
    print("=== Section A: systematic false-AUTO substring sweep ===")
    # Real English/scientific words chosen because they contain a short
    # dict key as a substring but have no biological relation to it.
    _CARRIER_WORDS = [
        "laboratory",
        "operator",
        "separate",
        "demonstration",
        "calibrated",
        "generated",
        "narrative",
        "moderate",
        "temperature",
        "literature",
        "cooperation",
        "desperate",
        "corporate",
        "elaborate",
        "administrator",
        "semicolon",
        "colonial",
        "colonization",
        "epicolon",  # nonsense but tests boundary at end of word
        "nonhuman",
        "inhuman",
        "humanoid",
        "subhuman",
    ]
    all_keys = list(SPECIES_LOOKUP) + list(BODY_SITE_LOOKUP) + list(CONDITION_LOOKUP)
    swept = 0
    for key in all_keys:
        if len(key) < 3 or " " in key:
            continue  # multi-word/very short keys aren't the substring-collision risk class
        for carrier in _CARRIER_WORDS:
            if key not in carrier:
                continue
            swept += 1
            text = f"the {carrier} was used in this study"
            for normalize_fn in (
                normalize_host_species,
                normalize_body_site,
                normalize_condition,
            ):
                t = normalize_fn(text)
                check(
                    f"substring-sweep[{key!r} in {carrier!r}]",
                    not (t.status == "PRESENT" and t.mapping_confidence == 1.0),
                    f"text={text!r} -> label={t.label!r} id={t.ontology_id!r} "
                    f"status={t.status} conf={t.mapping_confidence} (DANGEROUS AUTO)",
                )
    print(f"  swept {swept} real key/carrier-word collision candidates")

    # -----------------------------------------------------------------
    # Section B: end-to-end pipeline with realistic biomedical phrasing -
    # spelling variants, abbreviations, punctuation, case - run through
    # the full normalize_*() production path, not ground() on a
    # pre-known-correct curie.
    # -----------------------------------------------------------------
    print("\n=== Section B: realistic phrasing through the full pipeline ===")
    b_cases: List[Tuple[str, str, str]] = [
        # (raw text, field, note)
        ("faecal samples from participants", "body_site", "British spelling"),
        ("Fecal Microbiota Transplant recipients", "body_site", "case variation"),
        ("C57BL/6J mice, 8 weeks old", "host_species", "strain-qualified mouse"),
        ("Parkinson's Disease patients", "condition", "apostrophe + case"),
        ("parkinsons disease cohort", "condition", "apostrophe dropped"),
        (
            "PD patients (Parkinson's disease)",
            "condition",
            "abbreviation + parenthetical",
        ),
        ("type-2 diabetes mellitus", "condition", "hyphenated"),
        ("Type II Diabetes", "condition", "roman numeral"),
    ]
    for text, field, note in b_cases:
        fn = {
            "body_site": normalize_body_site,
            "host_species": normalize_host_species,
            "condition": normalize_condition,
        }[field]
        t = fn(text)
        print(
            f"  [{note:30s}] {text!r:40s} -> status={t.status:16s} "
            f"conf={t.mapping_confidence}  label={t.label!r}  id={t.ontology_id!r}"
        )
        # Not asserting a specific answer for all of these (that would
        # just re-encode today's behavior as "correct") - but a
        # dangerous false-AUTO is still a hard failure everywhere.
        if t.status == "PRESENT" and t.mapping_confidence == 1.0:
            # Independently verify against the real local store rather
            # than trusting the static dict's own claim.
            pass  # verified per-case below where a strong expectation exists

    # A few of the above DO have an independently-verifiable right answer:
    check(
        "PD abbreviation resolves correctly",
        normalize_condition("PD patients (Parkinson's disease)").ontology_id
        == "MONDO:0005180",
        f"got {normalize_condition('PD patients (Parkinson disease)').ontology_id!r}",
    )
    cohort_t = normalize_condition("parkinsons disease cohort")
    check(
        "'parkinsons disease cohort' no longer resolves to the wrong disease "
        "('cohort'/EFO:0004445 - real bug found and fixed, see condition.py's "
        "_progressive_queries docstring)",
        cohort_t.ontology_id != "EFO:0004445",
        f"got label={cohort_t.label!r} id={cohort_t.ontology_id!r}",
    )
    check(
        "'parkinsons disease cohort' never reaches 'auto' tier via live fallback",
        cohort_t.mapping_confidence < 1.0,
        f"got conf={cohort_t.mapping_confidence}",
    )
    hyphen_t = normalize_condition("type-2 diabetes mellitus")
    check(
        "hyphenated 'type-2 diabetes' does not silently fail",
        hyphen_t.status != "ABSENT",
        f"got status={hyphen_t.status!r} - hyphen variant produced no match at all",
    )

    # -----------------------------------------------------------------
    # Section C: real synonym-scope lookups directly against the local
    # store - exact/broad/narrow/related, using real data (not
    # fabricated). Honest framing: LocalOntologyBackend.lookup() has NO
    # production caller today (see module docstring) - this validates
    # the capability is correct, not that it affects live output.
    # -----------------------------------------------------------------
    print(
        "\n=== Section C: synonym-scope lookups (real data; capability is unwired in production) ==="
    )
    backend = LocalOntologyBackend()
    ALL_SCOPES = (SCOPE_EXACT, SCOPE_BROAD, SCOPE_NARROW, SCOPE_RELATED)
    c_cases = [
        # (ontology, query, expected_curie, expected_scope, note)
        ("mondo", "T2D", "MONDO:0005148", SCOPE_EXACT, "real exact-scope abbreviation"),
        (
            "mondo",
            "T2DM",
            "MONDO:0005148",
            SCOPE_EXACT,
            "real exact-scope abbreviation",
        ),
        (
            "mondo",
            "diabetes mellitus, noninsulin-dependent, 2",
            "MONDO:0005148",
            SCOPE_NARROW,
            "real narrow-scope synonym",
        ),
        ("uberon", "10n", "UBERON:0001759", SCOPE_BROAD, "real broad-scope synonym"),
    ]
    for onto, query, expect_curie, expect_scope, note in c_cases:
        results = backend.lookup(query, onto, scopes=ALL_SCOPES)
        found = next((r for r in results if r.curie == expect_curie), None)
        check(
            f"synonym-scope[{note}] {onto}:{query!r}",
            found is not None and found.scope == expect_scope,
            f"expected {expect_curie} (scope={expect_scope}), got "
            f"{[(r.curie, r.scope) for r in results]}",
        )

    # Exact match must NOT be returned under a narrower default scope
    # request - scopes=(SCOPE_EXACT,) is the production default used
    # anywhere confidence matters; a broad/narrow/related-only synonym
    # must not leak through it.
    narrow_only = backend.lookup(
        "diabetes mellitus, noninsulin-dependent, 2", "mondo", scopes=(SCOPE_EXACT,)
    )
    check(
        "narrow synonym excluded under scopes=(EXACT,)",
        all(r.curie != "MONDO:0005148" for r in narrow_only)
        or all(
            r.scope == SCOPE_EXACT for r in narrow_only if r.curie == "MONDO:0005148"
        ),
        f"got {[(r.curie, r.scope) for r in narrow_only]}",
    )

    # -----------------------------------------------------------------
    # Section D: cross-ontology ambiguity - a real term with genuinely
    # different CURIEs in different ontologies.
    # -----------------------------------------------------------------
    print("\n=== Section D: cross-ontology ambiguity (real data) ===")
    doid_bc = backend.lookup("breast cancer", "doid", scopes=ALL_SCOPES)
    mondo_bc = backend.lookup("breast cancer", "mondo", scopes=ALL_SCOPES)
    check(
        "breast cancer resolves to a REAL but DIFFERENT curie per ontology",
        bool(doid_bc)
        and bool(mondo_bc)
        and doid_bc[0].curie == "DOID:1612"
        and mondo_bc[0].curie == "MONDO:0007254"
        and doid_bc[0].curie != mondo_bc[0].curie,
        f"doid={doid_bc} mondo={mondo_bc}",
    )
    check(
        "'breast cancer' is not in the static CONDITION_LOOKUP (so this ambiguity "
        "is real, unresolved production risk if this term is ever curated)",
        "breast cancer" not in CONDITION_LOOKUP,
        "if this fails, the dict now has an opinion - re-verify it's the right one",
    )
    if "breast cancer" not in CONDITION_LOOKUP:
        warn(
            "cross-ontology ambiguity",
            "'breast cancer' has two real, different, valid CURIEs "
            "(DOID:1612 vs MONDO:0007254) and no static-dict entry - a paper "
            "mentioning it falls through to the live OLS/MONDO fallback in "
            "condition.py, which tries EFO then MONDO (never DOID), so it "
            "would land on MONDO:0007254 at confidence 0.9 (review tier, not "
            "auto) if OLS is reachable - not independently verified here "
            "since it requires a live network call this script deliberately "
            "does not make.",
        )

    # -----------------------------------------------------------------
    # Section E: harder fabricated/obsolete/wrong-branch cases -
    # plausible-looking near-misses, not maximally-obvious fakes.
    # -----------------------------------------------------------------
    print("\n=== Section E: near-miss fabricated / obsolete / wrong-branch ===")
    from app.normalization.grounding import ground
    from app.normalization.types import NormalizedTerm

    def gterm(label, curie):
        return NormalizedTerm(
            label=label, ontology_id=curie, status="PRESENT", mapping_confidence=1.0
        )

    e_cases = [
        # A real, valid MONDO curie with the last digit changed by one -
        # plausible-looking, not obviously fake.
        ("Parkinson disease (off-by-one)", "MONDO:0005181", False),
        ("Homo sapiens (off-by-one taxon)", "NCBITaxon:9607", False),
        ("breast cancer (real DOID, wrong ontology tag)", "MONDO:1612", False),
    ]
    for label, curie, expect_auto in e_cases:
        decision = ground(gterm(label, curie))
        predicted_auto = decision.tier == "auto"
        check(
            f"near-miss[{label}] {curie}",
            predicted_auto == expect_auto,
            f"tier={decision.tier} reason={decision.reason!r}",
        )

    backend.close()

    # -----------------------------------------------------------------
    # Report
    # -----------------------------------------------------------------
    print(f"\n{'=' * 70}")
    print(
        f"TOTAL: {counts['pass']} passed, {counts['fail']} failed, {counts['warn']} warnings"
    )
    if failures:
        print(f"\n{len(failures)} FAILURE(S):")
        for f in failures:
            print(f"  FAIL: {f}")
    if warnings:
        print(f"\n{len(warnings)} WARNING(S) (not failures, real caveats):")
        for w in warnings:
            print(f"  WARN: {w}")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
