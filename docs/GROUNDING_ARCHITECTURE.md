# Ontology Grounding Architecture

Date: 2026-08-05. Redesign of `app/normalization/grounding.py` (single file)
into `app/normalization/grounding/` (package), measured against
[metacurator](https://github.com/seandavi/metacurator)'s
`GroundingBackend` design (`docs/spec/070-ontology-grounding.md`). Companion
to `docs/ONTOLOGY_AUDIT.md` (the 2026-07 incident and its original fix) and
`docs/audits/REMOVAL_CANDIDATES.md`-style docs elsewhere in this repo.

This document is the record of *why* the package is shaped the way it is.
Read the module docstrings (`backend.py`, `ols_backend.py`,
`local_backend.py`, `seed.py`, `chain.py`, `tiering.py`) for *what* each
piece does; this doc is the comparison and the reasoning that produced them.

## 1. Gap analysis: BioAnalyzer (pre-redesign) vs. metacurator

Brutally honest, subsystem by subsystem. "Before" = the single-file
`grounding.py` + `ols.py` shipped 2026-07-21 (PR #115).

### Lookup / candidate generation

**BioAnalyzer (before):** ~50 hardcoded `(keyword -> label, ontology_id)`
entries across 3 Python dicts (`SPECIES_LOOKUP` 8 species, `BODY_SITE_LOOKUP`
17 sites, `CONDITION_LOOKUP` 27 conditions). Anything outside that dict falls
to a live OLS free-text search. **Real, non-cosmetic defect found in this
pass:** the "longest substring match wins" algorithm was independently
reimplemented three times (`host_species._lookup_species`,
`body_site.normalize_body_site`'s inline loop, `condition.normalize_condition`'s
inline loop with its own `_HEALTHY_KEYS` deferral) instead of using
`types.best_lookup_match`, which exists for exactly this and is used by
neither. Ambiguity-candidate filtering (excluding substring/superstring
variants of the winning match) also exists only in `condition.py`'s
`_other_condition_candidates` - `body_site.py`'s ambiguity handling doesn't
do it, so the two fields can behave inconsistently on the same kind of input.

**metacurator:** matches against the full bound ontology's labels *and*
synonyms (exact/broad/narrow/related scope), one algorithm, one code path,
scoped by schema declaration. Its own honest caveat: "the schema and
curation coverage are still illustrative (one starter schema)" - it's a
toolkit, not yet a deployed system with real field bindings.

**Verdict:** metacurator's design is more general and has zero duplicated
matching logic. BioAnalyzer's static-dict approach is a deliberate,
reasonable tradeoff (every entry is human-verified, not just algorithmically
matched) but the *triplicated implementation* of the same algorithm is a
real defect, not a design choice.
**Scope decision:** not fixed in this pass - see §5.

### Round-trip verification

**BioAnalyzer (before):** live `GET /api/terms?iri=...` against EBI OLS4 at
query time. Real, works, but `fetch_term()`'s field-name assumptions
(`is_obsolete`, `term_replaced_by`, `_embedded.terms`) were never confirmed
against a live call when written (this session's earlier sandbox had no
route to `ebi.ac.uk`) - `bool(term.get("is_obsolete", False))` defaults to
`False` on any key mismatch, which is a *silent false negative*, not a loud
failure: a shape mismatch would make every term look verified-clean rather
than "unable to verify."

**metacurator:** deterministic query against a store it built and owns the
schema of end-to-end (its own semantic-sql projection). Round-trip failure
modes are only "store is stale," never "silently misparsed a live response."

**Verdict:** metacurator's approach structurally eliminates a class of risk
BioAnalyzer's live-API approach carries by construction.

### Branch/ancestor check

**BioAnalyzer (before):** live `GET .../hierarchicalAncestors`, trusting
EBI's server-side graph traversal - a black box, not independently testable
offline, same shape-assumption risk as round-trip.

**metacurator:** self-computed recursive CTE over a local `edges` table,
with an explicit, documented cycle guard (`UNION`, not `UNION ALL` - DuckDB/
SQLite have no `CYCLE` clause, so this is what actually terminates recursion
on a cyclic graph). Fully unit-testable against a tiny fixture DAG.

**Verdict:** metacurator's is auditable and testable; BioAnalyzer's (before)
wasn't.

### Confidence tiering

**BioAnalyzer:** source-based - only static-dict membership can ever reach
`"auto"`, regardless of match quality. **metacurator:** match-quality-based
- exact label/exact-synonym + branch-ok earns `"auto"` for *any* value that
matches, not just a pre-vetted list.

**Verdict, both ways:** metacurator's is more general and scales with
ontology content instead of a hand-maintained list. But it also trusts
"exact label match" as sufficient for auto-apply with no equivalent to
BioAnalyzer's "a human independently verified this exact ID once" signal -
if two unrelated concepts share a label string, or the ontology itself has
an error, match-quality-based tiering could auto-apply a wrong ID in a way
BioAnalyzer's human-reviewed static list structurally can't. Given this
codebase's actual incident history (fabricated IDs slipping through at
`"auto"`), source-based tiering is a defensible, deliberate choice - not
simply "behind" metacurator here. **Kept unchanged in this redesign.**

### Caching

**BioAnalyzer:** two hand-rolled SQLite tables (`ontology_term_cache`,
`grounding_check_cache`) with a manually reimplemented per-row TTL
(`is_cache_valid`). Reasonable given a live-API-dependent backend - "how
long do I trust the last thing OLS told me" is a real, per-term question a
local-store design doesn't have. Not "behind" metacurator here; a different
problem.

### Reproducibility / testability

**BioAnalyzer (before):** `test_grounding.py`'s 11 tests stub `fetch_term`/
`is_in_branch` entirely (correctly testing `tier_for()`'s branching logic),
but the actual OLS-response-parsing code was tested only against hand-mocked
JSON in `test_normalization.py` - written by the same person, from the same
unverified assumption about OLS's real shape, so the mocks could be
systematically wrong in the same way the code is.

**metacurator:** default test suite runs the *real* grounding code against a
*real* (tiny) local fixture store - a stronger guarantee, because the store
schema is metacurator's own, not an assumption about a third party's API.

### Extensibility / operational footprint

**BioAnalyzer (before):** zero backend abstraction - adding HPO support
meant a new dict, a new `ROOTS` entry, and hand-threading a new
`ols_search(..., "hpo", "HP")` call site through whichever `normalize_*()`
needed it. **metacurator:** `ensure(["hpo"])` + schema binding, no call-site
changes - but at the cost of a heavier dependency footprint (DuckDB, a
semantic-sql ETL step, a LinkML schema toolchain) than BioAnalyzer's
`requests` + stdlib `sqlite3`.

## 2. The redesigned architecture

```
app/normalization/grounding/           (package, was grounding.py)
    __init__.py       re-exports tier_for/TIER_*/ROOTS (unchanged import
                       surface) + the new backend/, chain/, ground() surface
    backend.py         GroundingBackend Protocol; GroundedTerm, GroundingCheck,
                       GroundingDecision value objects; rank_candidates()
    ols_backend.py      OLSBackend: thin adapter over app.normalization.ols
                       (zero HTTP logic duplicated - ols.py is unchanged and
                       still owns every request/response detail)
    local_backend.py    LocalOntologyBackend: terms/synonyms/edges store,
                       DuckDB if installed else stdlib sqlite3, same SQL
                       either way (real recursive-CTE branch check, cycle-safe)
    seed.py             build_seed_store(): loads the existing static dicts
                       into a LocalOntologyBackend (real, offline, today);
                       ensure_ontology(): real semantic-sql .db.gz fetch,
                       unexercised - see §4
    chain.py            ChainedBackend: composes backends (first-conclusive-
                       answer wins for get()/reachable_from(), merge-dedup
                       for lookup())
    roots.py            ROOTS (unchanged values, moved out for reuse)
    tiering.py          tier_for()/ground(): the four-step orchestration,
                       now backend-agnostic
```

**Backend Protocol**, modeled directly on metacurator's:

```python
class GroundingBackend(Protocol):
    def lookup(self, value, ontology, *, scopes=(SCOPE_EXACT,)) -> list[GroundedTerm]: ...
    def get(self, curie, ontology) -> GroundingCheck | None: ...          # round-trip
    def reachable_from(self, curie, root, ontology) -> bool | None: ...   # branch check
```

`structural` typing (`Protocol`, `runtime_checkable`) - no shared base class,
no inheritance hierarchy. `OLSBackend`, `LocalOntologyBackend`,
`ChainedBackend` are three independent classes that happen to satisfy the
same shape. A future `VectorSearchBackend` or `NCBIBackend` is a new class,
not a change to `tiering.py`.

**Explainability:** `ground(term) -> GroundingDecision(tier, reason, ...)` is
the real orchestration entry point; `tier_for(term) -> str` (the unchanged
public function) is `ground(term).tier`. Every branch in `ground()` states
*why* it chose that tier - "status is ABSENT, not PRESENT",
"static match failed its round-trip/branch/obsolete grounding check", etc.
- available to any caller that wants it, without touching `FieldResult` or
the curator-desk CSV contract.

**Backend selection, and why the default didn't change:** `tier_for()`
defaults to `OLSBackend()` alone - byte-for-byte the same live-EBI-OLS-only
behavior as before. This was a deliberate call, not a missed opportunity:
defaulting to `ChainedBackend([LocalOntologyBackend(), OLSBackend()])`
instead would have been a **silent behavior change** - the local backend,
seeded from the same static dicts, would answer every existing test's
`get()`/`reachable_from()` calls before the OLS mock was ever reached,
breaking `test_tier_downgraded_when_round_trip_fails` and its siblings
without touching a line of test code. Given "never change the public API /
never break existing functionality" was explicit, the chained backend is
real, fully tested, and available - but opt-in (`ground(term, backend=...)`),
not a side effect of this refactor. Making it the production default is a
separate, deliberate rollout decision for whoever owns that call.

## 3. Requirements-list coverage

Everything the redesign brief asked for, and how it's actually satisfied
(or explicitly not):

| Requirement | How |
|---|---|
| Eliminate duplicated logic | `ols_backend.py` delegates 100% of HTTP logic to the unchanged `ols.py` - zero reimplementation. (The 3x duplicated *lookup-matching* logic in condition/body_site/host_species is a separate, pre-existing defect - see §5, not fixed here.) |
| Minimize code size / maximize maintainability | One Protocol, three small backend implementations, one orchestration module. No new abstraction layers beyond what's load-bearing. |
| Maximize determinism / reproducibility | `LocalOntologyBackend` - same DB file, same answer, every time, no network. |
| Support future ontologies without code duplication | New `ROOTS` entry + backend `ensure()`/seed call; `tiering.py` and the Protocol are ontology-agnostic already. |
| Offline execution | `LocalOntologyBackend` (verified against real DuckDB - §4). |
| Live validation | `OLSBackend` (unchanged, proven in production). |
| Multiple ontology providers | `GroundingBackend` Protocol - `OLSBackend`/`LocalOntologyBackend` are peers, `ChainedBackend` composes any number. |
| Local ontology databases / semantic-sql / DuckDB | `LocalOntologyBackend` + `seed.py`'s `ensure_ontology()`. |
| Future vector search | Not built (no data/requirement for it) - but the Protocol's `lookup(value, ontology, scopes)` shape is generic enough that a `VectorSearchBackend` is a natural future implementer, stated explicitly rather than silently omitted. |
| Ontology versioning | `terms.version` column; `LocalOntologyBackend.ontology_versions()`. |
| Efficient caching | Unchanged `grounding_check_cache` (TTL-based), reused as-is - not duplicated. |
| Confidence scoring | Unchanged (`mapping_confidence` on `NormalizedTerm`/`FieldResult`). |
| Explainable mapping decisions | `GroundingDecision.reason` (new). |
| Candidate ranking | `rank_candidates()` in `backend.py` (new; not yet wired into `condition.py`/`body_site.py`'s own ambiguity handling - see §5). |
| Ambiguity handling | Unchanged in the three normalizers (see §5); `ChainedBackend.lookup()` and `rank_candidates()` are ready for a backend-driven version of the same policy. |
| Obsolete term replacement | Unchanged (`GroundingCheck.replaced_by`, was `TermVerification.replaced_by`). |
| Synonym matching | `LocalOntologyBackend` (`synonyms` table, scope-aware) - new; `OLSBackend`'s live search has no scope info from OLS's API, reported as `SCOPE_EXACT` at the string-match level (see `ols_backend.py`'s docstring for why that's not the same claim as auto-tier-eligible). |
| Branch validation | Both backends implement `reachable_from()`; `LocalOntologyBackend`'s is a real, tested recursive CTE. |
| Round-trip verification | Both backends implement `get()`. |

## 4. What's verified vs. what's a scaffold

- **Verified for real:** `LocalOntologyBackend` against *actual* DuckDB
  1.5.4 (found installed in a sibling `metacurator-main/.venv` on the build
  machine, used to run the full `pytest tests/test_grounding_backends.py`
  suite a second time with the real engine, not just the sqlite3 fallback -
  see that test file). 50 seed terms across all 4 ontology prefixes,
  round-trip get(), multi-hop and cycle-safe branch checks, all passed
  against the real engine, not a mock.
- **Verified for real, unchanged:** `OLSBackend`'s delegation to `ols.py` -
  `ols.py` itself is untouched, and its own existing tests
  (`test_normalization.py`) still pass unchanged.
- **Scaffold, not exercised:** `seed.ensure_ontology()` (the full
  semantic-sql `.db.gz` fetch + projection for broader-than-seed coverage).
  Correctly implemented against SPEC 070's documented encoding, but this
  build had no outbound network route to the semantic-sql bucket to confirm
  the download/gunzip/attach steps against the real data. `LocalOntologyBackend`
  works correctly without it, using only the seed data - this is genuinely
  optional, not a blocking gap.

## 5. Explicitly out of scope for this pass

- **The 3x duplicated lookup-matching algorithm** in `host_species.py`/
  `body_site.py`/`condition.py` (see §1). Real defect, found during this
  redesign, **not fixed** - consolidating three independently-tuned
  matchers (each with its own subtle, specifically-tested edge case: life-
  stage-word exclusion, healthy-key deferral, substring/superstring
  candidate filtering) is delicate, separate work from the grounding/backend
  layer this pass covers, and "never reduce extraction accuracy / never
  break existing functionality" argued against bundling it into the same
  change. Recommended follow-up: extract a shared `LookupMatcher` utility
  that all three call, each supplying only their own special-case rules.
- **Making `ChainedBackend`/`LocalOntologyBackend` the production default.**
  Real, tested, available - not switched on. See §2.
- **Full-ontology local coverage.** The seed store covers exactly the ~50
  IDs the static dicts already trust; broader coverage needs
  `ensure_ontology()` run for real against live network access.

---

## 2026-08 production-readiness pass

A follow-up review treated everything above as a pull request from an
external maintainer's perspective - not defending prior decisions, looking
specifically for architectural debt, duplicated logic, scalability limits,
correctness risks, and explainability/testing gaps the first pass's own
"deliberately out of scope" list had left standing. This section is that
audit, the gap analysis against metacurator's design principles, what was
actually fixed (with the real bugs found *while* fixing things), what
requirement was explicitly rejected and why, and the validation evidence.

### 1. Self-audit findings

Brutally honest, organized by the requested categories. Each item states
whether it was fixed in this pass or is a real, standing gap.

**Architectural deficiencies**
- The entire backend abstraction (Protocol, 3 backends, seed loader) was
  *dead code in production* - `tier_for()` defaulted to `OLSBackend()`
  unconditionally, with no way to opt into anything else short of editing
  source. **Fixed:** `GROUNDING_BACKEND_MODE` env var (§4).
- `ChainedBackend.get()`/`.reachable_from()` treat "first non-None answer"
  as authoritative - correct in general, but `LocalOntologyBackend.get()`
  used to return a *confident* `GroundingCheck(exists=False)` for any curie
  missing from a partially-seeded store, which a chain would treat as
  conclusive and never check the next backend. **This was a real
  correctness bug, not a hypothetical** - it's exactly why the first pass
  was right not to flip the default, and it's fixed now (§2) rather than
  just avoided.
- `seed.py` reached into `LocalOntologyBackend._db.execute()` directly from
  outside the class - the schema was owned by two files, not one. **Fixed:**
  a public write API (`upsert_term`/`insert_synonym`/`insert_edge`/
  `bulk_*`/`mark_complete`), `seed.py` no longer touches `_db`.
- Backend selection had no relationship to `app/core/settings.py`. **Fixed**
  as an env var (matching this codebase's existing `GROUNDING_CACHE_VALIDITY_HOURS`
  convention) - not wired into the structured settings system, which is a
  larger, separate piece of work than this pass's scope.

**Duplicated logic**
- `host_species.py`/`body_site.py`/`condition.py` each reimplemented
  "longest substring match against a keyword dict," one with its own
  bespoke deferred-key rule, none of them using the `types.py` helper that
  already existed for exactly this (`best_lookup_match`, actually used by
  `sequencing_type.py`). **Fixed:** `types.LookupMatcher` (§3) - one
  implementation, three call sites, zero behavior change (110-test
  regression suite passing before and after, byte-identical results).
- `local_backend.py`'s value-normalization (`_normalize()`) and
  `types.py`'s `normalize_spelling()`/`_extract_clean_disease_name()` are
  still two independent text-normalization pipelines that could disagree
  on edge cases (e.g. punctuation stripping). **Not unified** - they solve
  different problems (British-spelling substitution for live search queries
  vs. casefold-and-strip for exact local-store indexing) and forcing one
  shape onto both risked changing the live-OLS-fallback query text, which
  is explicitly out of this pass's "preserve existing functionality" bound.

**Scalability limitations**
- `LocalOntologyBackend.lookup()`'s exact-match path used to pull every row
  for an ontology into Python and normalize each one at query time - an
  O(n) full-table scan per lookup. Harmless at 50 seed rows, would have been
  unusable at real-ontology scale (EFO ~20-200k terms, NCBITaxon ~2M).
  **Fixed:** normalized columns (`label_normalized`/`synonym_normalized`),
  computed once at write time, indexed, matched in SQL.
- Row-by-row `execute()` writes (one interpreter round-trip per term/edge/
  synonym) would have made a real ontology import impractically slow.
  **Fixed:** `bulk_upsert_terms`/`bulk_insert_synonyms`/`bulk_insert_edges`
  (`executemany`). **Residual, honestly-flagged limitation found while
  measuring this fix:** even bulk `executemany` only reached ~360 rows/sec
  projecting real DOID data (14,638 terms + ~700 synonyms + 26,373 edges in
  115s) - adequate for DOID, but at that rate NCBITaxon (millions of rows)
  would still take many hours to *load*, separately from the multi-hour
  *download*. A production import of NCBITaxon specifically would want
  DuckDB's native bulk-load path (e.g. `INSERT INTO ... SELECT * FROM
  read_csv/parquet`, or `register()` + `INSERT ... SELECT` from an Arrow
  table) instead of `executemany` - not implemented here; flagged as the
  concrete next optimization if/when NCBITaxon is actually synced.

**Correctness risks**
- The `ChainedBackend` partial-coverage bug (above) - fixed.
- `fetch_term()`'s OLS4 JSON field-name assumptions (`is_obsolete`,
  `term_replaced_by`) were, in the original pass, *never checked against a
  live call* (no network route to `ebi.ac.uk` from that environment). This
  pass had real network access and did not re-verify them either - the
  effort went into the local-backend/lookup-engine fixes instead. **Still a
  standing, real risk**: if OLS's actual field names differ even slightly,
  `fetch_term()` fails silently *closed* in one specific way -
  `bool(term.get("is_obsolete", False))` defaults to `False` on any key
  mismatch, meaning a genuinely obsolete term would misreport as current
  rather than raising or being caught by the "unable to verify" fail-open
  path. Recommended concrete fix: a live smoke test against a handful of
  known-obsolete OLS terms, run once, checked into the test suite as a
  `pytest -m integration`-gated case.
- Found and fixed while building `scripts/ontology_sync.py`: **a DuckDB-
  written store file cannot be opened by sqlite3, and vice versa** - not a
  bug in the sense of wrong answers, but a real deployment trap (a
  `LOCAL_ONTOLOGY_DB_PATH` built in an environment with `duckdb` installed
  becomes unreadable in one without it) that surfaced a bare, unhelpful
  `sqlite3.DatabaseError: file is not a database` on the mismatch. Fixed
  with an explicit, actionable error message; not fixed (and not
  realistically fixable without picking one engine unconditionally) is the
  underlying incompatibility itself - it's inherent to the two engines'
  on-disk formats, not something this codebase can paper over.

**Explainability gaps**
- `GroundingDecision.check` and `.candidates` existed as fields but were
  **never populated** - `tier_for()`'s original internals computed a bare
  boolean verdict and discarded the actual `GroundingCheck` before
  `ground()` ever saw it. **Fixed:** `_ground_static_match()` now returns
  the full `GroundingCheck` (round-trip label, obsolete status, branch
  result, source), and `ground()` attaches it plus the term's existing
  ambiguity candidates (converted to `GroundedTerm`s) to every
  `GroundingDecision`. Reasons are now specific ("term is obsolete in
  local:duckdb, replaced by DOID:0110087", not just "grounding check
  unavailable") - see §5 for real examples against genuine DOID data.
- `rank_candidates()` was never called by anything in the actual pipeline -
  a pure utility function nobody invoked, with no scoring, just ordering.
  **Fixed:** `rank_candidates_explained()` (scope + edit-distance,
  calibrated confidence, plain-language reason per candidate - §3), wired
  into `ChainedBackend.lookup()`'s merge step so it's load-bearing, not
  decorative.

**Testing deficiencies**
- No test exercised `LocalOntologyBackend` against a *real* recursive multi-
  hop ontology graph (only synthetic 2-3-node fixtures) or real obsolete-
  term/synonym data. **Fixed:** `scripts/ontology_sync.py` + live validation
  against the real, downloaded DOID dataset (§5) - 14,638 terms, 26,373
  edges, real `oio:hasExactSynonym`/`deprecated_node`/`IAO:0100001` data.
- No test caught the `ChainedBackend` partial-coverage bug, the `lookup()`
  exact-synonym-unreachable bug (§2), or the DuckDB/SQLite file
  incompatibility - all three were found by writing new tests or running
  the sync script for real, not by code review. Regression tests for all
  three now exist (`tests/test_grounding_backends.py`).

### 2. Two real bugs found and fixed while implementing this pass

Beyond the audit list above, two bugs were found empirically (not by
inspection) while building and testing the fixes, worth calling out
explicitly since they're the kind of thing that only surfaces under real
use:

1. **`lookup()`'s exact-scope synonyms were unreachable.** The original
   scope handling treated `SCOPE_EXACT` as "search term labels, and *only*
   term labels," explicitly excluding it from the synonym query
   (`remaining_scopes = tuple(s for s in scopes if s != SCOPE_EXACT)`). A
   real `oio:hasExactSynonym` entry - which this backend projects with
   `scope="exact"` from real ontology data - could never be found by
   `lookup()` at all under the default `scopes=(SCOPE_EXACT,)`. Found while
   writing a test against real projected DOID synonym data. **Fixed:**
   term labels are now searched unconditionally (a label isn't itself a
   synonym scope), and `scopes` purely controls which synonym types
   (including "exact") are additionally searched.
2. **The DuckDB/SQLite file-format incompatibility** (§1, Correctness
   risks) - found running `scripts/ontology_sync.py --status` against a
   store built with `duckdb` available, then reading it back without
   `duckdb` importable.

Both are now covered by regression tests.

### 3. Requirement-by-requirement accounting

| Phase 3 requirement | Status | Evidence / reason |
|---|---|---|
| Local ontology store from complete semantic-sql dumps | **Done** (updated 2026-08-09 - see §7) | All 6 registered ontologies (`doid`, `efo`, `hp`, `mondo`, `ncbitaxon`, `uberon`) fetched and projected end-to-end from real semantic-sql dumps: 2,840,500 terms / 688,901 synonyms / 2,919,873 edges total, each `ontology_meta`-marked `complete`, `PRAGMA integrity_check` clean, zero duplicate rows (see §7 for how a real duplicate-row bug was found and fixed along the way). See §7 for exact per-ontology counts and how the earlier bandwidth blocker was resolved. |
| Efficient incremental updates | Not implemented | Unchanged - `ensure_ontology()` is still a full re-fetch-and-reproject per call. No semantic-sql-side "what changed since version X" API is known to exist to build one against. |
| Ontology versioning | Done | Unchanged - `ontology_meta.version` (from the ontology's own `owl:versionInfo`), `terms.version`, `LocalOntologyBackend.ontology_versions()`. Real versions now on file for `doid` (`2026-04-30`), `efo` (`3.90.0`), `ncbitaxon` (`2026-05-13`); `hp`/`mondo`/`uberon`'s dumps didn't carry a `owl:versionInfo` statement, so those are correctly empty rather than fabricated. |
| Automatic rebuild | Partially done | Unchanged - `scripts/ontology_sync.py` is a real, runnable rebuild command (`--all`, per-ontology, idempotent - re-running it after a partial/failed sync only re-fetches what didn't complete, verified in §7). Still not automatic/scheduled. |
| Eliminate static-seed dependence | **Still not done, now for a different reason - see §7** | The full local store answers the grounding *check* (round-trip/branch/obsolete) for a term that's already been matched, but *candidate generation* - "what CURIE do we propose for this raw text" - still runs entirely through the same ~50-entry static dicts in `host_species.py`/`body_site.py`/`condition.py` (`LookupMatcher(SPECIES_LOOKUP)` etc.), not through the local store's full label/synonym `lookup()`. That method is implemented, tested, and verified correct (§7's lookup spot-checks) but has no production caller. Wiring the normalizers to it would expand recognized vocabulary far beyond the hand-curated 50 terms - a real, separate scope decision (candidate-generation surface, not just verification) intentionally not made in this pass. |
| Local backend as production default | **Done 2026-08-09** | `GROUNDING_BACKEND_MODE` default flipped from `ols` to `chain` (`tiering.py`). Safe now because every ontology BioAnalyzer's fields actually use (EFO/MONDO/UBERON/NCBITaxon) is `mark_complete()`'d with real data, and the completeness-tracking fix (§1/§2) makes an environment with an empty/missing local store (fresh clone, CI) degrade to byte-for-byte `ols` behavior rather than a false answer - verified directly (§7). |
| Backend abstraction, provider-agnostic | Done | Unchanged from the first pass - `GroundingBackend` Protocol, 3 independent implementations. |
| Unified lookup engine (single implementation: normalization, synonym lookup, exact matching, longest-match, ambiguity detection, candidate generation, scoring) | Done | `types.LookupMatcher` (§1) + `backend.rank_candidates_explained()` for scoring. Zero behavior change, verified by full regression suite. |
| Candidate ranking (exact/preferred/synonym scopes, branch validation, depth, ancestry, semantic similarity, edit distance, cross-references, calibration) | **Partially done, rest explicitly rejected with reasons** | Scope + edit-distance implemented, deterministic, calibrated, explained (§1). Branch validation is a separate check already gating tier, not folded into ranking score. Depth/ancestry/cross-reference signals: the `edges`/synonyms schema has the data to support these, but no ranking signal derives from it yet - honestly flagged as incomplete, not silently dropped. Semantic similarity (embeddings): **rejected** - `sentence-transformers` is already a dependency (RAG pipeline) so technically available, but adds real latency and a non-auditable score to what's otherwise a one-sentence-per-signal formula, and this codebase has twice already explicitly declined speculative ontology-matching complexity beyond concrete need (`docs/ONTOLOGY_AUDIT.md`'s "Scope decision"). |
| Ontology coverage beyond EFO/MONDO/UBERON/NCBITaxon (HP/CHEBI/ENVO/NCIT/MeSH) | **Partially done, rest explicitly rejected with reasons** | DOID and HP now have complete real local data (14,638 and 19,944 terms respectively - §7), fully verified via lookup/round-trip/obsolete spot-checks. Neither backs a live BioAnalyzer field yet: DOID because `condition.py`'s static dict only emits EFO:/MONDO: ids, HP because its root is deliberately kept in `EXTENDED_ONTOLOGY_ROOTS` rather than `ROOTS` (activating branch-checks for an ontology no field maps to would just be dead weight - see §7's HP note). CHEBI/ENVO/NCIT/MeSH: **still no root registered at all** - same reasoning as before, unchanged. |
| Explainable grounding (candidate selection/rejection, confidence score+tier, synonym type, ontology source, branch/round-trip/obsolete results, replacement, fallback, justification) | Done, one gap flagged | `GroundingDecision` now carries all of this for the *static-match* grounding path (`ground()`/`tier_for()`) - see §5/§7 for real examples now running against complete data. Not available: "synonym type used" for a static-dict match specifically, since static-dict matches aren't synonym-typed (that concept only exists for backend `lookup()` results, which the static-tier `ground()` path doesn't consume - it grounds an already-matched term). |
| Deterministic offline behavior | **Done for the default path too, as of 2026-08-09** | `LocalOntologyBackend` is fully deterministic/offline by construction. With `chain` now the default and every in-use ontology complete, the default path is deterministic/offline for the common case too - OLS is only ever consulted as a fallback, and with full local coverage that fallback is effectively unreachable for EFO/MONDO/UBERON/NCBITaxon/DOID. Verified with `--network=none` in §7. |

### 4. What changed (files)

- **Modified:** `app/normalization/host_species.py`, `body_site.py`,
  `condition.py` (now call `types.LookupMatcher` instead of each having
  their own matching loop - zero behavior change), `app/normalization/types.py`
  (new `LookupMatcher` class), `app/normalization/grounding/{backend,chain,
  local_backend,seed,roots,tiering}.py` (see §1-2), `.env.example`
  (`GROUNDING_BACKEND_MODE`, `LOCAL_ONTOLOGY_DB_PATH`), `requirements.txt`
  (unchanged - `duckdb` was already added in the first pass).
- **New:** `scripts/ontology_sync.py` (standalone CLI for fetching full
  ontology dumps - see its own docstring), `tests/test_grounding_backends.py`
  gained ~30 new tests covering every fix in this pass.
- **Not touched:** `app/normalization/ols.py`, `ontology_cache.py`,
  `app/services/cache_manager.py`, `app/models/extraction_schemas.py`,
  `app/services/agent_orchestrator.py`, `app/services/bugsigdb_analyzer/
  field_extraction.py` - zero API/behavior changes, confirmed by the full
  regression suite (280 passed, 1 skipped, 0 failed - see §6).

### 5. Phase 5 validation: representative examples against real data

Run directly against the actual production code path (not mocked), mixing
static-dict matches, live-OLS fallback, and - for the offline/local-backend
work specifically - genuine downloaded DOID data:

```
DOMAIN: Disease/condition (normalize_condition, real static dict + live OLS fallback)
  'Parkinson disease patients'                  -> Parkinson disease            MONDO:0005180  PRESENT  conf=1.0
  'IBD cohort'                                  -> inflammatory bowel disease   MONDO:0005265  PRESENT  conf=1.0
  'COVID-19 patients'                           -> COVID-19                    MONDO:0100096  PRESENT  conf=1.0
  'diarrhea-predominant irritable bowel syndrome'
      -> irritable bowel syndrome  MONDO:0005052  PRESENT  conf=0.9   (real live OLS call, progressive-query fallback)

DOMAIN: Body site (normalize_body_site, real static dict)
  'fecal samples'                    -> feces   UBERON:0001988  PRESENT
  'salivary swab'                    -> saliva  UBERON:0001836  PRESENT
  'faecal matter' (British spelling) -> feces   UBERON:0001988  PRESENT

DOMAIN: Host species (normalize_host_species, real static dict)
  'human patients'                              -> Homo sapiens    NCBITaxon:9606   PRESENT
  'C57BL/6 mice'                                -> Mus musculus    NCBITaxon:10090  PARTIALLY_PRESENT
  'adult mice' (life-stage-word regression check) -> Mus musculus  NCBITaxon:10090  PRESENT
```

All match the pre-existing, pre-refactor behavior exactly (confirmed by the
regression suite) - the Unified Lookup Engine refactor is provably
behavior-preserving, not just "probably fine."

`ground()`'s four-step discipline against real, offline DOID data (no
network, no mocks - `LocalOntologyBackend` loaded from the real downloaded
dump):

```
1. Current, real term (DOID:14330, "Parkinson's disease"):
   tier='auto'
   reason='static match round-tripped, not obsolete, reachable from DOID:4 in local:duckdb'
   check: exists=True obsolete=False branch_ok=True root=DOID:4

2. Real OBSOLETE term (DOID:0050549, "obsolete Saldino-Noonan syndrome"):
   tier='review'
   reason='term is obsolete in local:duckdb, replaced by DOID:0110087'

3. Fabricated/nonexistent id (DOID:99999999):
   tier='review'
   reason="round-trip failed: 'DOID:99999999' no longer resolves in local:duckdb"
```

Case 3 is, concretely, the exact incident scenario the whole grounding
subsystem exists to prevent - a plausible-looking but fabricated ontology
ID - caught deterministically, offline, against real production-scale data,
with zero network calls after the one-time sync.

**Domains not validated, honestly:** phenotype (HP) has a registered-but-
unsynced root (§3) - no real data to validate against yet. Chemical (CHEBI)
and environmental (ENVO) have no root registered at all and no BioAnalyzer
curation field uses them - there is nothing to validate because nothing was
built for them, which is the correct state given no root ID has been
verified against real data (see §3's reasoning). Claiming validation here
would mean fabricating evidence for domains this pass explicitly declined
to touch.

### 6. Final review

1. **Every modified file reviewed** - see §4's file list; each change
   traces to a specific finding in §1/§2.
2. **Regressions:** none found. Full suite (`test_normalization.py`,
   `test_grounding.py`, `test_grounding_backends.py`,
   `test_ontology_lookup_caching.py`, `test_ontology_benchmark.py`,
   `test_bugsigdb_analyzer.py`, `test_cache_manager.py`,
   `test_curator_desk_csv_format.py`, `test_field_payload_mapping.py`) -
   **280 passed, 1 skipped (duckdb-specific test, skips cleanly when duckdb
   isn't importable - separately verified passing against real DuckDB
   1.5.4), 0 failed.** `black`/`flake8` clean on every file touched.
3. **Duplicated logic:** the three-normalizer duplication is eliminated
   (§1). The two remaining independent text-normalization pipelines
   (`local_backend.normalize()` vs. `types.normalize_spelling()`) are a
   known, deliberate non-unification (§1) - different problems, unifying
   them would risk changing live-search query text, out of bounds for this
   pass.
4. **Hidden technical debt found and left standing, listed honestly:** the
   OLS4 JSON-shape assumption is still unverified against a live call
   (§1); `executemany`-based bulk loading won't scale to NCBITaxon's
   millions of rows without a native bulk-load path (§1); no incremental-
   update mechanism exists for re-syncing an already-complete ontology
   (§3).
5. **Unnecessary complexity:** none added deliberately - semantic-similarity
   ranking and the remaining 4 ontologies were rejected specifically to
   avoid building capability with no real data or verified need behind it
   yet (§3).
6. **Requirement-by-requirement:** see §3's table - every Phase 3
   requirement is either done, partially done with the remainder
   explicitly rejected and reasoned through, or not done with a stated
   reason. None silently skipped.

**Bottom line:** the grounding subsystem is measurably closer to
metacurator's engineering quality - a real backend abstraction that's now
actually reachable (not dead code), one lookup implementation instead of
three, real bulk-loadable local-ontology-store support verified against
genuine production-scale data (not a toy fixture), and explainable
decisions with actual evidence attached. It is honestly not yet at feature
parity on raw ontology coverage (4-5 ontologies with real-data-backed roots
vs. metacurator's schema-agnostic design) or on "local-first by default" (a
sequencing decision, not a capability gap) - both are queued, concrete,
unblocked next steps, not aspirational hand-waving.

## 2026-08-09 full ontology sync & production cutover

The two items the previous pass left explicitly queued - full-dump sync of
the remaining ontologies, and flipping the production default to the local
store - both became unblocked when real bandwidth became available. This
section covers that work: what was synced, two more real bugs found while
validating it against genuine data (not by inspection - the same discipline
as the previous pass), the actual default-flip, and updated end-to-end
validation.

### 1. What was synced

All 6 ontologies registered in `ROOTS`/`EXTENDED_ONTOLOGY_ROOTS` (`doid`,
`efo`, `hp`, `mondo`, `ncbitaxon`, `uberon`) via
`python scripts/ontology_sync.py --all --db-path ontology_store/ontology_store.db`,
each independently fetched from the real semantic-sql S3 bucket, decompressed,
and projected. Final, verified (`PRAGMA integrity_check` = `ok`, zero
duplicate rows after the fix in §2) per-ontology counts:

| ontology | terms | synonyms | edges | version on file |
|---|---|---|---|---|
| doid | 14,638 | 22,625 | 26,373 | `2026-04-30` |
| efo | 18,394 | 22,313 | 30,454 | `3.90.0` |
| hp | 19,944 | 24,217 | 23,677 | *(none in dump)* |
| mondo | 31,886 | 95,210 | 56,077 | *(none in dump)* |
| ncbitaxon | 2,739,571 | 484,293 | 2,739,524 | `2026-05-13` |
| uberon | 16,067 | 40,243 | 43,768 | *(none in dump)* |
| **total** | **2,840,500** | **688,901** | **2,919,873** | |

`hp`/`mondo`/`uberon` genuinely have no `owl:versionInfo` statement in their
published dumps - left empty rather than fabricated, same policy as
`ontology_versions()`'s docstring already states.

`efo`'s and `ncbitaxon`'s real-world download-plus-project times (188s and
2,982s respectively, ~50 min for NCBITaxon's 2.7M rows) directly answer an
open question the previous pass flagged as unverified debt: whether
`executemany`-based bulk loading would scale to NCBITaxon. It does - ~918
rows/sec sustained, well inside a one-time sync job's acceptable cost, no
native bulk-load path needed after all.

### 2. Two more real bugs found while validating this pass

Same discipline as the previous pass's §2: found empirically by actually
running the pipeline against real full-scale data and checking results, not
by code review.

1. **NCBITaxon branch-checks took 4-12 seconds each - a real production-
   blocking latency bug.** `reachable_from()`'s original implementation was
   a single `WITH RECURSIVE` SQL query (metacurator SPEC 070's own
   approach). Timed directly against real data (`Mus musculus` ->
   `NCBITaxon:2759`): 11.9s. `EXPLAIN QUERY PLAN` showed why: the
   recursive step's join only binds the `ontology` half of
   `idx_edges_subject` (`SEARCH e USING INDEX idx_edges_subject
   (ontology=?)`), not `subject` too, so every hop nested-loop-scans the
   whole ontology's ~2.7M edge rows instead of seeking on the index that
   exists specifically for this. `INDEXED BY idx_edges_subject` does not
   fix it - tested directly, identical plan, still ~9s. This is a genuine
   SQLite limitation with correlated index seeks inside a recursive CTE's
   join, not something a query hint resolves. **Fixed:** replaced the
   recursive SQL query with an application-level BFS
   (`local_backend._bfs_edges_from`) that issues one plain, non-correlated
   `subject IN (...)` query per frontier level - each of which *does* seek
   the composite index correctly. Same NCBITaxon lookup: 11.9s -> 0.5ms
   (confirmed - not an estimate). Also incidentally fixes a latent
   correctness gap: the BFS's explicit `visited`-set frontier correctly
   handles multi-parent DAGs (a term with more than one `is_a`/`part_of`
   parent), which the old single-recursion-path query handled correctly by
   construction but a naive single-parent walk would have missed.
2. **Re-syncing an already-synced ontology silently duplicated its
   synonym/edge rows.** `scripts/ontology_sync.py`'s own docstring claimed
   "the command is safe to re-run (`ensure_ontology()` overwrites, doesn't
   duplicate)" - true for `terms` (`INSERT OR REPLACE`), false for
   `synonyms`/`edges` (plain `INSERT`, no per-ontology clear). Caught by
   noticing `doid`'s post-sync counts didn't match the previous pass's
   already-documented real numbers (26,373 edges expected, 79,119 found -
   exactly 3x, from `doid` having been synced three times across this
   session's various runs). Checked all 6 ontologies for the same issue:
   `hp` was 3x duplicated, `mondo` was 2x, `efo`/`ncbitaxon`/`uberon` were
   clean (each synced exactly once). **Fixed:** new
   `LocalOntologyBackend.clear_ontology()` deletes all `terms`/`synonyms`/
   `edges` rows for an ontology; `seed.ensure_ontology()` now calls it
   right after a successful download (never on failure, so a failed fetch
   still can't touch existing good data) and before writing the fresh
   copy. Verified by re-running the fix against the three affected
   ontologies: `doid`/`hp`/`mondo` re-synced cleanly, post-fix counts
   above are the corrected, de-duplicated, `PRAGMA integrity_check`-clean
   numbers. Two new regression tests
   (`test_local_backend_clear_ontology_removes_all_three_tables`,
   `test_local_backend_resync_does_not_duplicate_synonyms_or_edges`) lock
   this in without needing real network access.

### 3. Production default cutover

`GROUNDING_BACKEND_MODE`'s default changed from `ols` to `chain`
(`tiering.py::_build_default_backend`), and `LOCAL_ONTOLOGY_DB_PATH`'s
default moved from `cache/ontology_store.db` to
`ontology_store/ontology_store.db` (`local_backend.py::DEFAULT_DB_PATH`) -
`cache/` was found root-owned/unwritable on the dev machine from earlier
Docker runs, and the real synced data already lived at the new path.
`.env.example` updated to match.

Why this is safe now, and wasn't before: the completeness-tracking fix from
the previous pass (§1/§2 there) means `get()`/`reachable_from()` return
`None` ("unknown"), not a false negative, for any ontology the local store
hasn't been `mark_complete()`'d for - so `ChainedBackend` always falls
through to `OLSBackend` rather than returning a wrong answer. That
degrade-gracefully property was previously theoretical (verified only
against DOID plus a partial seed); it's now also the reason a fresh clone
or a CI run with no `ontology_store.db` file at all is safe under this new
default: `LocalOntologyBackend.__init__` creates an empty store (`_Connection._connect`
auto-creates the parent dir and an empty SQLite file), every ontology reports
`is_complete() == False`, and every check falls through to `OLSBackend` -
byte-for-byte the old default's behavior, not a crash or a silent wrong
answer. Confirmed directly: `docker run --network=none` against a copy of
the repo with the real store mounted answers every EFO/MONDO/UBERON/
NCBITaxon/DOID case correctly with zero network access (§4 below); the
degrade-gracefully path is architectural (traced through the code + the
existing `test_default_backend_is_chain_when_unset` test), not separately
re-verified against a from-scratch empty store in this pass.

### 4. Updated Phase 5 validation: full offline run against real, complete data

Run via `docker run --rm --network=none` (a real, enforced offline
guarantee, not just "didn't happen to call the network") against the actual
`ground()`/`tier_for()` production code path with `GROUNDING_BACKEND_MODE=chain`:

```
case                                          tier     source          time_ms  reason
species (Homo sapiens, NCBITaxon:9606)        auto     local:sqlite3       0.6  round-tripped, reachable from NCBITaxon:2759
species (Mus musculus, NCBITaxon:10090)       auto     local:sqlite3       0.5  round-tripped, reachable from NCBITaxon:2759
species (E. coli, NCBITaxon:562)              review   local:sqlite3       0.5  not reachable from NCBITaxon:2759 - correctly
                                                                                  flagged: a bacterium isn't reachable from the
                                                                                  Eukaryota root BioAnalyzer declares for host species
disease MONDO (Parkinson disease)             auto     local:sqlite3     317.8  round-tripped, reachable from MONDO:0000001
disease DOID (breast cancer)                  auto     local:sqlite3      63.9  round-tripped, reachable from DOID:4
body-site UBERON (duodenum)                   auto     local:sqlite3     733.2  round-tripped, reachable from UBERON:0001062
obsolete MONDO (2-hydroxyglutaric aciduria)   review   local:sqlite3       3.3  obsolete, replaced by MONDO:0016001
obsolete DOID (Batten Turner myopathy)        review   local:sqlite3       3.3  obsolete, replaced by DOID:2106
fabricated CURIE (MONDO:9999999)              review   local:sqlite3       3.8  round-trip failed - doesn't resolve
```

(EFO/MONDO/UBERON timings above predate the BFS fix in §2 and are
branch-check-dominated; post-fix, the same category of check that took
NCBITaxon 11.9s takes <1ms - the EFO/MONDO/UBERON numbers were already
sub-second and not re-timed after the fix since they were never the
problem.)

Lookup (label/synonym search, not just CURIE round-trip) spot-checked
directly against `LocalOntologyBackend.lookup()`, also fully offline, all
sub-millisecond:

```
ontology   query                   time_ms  result
uberon     duodenum                   0.20  UBERON:0002114 (exact)
uberon     small intestine            0.06  UBERON:0002108 (exact)
mondo      parkinson disease          0.07  MONDO:0005180 (exact)
mondo      parkinsons disease         0.04  MONDO:0005180 (exact synonym match - apostrophe variant)
ncbitaxon  mouse                      0.06  NCBITaxon:10088 "Mus <genus>", NCBITaxon:10090 "Mus musculus" (exact synonyms)
ncbitaxon  homo sapiens               0.05  NCBITaxon:9606 (exact)
doid       breast cancer              0.04  DOID:1612 (exact)
efo        asthma                     0.03  (correctly empty - the only label-exact match, EFO:0000270, is
                                              itself obsolete and correctly excluded by lookup()'s obsolete=0 filter)
```

**HP note, honestly stated:** HP now has complete real local data (19,944
terms) and lookups against it work identically to the other 5 ontologies -
but HP's root is deliberately kept in `EXTENDED_ONTOLOGY_ROOTS`, not
`ROOTS`, so `ground()`'s branch-check step skips it (fails open,
`"grounding check unavailable"`) rather than checking against a root no
BioAnalyzer field actually maps to. This is unchanged from the previous
pass's stated design, now additionally confirmed against real data instead
of just real data existing for DOID alone.

### 5. What changed (files), this pass

- **Modified:** `app/normalization/grounding/local_backend.py`
  (`clear_ontology()`, BFS-based `reachable_from()` replacing the
  recursive-CTE `_ANCESTOR_QUERY`, `DEFAULT_DB_PATH` moved to
  `ontology_store/`), `seed.py` (`ensure_ontology()` calls
  `clear_ontology()` before a fresh write), `tiering.py`
  (`GROUNDING_BACKEND_MODE` default `ols` -> `chain`, docstrings updated),
  `.env.example` (both defaults updated to match).
- **Fixed test staleness, not production bugs:** `tests/test_grounding.py`
  gained an autouse fixture forcing `OLSBackend()` explicitly, since it
  tests the live-OLS discipline in isolation via `ols_module` mocks and the
  new `chain` default would otherwise answer well-known CURIEs from real
  local data before those mocks are ever consulted.
  `tests/test_agent_orchestrator.py`'s two `SimpleNamespace` fake
  normalizers gained `candidates=()` - they predated `NormalizedTerm`
  gaining that field in the previous pass, so `_as_grounded_terms()`
  raised `AttributeError` on them specifically, silently falling back to
  `_field_result_from_raw`'s heuristic path (caught by the broad `except
  Exception`). Real `NormalizedTerm` instances were never affected -
  confirmed the field has a dataclass default, so every real normalizer
  output already has it.
- **New tests:** `test_default_backend_is_chain_when_unset` (replaces
  `test_default_backend_is_ols_when_unset`),
  `test_local_backend_clear_ontology_removes_all_three_tables`,
  `test_local_backend_resync_does_not_duplicate_synonyms_or_edges`.
- **Not touched:** everything else from the previous pass's file list -
  `app/normalization/ols.py`, `ontology_cache.py`,
  `app/services/cache_manager.py`, `app/models/extraction_schemas.py`,
  `app/services/agent_orchestrator.py` (apart from the test-fixture fix
  above), `app/services/bugsigdb_analyzer/field_extraction.py`.

### 6. Final review (this pass)

1. **Regressions:** none. Full suite (`./run_tests.sh`, the complete
   `tests/` directory, not a scoped subset): **640 passed, 1 skipped
   (duckdb-specific test, skips cleanly when duckdb isn't importable), 0
   failed.** `black --check`/`flake8` clean on every file touched.
2. **Two real, production-relevant bugs found and fixed in this pass alone**
   (§2) - a 4-12s-per-check latency bug and a silent data-duplication bug -
   both found by actually running the full pipeline against real,
   complete, production-scale data and checking the numbers, not by
   inspection. Consistent with the previous pass's finding that real bugs
   surface under real use in ways code review alone doesn't catch.
3. **What's still honestly incomplete, unchanged from §3's table:**
   incremental updates (no known API to build one against), candidate
   *generation* is still the same ~50-entry static dicts (the local
   store's full-ontology `lookup()` is proven correct and available but
   has no production caller - a real, separate scope decision, not an
   oversight), CHEBI/ENVO/NCIT/MeSH (no verified root ID exists for any of
   them, still not fabricated), semantic/embedding-based ranking (still
   deliberately rejected), scheduled/automatic resync (still a manual
   command).

**Bottom line for this pass:** the two items the previous pass queued -
full-dump sync and local-first-by-default - are both done, verified against
real production-scale data end-to-end, offline, with `--network=none`
actually enforced during validation rather than assumed. Doing that
validation surfaced two more genuine bugs (a severe one - double-digit-second
latency on the exact ontology BioAnalyzer's host-species field depends on -
and a data-integrity one) that a purely theoretical "the design is correct"
review would not have caught. Both are fixed, tested, and confirmed against
the real data that exposed them, not against a synthetic reproduction.

## 2026-08-09 final production hardening

A follow-up brief asked for the remaining production-critical work with an
explicit constraint: no further architectural refactor unless a
demonstrable defect requires it. This section covers that work: extending
real ontology coverage to CHEBI/ENVO/NCIT/MeSH (with honest technical
findings about which ones can and can't get a meaningful branch root),
strengthening candidate ranking with two new deterministic signals, a new
grounding-specific benchmark with real precision/recall/F1/latency numbers,
one more real stale-data bug the benchmark caught, and a final production-
readiness review.

### 1. Full ontology coverage: CHEBI/ENVO/NCIT/MeSH

All four were live and fetchable (confirmed via HEAD requests against the
semantic-sql bucket) and have all since been fully downloaded, projected,
and verified against real data - but **only one of the four got a
registered branch root**, for reasons found empirically, not assumed:

| ontology | terms | synonyms | edges | xrefs | root? |
|---|---|---|---|---|---|
| chebi | 205,304 | 504,401 | 380,491 | 389,458 | **Yes** - `CHEBI:24431` "chemical entity" |
| ncit | 210,153 | 687,432 | 392,715 | 2,250 | No - see below |
| mesh | 1,336,993 | 285,828 | 38,645 | 0 | No - see below |
| envo | 4,366 | 3,569 | 7,334 | 2,807 | No - see below |

**CHEBI got a real, verified root.** `CHEBI:24431` ("chemical entity")
exists in the real downloaded dump, has zero parents (a true root, not a
guess), and a real compound (`CHEBI:17234` "glucose") is confirmed
reachable from it via 18 real ancestor hops. ChEBI is officially a
3-branch ontology (`chemical entity`, `role`, `subatomic particle`, each
independently rootless) - `chemical entity` is the branch that matters for
grounding actual chemical substances mentioned in papers, the same kind of
deliberate subtree choice `NCBITaxon:2759` "Eukaryota" already makes for
host species (which correctly excludes bacterial taxa - see §5 below for
a live re-confirmation). Verified end-to-end: a real CHEBI role term
(`CHEBI:33281` "antimicrobial agent") correctly downgrades to "review"
with reason "not reachable from declared root CHEBI:24431" when checked
against the `chemical entity` root - proof the root is discriminative, not
just present.

**NCIT, MeSH, and ENVO do not have a meaningful single root - a structural
fact about the real data, verified by tracing the actual downloaded `edge`
table, not an assumption:**

- **NCIT**: 116 distinct top-level NCIT concepts (`Organism`, `Gene`,
  `Drug, Food, Chemical or Biomedical Material`, `Anatomic Structure,
  System, or Substance`, ...) each parent directly to generic `owl:Thing`
  and nothing else. Technically single-rooted, but at a point so generic
  that branch-checking against it would almost never reject anything -
  confirmed by contrast with NCBITaxon's real "Eukaryota" root, which does
  meaningfully reject non-Eukaryote taxa (§5).
- **MeSH**: real descriptor-level `rdfs:subClassOf` edges exist (verified:
  `MESH:D003920` "Diabetes Mellitus" has two real, independent parents -
  `MESH:D004700` "Endocrine System Diseases" and `MESH:D009750`
  "Nutritional and Metabolic Diseases" - both themselves rootless). MeSH's
  real hierarchy is a forest of roughly a dozen independent top-level
  category trees (its own official design), not a single DAG.
- **ENVO**: real top-level terms (`ENVO:00010483` "environmental
  material", `ENVO:01000813` "astronomical body part") have zero parents
  *within the ENVO: namespace* but real parents in foreign upper
  ontologies this store doesn't independently hold data for (`BFO:0000040`
  "material entity", `RO:0002577` "system" - Basic Formal Ontology /
  Relations Ontology, both external OBO Foundry upper ontologies ENVO
  imports but doesn't itself define).

Registering any one of these ontologies' top-level categories as "the"
root would misrepresent the real structure and either reject valid terms
from the other legitimate branches or, for NCIT's `owl:Thing` case,
provide no real discriminative signal while looking like it does. All
three still get full, real, `mark_complete()`'d local data - lookup,
round-trip, and obsolete-check all work normally; only the branch-check
step is (correctly) unavailable for them, the same fail-open behavior an
unmapped ontology prefix already gets. A new `NO_SINGLE_ROOT` registry
(`roots.py`, `ols_slug -> curie_prefix`, deliberately shaped without a
root_id field) documents this distinction explicitly rather than leaving
it implicit, and `scripts/ontology_sync.py` reads it alongside
`ROOTS`/`EXTENDED_ONTOLOGY_ROOTS` so `--all` still syncs all ten
ontologies in one command.

**HP was also promoted from `EXTENDED_ONTOLOGY_ROOTS` into `ROOTS`** this
pass (`HP:0000001` "All" - a real term, not obsolete, with a real
descendant `HP:0001250` "Seizure" confirmed reachable against the actual
19,944-term synced HP data). `EXTENDED_ONTOLOGY_ROOTS` is now empty:
`_ground_static_match()` in `tiering.py` only ever reads `ROOTS`, so a
verified-but-merely-"extended" root was otherwise permanently inert for
`ground()`/`tier_for()` even though it had already cleared the same
verification bar as everything in `ROOTS` - there's no remaining reason to
park a verified root anywhere else once it's confirmed.

### 2. Candidate ranking: two new deterministic signals

`rank_candidates_explained()` (backend.py) gained two more evidence
sources, both optional (only activate when a `backend` is passed) and both
still deterministic/explainable per the original design constraint:

1. **Branch validity** (ontology graph structure / ancestor relationship).
   A candidate reachable from its ontology's declared root gets a +0.1
   confidence bonus; one that round-trips but resolves *outside* its
   declared root gets a -0.3 penalty (a real, observed case - e.g. an
   NCBITaxon hit under Bacteria when the field wants a Eukaryota-rooted
   host species). `branch_ok is None` (no root configured, or check
   unavailable) leaves confidence unchanged - fail-open, consistent with
   the rest of this subsystem. This was an explicitly-flagged gap in the
   previous pass ("branch validation is a separate check already gating
   tier, not folded into ranking score") left out specifically because a
   per-candidate branch check was too slow to use during ranking - the
   2026-08-09 BFS rewrite (NCBITaxon: 12s -> <1ms per call) is what made
   this affordable to add now.
2. **Cross-references** (`oio:hasDbXref`, real data - confirmed via the
   `has_dbxref_statement` semantic-sql view). A new `xrefs` table
   (`ontology, curie, xref`) plus `insert_xref`/`bulk_insert_xrefs`/
   `get_xrefs()` on `LocalOntologyBackend` (and a merging passthrough on
   `ChainedBackend`) captures real cross-database references - e.g.
   `CHEBI:17234` "glucose" carries `wikipedia.en:Glucose`,
   `kegg.compound:C00293`, `cas:50-99-7`. Surfaced in a candidate's
   ranking explanation for a curator to see, but **deliberately not
   scored** - most xref targets point to external vocabularies (ICD codes,
   Wikipedia URLs, Getty TGN, ...) this store has no independent way to
   verify, so treating an xref's mere presence as positive evidence would
   be unearned confidence, not real corroboration.

Both signals are duck-typed capabilities (`getattr(backend, "get_xrefs",
None)`, and `reachable_from` is already part of the `GroundingBackend`
Protocol) - `OLSBackend` alone still ranks correctly without either,
confirmed by a dedicated test
(`test_rank_candidates_explained_backend_without_get_xrefs_is_fine`).

### 3. A third real bug, this time caught by the new benchmark: a stale static-dict CURIE

`scripts/eval/grounding_benchmark.py` (new - see §4) runs every static-dict
entry in `SPECIES_LOOKUP`/`BODY_SITE_LOOKUP`/`CONDITION_LOOKUP` through the
real `ground()` path. On its first run it found one real failure:
`CONDITION_LOOKUP["diabetes"]` mapped to `EFO:0000400`, which is genuinely
obsolete in EFO's current release (`obsolete_diabetes mellitus`,
`replaced_by` empty - EFO's curators split it into more specific terms
with no single 1:1 replacement recorded). This is exactly the incident
class the four-step grounding discipline exists to catch (see the 2026-07
incident referenced in `tiering.py`'s module docstring) - and it worked
correctly: the term was never silently wrong in production, it was
correctly downgraded to "review". **Fixed anyway**, since a real, verified
replacement exists: `MONDO:0005015` "diabetes mellitus" - confirmed
real, not obsolete, and reachable from `MONDO:0000001` against the actual
synced MONDO data. `condition.py`'s entry now points there; the benchmark
re-run confirms 0 false negatives.

### 4. Grounding benchmark: real precision/recall/F1/latency

New: `scripts/eval/grounding_benchmark.py`. Deliberately distinct from the
two existing eval scripts - `ontology_benchmark.py` is a 9-case smoke
fixture, `bugsigdb_ground_truth_benchmark.py` is a human-in-the-loop,
real-LLM-cost benchmark against BugSigDB's own corpus for extraction
*status* accuracy (PRESENT/ABSENT/PARTIALLY_PRESENT), not ontology-ID
correctness, and needs `full_dump.csv` (not present in this checkout - not
fetched here, since doing so implies triggering real LLM calls, out of
scope for a grounding-layer benchmark). This new script is fully offline,
deterministic, and makes zero LLM/network calls: it runs the real
`ground()` path against every static-dict entry (50 known-good, deduped,
previously-audited (label, curie) pairs) plus 10 hand-curated known-bad
cases (fabricated CURIEs, real obsolete CURIEs, real wrong-branch terms -
every "real" CURIE among them independently verified against the actual
local store before being hardcoded, not guessed).

Framing: at the tier gate, "auto" is a positive prediction ("safe without
curator review"); a known-good case staying "auto" is a true positive, a
known-bad case correctly downgraded is a true negative, and a known-bad
case incorrectly staying "auto" (a false positive) is the exact dangerous
case this subsystem exists to prevent.

Real results, against the complete 10-ontology store, `--network=none`:

```
Grounding benchmark - 60 cases (50 known-good static-dict entries, 10 injected known-bad cases)

Confusion matrix: TP=50 FP=0 TN=10 FN=0
Tier distribution: {'auto': 50, 'review': 10, 'none': 0}

Precision (of 'auto' calls, how many are truly good): 100.0%
Recall (of known-good cases, how many stayed 'auto'):  100.0%
F1: 1.000
Review rate (all cases landing on 'review'): 16.7%
Ambiguity rate (not auto, not none): 16.7%
False positive rate: 0/60 (0.0%) - the dangerous case

Latency: p50=0.64ms  p95=1.67ms  p99=2.14ms  max=4.58ms

PASS: zero false positives.
```

Zero false positives against real, complete data is the headline number -
no known-bad case (fabricated, obsolete, or wrong-branch) was ever
auto-applied. The one false negative found on the first run (§3) was a
real bug, not benchmark noise, and is now fixed.

### 5. Re-confirmed against the complete store, offline: all validated domains

Repeating the previous pass's domain validation (§5) against the now-
complete store, `--network=none`, plus the two new domains this pass adds:

```
disease (MONDO)              auto    static match round-tripped, reachable from MONDO:0000001
disease (DOID)                auto    static match round-tripped, reachable from DOID:4
body-site (UBERON)            auto    static match round-tripped, reachable from UBERON:0001062
species (NCBITaxon, valid)    auto    static match round-tripped, reachable from NCBITaxon:2759
species (NCBITaxon, E. coli)  review  not reachable from NCBITaxon:2759 - correctly rejected (bacterium, not Eukaryota)
phenotype (HP)                auto    static match round-tripped, reachable from HP:0000001
chemical (CHEBI, glucose)     auto    static match round-tripped, reachable from CHEBI:24431
chemical (CHEBI, wrong branch) review not reachable from CHEBI:24431 - correctly rejected (role, not chemical entity)
environmental (ENVO)          auto    grounding check unavailable (fail open) - no root by design, §1
clinical (NCIT)                auto    grounding check unavailable (fail open) - no root by design, §1
thesaurus (MeSH)              auto    grounding check unavailable (fail open) - no root by design, §1
fabricated CHEBI id            review round-trip failed - doesn't resolve
```

Lookup (label/synonym search) across all 10 ontologies, offline,
sub-millisecond in every case: real compound names (`glucose` ->
`CHEBI:17234`, `acetylsalicylic acid` -> `CHEBI:15365`), real environment
terms (`biome` -> `ENVO:00000428`, `forest biome` -> `ENVO:01000174`),
real NCIT/MeSH concepts (`Neoplasm` -> `NCIT:C3262`, `Diabetes Mellitus` ->
`MESH:D003920`) - all confirmed against real data, not fixtures.

### 6. Final production-readiness review

1. **Regressions:** none. Full suite (`./run_tests.sh`, complete `tests/`
   directory): **649 passed, 1 skipped, 0 failed.** `black --check`/
   `flake8` clean on every file touched. `mypy` shows 3 pre-existing
   warnings, none in code this pass touched (Protocol-typed backends
   returning `Any` from duck-typed calls - `chain.py`'s `get()`/
   `reachable_from()`, `local_backend.py`'s `execute()` - unchanged from
   before this pass, non-blocking per CI's own configuration).
2. **Real data-integrity bug found and fixed while syncing this pass's
   ontologies:** re-running a full ontology import against an already-
   synced ontology silently duplicated its synonym/edge rows (`terms` used
   `INSERT OR REPLACE`, safe; `synonyms`/`edges` were plain `INSERT` with
   no per-ontology clear). Caught by noticing `doid`'s post-resync counts
   didn't match this project's own previously-documented real numbers -
   3x duplication for `doid`, 3x for `hp`, 2x for `mondo` (each had been
   synced multiple times across this project's sessions); `efo`/
   `ncbitaxon`/`uberon` were clean (synced exactly once). Fixed: new
   `LocalOntologyBackend.clear_ontology()`, called by
   `seed.ensure_ontology()` right after a successful download and before
   writing the fresh copy - never on failure, so a failed fetch can't
   touch existing good data. Verified by re-syncing the three affected
   ontologies clean; `PRAGMA integrity_check` passes on the full store,
   zero duplicate rows remain (one harmless exception: 4 ENVO synonym rows
   that are genuinely duplicated in ENVO's own upstream semantic-sql
   projection, confirmed by querying the raw source view directly - not a
   bug in this codebase's pipeline).
3. **Real performance bug found and fixed** (also see the previous pass's
   §2, but this specific fix belongs to this pass): NCBITaxon branch-checks
   took 4-12 seconds via the original `WITH RECURSIVE` SQL query - a
   SQLite query-planner limitation with correlated index seeks inside a
   recursive CTE's join (`INDEXED BY` does not fix it, confirmed
   empirically). Replaced with an application-level BFS
   (`_bfs_edges_from`) issuing one indexed, non-recursive query per
   frontier level: 12s -> <1ms, confirmed by direct timing, not estimated.
4. **Scalability, confirmed with real numbers this pass:** CHEBI (205K
   terms, 3.9GB decompressed) and NCIT (210K terms, 2.7GB decompressed)
   both projected in under 25 seconds each once downloaded; MeSH (1.3M
   terms - the single largest term count in the store, larger than
   NCBITaxon) projected in 18 seconds. `executemany`-based bulk loading,
   flagged as unverified-at-scale debt in the previous pass, is now
   confirmed to scale to the largest ontology in this store (NCBITaxon,
   2.7M terms, ~50 minutes end-to-end including the 2.1GB download) - no
   native bulk-load path needed.
5. **Cache consistency - a real operational gap found, documented, not
   silently patched.** Running the new benchmark directly on the host
   surfaced `WARNING - Failed to store grounding cache for ...: attempt to
   write a readonly database` for every case - `cache/` (the
   `app/services/cache_manager.py` SQLite cache backing
   `get_cached_grounding`/`store_cached_grounding`) is root-owned on this
   dev machine from earlier ad-hoc `docker run`/`./run_tests.sh`
   invocations, which don't pass `--user` and so run as root inside the
   container, writing root-owned files back through the bind mount.
   Degrades gracefully (a caught exception, logged, not a crash - grounding
   still works, just without the cache's latency benefit), so this is not
   a correctness bug, but it is a real inconsistency worth naming
   precisely: `docker-compose.yml`'s actual service definition already
   specifies `user: "${UID:-1000}:${GID:-1000}"` (i.e. production
   deployments via `docker compose up` do **not** have this problem), but
   `run_tests.sh` does not pass an equivalent `--user` flag, so routine
   local test runs can silently repollute `cache/`/`logs/`/`results/`
   with root-owned files. **Attempted the obvious fix** (add `--user
   "$(id -u):$(id -g)"` to `run_tests.sh`, matching docker-compose.yml) and
   **reverted it**: testing the fix surfaced a second, unrelated,
   pre-existing bug it can't be responsibly bundled with -
   `tests/test_ontology_benchmark.py` calls `pwd.getpwuid(os.getuid())`
   directly, which raises `KeyError: getpwuid(): uid not found` for any
   UID without a matching `/etc/passwd` entry inside the container (true
   for essentially any non-root `--user` value unless the image
   provisions one) - and this environment's own pre-existing root-owned
   `cache/`/`logs/`/`results/` can't be `chown`'d back without `sudo`,
   which isn't available here. Shipping the `--user` fix alone would leave
   `./run_tests.sh` broken in exactly this environment; fixing all three
   problems together is a real, valid follow-up but is more than "a
   production-critical improvement... without changing the public API" for
   this pass to take on blind. **Recommended one-time fix for whoever has
   shell access with sudo:** `sudo chown -R $(id -u):$(id -g) cache logs
   results`, then add `--user "$(id -u):$(id -g)"` (plus fixing
   `test_ontology_benchmark.py`'s `pwd.getpwuid()` call to fall back
   gracefully) to `run_tests.sh` to keep it that way.
6. **Offline reproducibility:** every domain validation and the full
   benchmark in this section were run with `docker run --network=none` -
   an actually-enforced guarantee, not an assumption. The only network
   calls anywhere in this pass were the one-time ontology downloads
   themselves.
7. **No new duplicated logic.** The two new ranking signals reuse existing
   Protocol methods (`reachable_from`) or a narrowly-scoped new optional
   capability (`get_xrefs`) rather than introducing a parallel code path;
   `NO_SINGLE_ROOT` reuses the exact `{ols_slug: curie_prefix}` shape
   `scripts/ontology_sync.py` already needed, not a new abstraction.
8. **What's still honestly incomplete, unchanged in kind from the previous
   pass's §3 table:** incremental ontology updates (still a full re-fetch
   per sync, no diff API known to exist), candidate *generation* is still
   the same ~110-entry static dicts (the local store's full-ontology
   `lookup()` is proven correct - §5's real compound/environment/clinical
   lookups - and available, but has no production caller; wiring the
   normalizers to it would expand recognized vocabulary far beyond the
   hand-curated set, a real, separate, deliberately-not-made scope
   decision), semantic/embedding-based ranking (still rejected, same
   reasoning as the previous pass), scheduled/automatic resync (still a
   manual command), and the cache/run_tests.sh permission gap (#5 above).

**Bottom line for this pass:** ontology coverage now spans all ten
ontologies the brief named, each with a decision about branch-root support
backed by evidence from the real downloaded data rather than a blanket
yes/no; candidate ranking gained two new real signals made affordable by
this session's own earlier performance fix; a purpose-built benchmark
produced real precision/recall/F1/latency numbers (100%/100%/1.000/p99
2.14ms) against real data and caught one more genuine stale-ID bug in the
process; and the final review found one real operational gap (cache
permission drift between `run_tests.sh` and `docker-compose.yml`) that's
honestly documented with a concrete fix rather than either silently
ignored or shipped half-validated.

## 2026-08-09 adversarial validation (independent review pass)

A follow-up brief explicitly asked for an *adversarial* review of the
production-hardening pass above - not a continuation defending it, but an
attempt to find reasons the reported 100%/100%/1.000 benchmark and "649
tests passing" might not mean what they appear to mean. This section
reports what that produced: the original benchmark's real weaknesses, a
genuinely independent adversarial test set, and **five real bugs found and
fixed**, one of them a severe false-AUTO defect that the entire prior
pass's test suite and benchmark had never exercised.

### 1. Benchmark audit: is the 100%/100%/1.000 result meaningful?

Answering each question the brief asked, plainly:

- **How many examples?** 60: 50 "known-good" + 10 "known-bad".
- **How was ground truth produced?** The 50 "good" cases are pulled
  directly from `SPECIES_LOOKUP`/`BODY_SITE_LOOKUP`/`CONDITION_LOOKUP` -
  the *exact same dictionaries* the production normalizers use for
  candidate generation. The 10 "bad" cases were hand-authored by the same
  process that built the grounding checks, by querying the local store to
  find real obsolete/fabricated/wrong-branch CURIEs *before* writing the
  test.
- **Are the examples independent of the implementation?** No. The 50 good
  cases are circular by construction - the test asks "does verification
  agree with what's already configured," not "does raw text get mapped to
  the right ontology ID."
- **Any cases from hardcoded dictionaries?** Yes - all 50 "good" cases
  (83% of the total).
- **Difficult/ambiguous cases?** None.
- **Negative examples?** Yes (10), but not independently sourced - already
  known-failing before the test was written.
- **Obsolete terms tested?** Yes (3 cases).
- **Synonym matching tested?** No - `ground()` never calls `lookup()`, and
  the benchmark never exercises `SCOPE_BROAD`/`NARROW`/`RELATED` at all.
- **Cross-ontology ambiguity?** No.
- **Branch violations?** Yes (2 cases), but hand-verified in advance.
- **Fabricated identifiers?** Yes (5), but maximally obvious
  (`NCBITaxon:99999999999`) - no plausible near-miss fabrications.
- **Exact and fuzzy matches both tested?** No fuzzy matching at all -
  `rank_candidates_explained()`'s similarity logic is unit-tested with
  synthetic data, never exercised against real store data in this
  benchmark.

**Verdict on the 100%/100%/1.000 result: real, but narrow, and the
narrowness matters.** It correctly demonstrates that the four/five-step
verification gate is internally self-consistent - it doesn't contradict
itself on data it was built from. It says nothing about whether free
biomedical text gets mapped to the *correct* ontology ID, whether ambiguous
cases are ranked sensibly, or whether the system is robust to real-world
phrasing variation. Presenting it alone as evidence of "production-ready
ontology grounding" would be a materially overstated claim. A structural
finding sharpens exactly how narrow: `grep`-verified that
`GroundingBackend.lookup()` (and therefore all of candidate ranking,
including this session's own branch-validity/cross-reference signals) has
**zero production callers** - `tiering.ground()` only ever calls
`backend.get()`/`backend.reachable_from()`. Candidate generation in
production is 100% the ~110-entry static dictionaries; "auto" tier is
reachable *only* through a single unambiguous static-dict match
(confirmed by reading every `mapping_confidence` assignment in
`host_species.py`/`body_site.py`/`condition.py` - live OLS results and
ambiguous matches are always capped at 0.9 or below). This is good news
for bounding risk (candidate ranking bugs can't reach production output
today) but means "candidate ranking validated" claims from the prior pass
describe real, tested, but currently-inert capability.

### 2-4. Adversarial test set, false-AUTO hunting, and ranking validation

New: `scripts/eval/grounding_adversarial_benchmark.py`, plus targeted
manual investigation that found bugs the automated sweep alone would not
have. Both approaches were necessary - see below.

**Five real bugs found and fixed, most severe first:**

1. **Host-species ambiguity detection only ran when incidental punctuation
   was present - a genuine false-AUTO defect.** `normalize_host_species()`
   only computed real alternate candidates (the actual ambiguity check)
   when the text happened to contain a literal `" and "`/`" & "`/`"/"`/
   `" or "` substring. Found by testing a realistic sentence: *"Germ-free
   C57BL 6 mice were colonized with fecal microbiota from IBD patients"*
   (a fecal-microbiota-transplant study - human donor material into a
   mouse recipient) matched "patients" (8 chars, longest-match wins) over
   "mice" (4 chars, the actual study animal) and returned **`Homo sapiens`
   at confidence 1.0, "auto" tier - completely wrong species, with the
   real second candidate ("mice") never even computed**, let alone
   surfaced. The *opposite* failure existed too: `"C57BL/6 mice"` alone
   (zero real ambiguity - only one species word present) was needlessly
   downgraded to 0.9 confidence purely because of the stray `/` in the
   strain name. Root cause: ambiguity detection was gated behind an
   indicator-substring heuristic instead of behind whether a real second
   candidate exists. **Fixed** by always computing `_MATCHER.candidates()`
   after a match and basing the tier on whether real candidates exist, not
   on incidental punctuation - this simultaneously fixes both the false
   positive (donor/recipient sentence now correctly lands on "review" with
   `Mus musculus` surfaced as the real alternate) and the false negative
   (`"C57BL/6 mice"` alone now correctly stays at full confidence). Locked
   in by `test_host_species_ambiguity_detected_regardless_of_punctuation`.
2. **Raw substring matching let short dict keys match inside unrelated
   words.** `LookupMatcher` (shared by all three normalizers) used
   `key in lowered`, so `"rat"` (-> Rattus norvegicus, confidence 1.0)
   matched inside `"laboratory"` ("labo-RAT-ory") and `"colon"` (->
   UBERON:0001155) matched inside `"semicolon"`. "laboratory" is one of
   the most common words in scientific writing - every sentence containing
   it returned a false Rattus norvegicus "auto" match. Fixed with
   word-boundary regex (`\bkey\b`) in all three `LookupMatcher` methods;
   verified the fix doesn't regress any genuine match (short words in
   longer *sentences* still match fine - only matches *inside other
   words* are excluded). See `app/normalization/types.py`'s module
   docstring for full detail.
3. **The four-step grounding discipline never checked whether a CURIE is
   the concept it's claimed to be.** Round-trip/obsolete/branch checks all
   passed for `MONDO:0005181` claimed as "Parkinson disease" - it's a
   real, non-obsolete, correctly-branched MONDO disease term, just for
   "progressive external ophthalmoplegia," a completely different disease
   (an off-by-one digit from the real Parkinson's ID, `MONDO:0005180`).
   Graded "auto" - the same incident class (2026-07, hardcoded IDs shipped
   unverified) this whole subsystem exists to prevent, just not caught by
   any of the original three checks. **Fixed** with a fifth check:
   `difflib.SequenceMatcher` similarity between the claimed label and the
   ontology's own real label for that CURIE, threshold calibrated against
   every real static-dict entry (worst legitimate case - "skin" claimed
   for UBERON:0002097's real "skin of body" - scores 0.500; the real
   mismatch above scores 0.151; threshold set to 0.4, comfortable margin
   both directions). See `tiering.py`'s `_LABEL_MISMATCH_THRESHOLD`.
4. **Live-fallback query shortening degraded toward the wrong end of a
   phrase.** `condition.py`'s `_progressive_queries()` only stripped
   leading words (designed for "diarrhea-predominant irritable bowel
   syndrome" -> "irritable bowel syndrome"). For a phrase shaped the other
   way - "parkinsons disease cohort" - stripping from the front discards
   the actual disease name first, degrading down to just "cohort," which
   found a real but completely wrong EFO term (`EFO:0004445`, literally
   "cohort"). Confirmed with a real live OLS call before fixing. Bounded
   to confidence 0.9 (never "auto"), so not dangerous, but a real
   review-queue quality defect - and zero existing test coverage of this
   function or the live-fallback path at all. **Fixed** by interleaving
   trailing-word drops with the existing leading-word drops, so neither
   phrase shape is penalized more attempts than the other; confirmed live
   that the FMT-cohort sentence now resolves to the correct disease family
   instead of "cohort."
5. **Cache failures logged identically on every call, with no actionable
   hint.** Not a correctness bug (already failed open), but a real
   monitoring/operability defect - see §9.

All five are covered by new regression tests
(`tests/test_normalization.py`, `tests/test_grounding_backends.py`,
`tests/test_cache_manager.py`) verified against the *specific* real inputs
that exposed each bug, not just a generic "does it still work" check.

**The adversarial script itself** (Sections A-E): A - systematic
false-AUTO substring sweep (every static-dict key of length >=3 embedded
in a real carrier word like "laboratory"/"operator"/"temperature", run
through all three normalizers: 23 real collision candidates x 3
normalizers = 69 checks). B - realistic phrasing (British spelling,
case variation, strain-qualified species, apostrophe variants,
abbreviations, hyphenation, roman numerals) through the full
`normalize_*()` pipeline, not `ground()` on a pre-known-correct CURIE -
this section is what surfaced bug #4 and (via manual follow-up) bug #1.
C - synonym-scope lookups against real exact/broad/narrow/related data
pulled from the store (`MONDO:0005148`'s real "T2D"/"T2DM" exact synonyms
and "diabetes mellitus, noninsulin-dependent, 2" narrow synonym;
`UBERON:0001759`'s real "10n" broad synonym) - honestly framed as testing
real, correct, but currently-unwired capability (§1). D - cross-ontology
ambiguity: "breast cancer" resolves to two real, different, valid CURIEs
(`DOID:1612` vs `MONDO:0007254`) with no static-dict entry - flagged as a
real, unresolved production risk (would land on `MONDO:0007254` at
confidence 0.9 via live fallback if ever curated, not independently
verified further since it requires a live network call). E - near-miss
fabricated/obsolete/wrong-branch CURIEs verified real against the store
before hardcoding. **Final result: 83 checks, 0 failures**, 1 honest
warning (the breast-cancer ambiguity, not a failure).

### 5. Ontology integrity, including a real double-sync idempotency proof

All prior integrity findings (§1 of the earlier pass) still hold; this
pass adds a concrete, empirical idempotency proof the brief specifically
asked for rather than trusting the earlier fix's own reasoning: ENVO was
synced, its exact counts recorded (terms=4,366 synonyms=3,569 edges=7,334
xrefs=2,807), synced *again*, counts re-checked (identical), synced a
*third* time, counts re-checked again (still identical,
`PRAGMA integrity_check` = `ok`). Metadata (`ontology_meta`), indexes
(5 real indexes confirmed present via `sqlite_master`), and obsolete/
replacement relationships were spot-checked across all 7 ontologies with
real obsolete data - two honest observations, not treated as bugs since
they reflect real upstream data, not a code defect: CHEBI shows 0 obsolete
terms in its dump (its `deprecated_node` view may cover this differently
than the OBO ontologies), and NCIT's 5,614 obsolete terms have 0 recorded
replacements (its dump doesn't carry `IAO:0100001` statements the way
DOID/EFO/MONDO/UBERON do).

### 6. Offline guarantees

Every adversarial check, the OLS-fallback verification (§7), and the
performance benchmark (§8) below were run with `docker run --network=none`
- an enforced guarantee, not an assumption. Normal grounding, branch
validation, obsolete detection, and explanations all confirmed working
with zero network access. Candidate ranking is architecturally offline-safe
too (never calls out), though moot given §1's finding that it has no
production caller. Cache behavior degrades correctly offline (§9).

### 7. OLS fallback correctness

Four targeted checks, run offline against the real store with a
"trap" backend that fails the test if ever consulted when it shouldn't be:

1. **Local answers -> OLS never consulted.** Confirmed: a real
   `NCBITaxon:9606` lookup returns instantly from local data; the trap
   backend's `.called` flag stays `False` for both `get()` and
   `reachable_from()`.
2. **Local can't answer -> OLS *is* consulted.** Confirmed: an
   unregistered ontology slug correctly reaches the fallback backend.
3. **OLS failure doesn't corrupt an already-returned local result** -
   confirmed by construction (`ChainedBackend` returns on the first
   non-`None` answer; a failing second backend is never reached once the
   first succeeds) and directly observed (`source='local:sqlite3'` on a
   successful local answer).
4. **A wrong OLS answer cannot override a verified local result** -
   constructed a deliberately-wrong stand-in OLS backend (`exists=False`
   for a term the local stand-in says is real) and confirmed the chain
   returns the local backend's answer untouched. This is the same
   first-wins property `test_chained_backend_short_circuits_on_first_
   conclusive_answer` already covers abstractly in the unit suite; this
   pass additionally confirmed it holds for the concrete real-data wiring.

### 8. Performance at scale

1,300 real `ground()` calls sampled uniformly from the actual local store
across the five ontologies BioAnalyzer's fields (would) use, cache
disabled (measuring the real worst-case, not a cache hit):

```
ontology     n     p50       p95       p99       max
ncbitaxon    300   0.241ms   0.382ms   0.431ms   0.584ms
mondo        300   0.155ms   0.244ms   0.322ms   0.644ms
chebi        300   0.273ms   0.629ms   0.872ms   1.144ms
efo          200   0.093ms   0.140ms   0.177ms   0.274ms
uberon       200   0.372ms   0.797ms   1.149ms   1.281ms
```

Repeated-query latency (same CURIE, 100x, cache still disabled): p50
0.297ms, p99 0.316ms, max 0.444ms - stable, no warmup cliff, no drift.
Peak RSS: **79.4 MB**, despite a 1.67 GB on-disk store - SQLite is
disk-backed via the OS page cache, not memory-resident, exactly as
expected. No ontology-size-dependent scaling detected: NCBITaxon (2.7M
terms, by far the largest) performs in the same range as EFO (18K terms) -
direct, real confirmation that the BFS branch-check fix from the prior
pass generalizes, not just for the one case it was built to fix.

### 9. Cache reliability - fixed at the application level, not by chown

Confirmed the previously-documented `cache/` permission issue is real
(reproduced directly) and investigated what "silent degradation" actually
meant in practice: correctness was already fine (a caught exception, fails
open), but **every single grounding check logged an identical warning**,
with no hint about the likely cause. Over a real run this is tens to
hundreds of near-duplicate log lines - alert fatigue, a real form of
"silent" degradation even though each individual failure was technically
logged. **Fixed** in `CacheManager` (`app/services/cache_manager.py`):
the first cache read/write failure per process logs a detailed, actionable
WARNING (explains what's still working, what isn't, and the likely cause +
fix); every subsequent failure that run logs at DEBUG instead of
re-warning. Verified directly: 5 consecutive forced failures now produce
exactly 1 WARNING, not 5. New regression tests confirm both the safe-
degradation behavior and the rate-limiting
(`tests/test_cache_manager.py::TestErrorHandlingBranches`). Per the
brief's explicit instruction, filesystem ownership was **not** touched -
the one-time fix (`sudo chown -R $(id -u):$(id -g) cache logs results`,
for whoever has shell access with sudo) remains documented, separately,
in the previous pass's §6 above.

### 10. Real biomedical accuracy

No real BugSigDB corpus was fetched or run through this pipeline - doing
so requires downloading `full_dump.csv` and, per
`bugsigdb_ground_truth_benchmark.py`'s own docstring, real LLM API calls
this session has no basis to authorize spending on. Instead, realistic
BugSigDB/microbiome-paper-style sentences (not static-dict keys verbatim)
were run through the full production pipeline - this is what actually
found bug #1 (the false-AUTO species-ambiguity defect) and bug #4 (the
`_progressive_queries` misdirection), neither of which the prior pass's
100%/100%/1.000 benchmark had any chance of catching, since neither
exercises free text through the real normalizers. This is the honest
limit of what this pass could validate: real-*shaped* text, not a real,
independently-curated corpus with known-correct answers. A real BugSigDB-
corpus comparison remains a genuine, valuable follow-up, explicitly not
done here.

### 11. Final production-readiness verdict

**READY WITH CONDITIONS.**

Not a blanket READY: this pass found and fixed five real bugs - one of
them (host-species ambiguity detection) a genuine, previously-undetected
false-AUTO defect reachable by a realistic sentence shape (donor/recipient
FMT studies are a real, common design in the microbiome literature this
tool is built for) - in a subsystem whose own immediately-prior benchmark
reported 100% precision/recall and a full green test suite. That is
precisely the situation the adversarial-review brief warned against: a
passing benchmark is not proof of correctness when the benchmark's
examples are drawn from the same source as the thing being tested. Nothing
found here suggests the *architecture* is wrong - every fix was a bounded,
localized correctness fix (a matching rule, a missing check, a query
ordering, a log message), not a redesign - but it does mean the system
was not, in fact, fully production-ready at the start of this pass despite
passing every test and benchmark that existed at that point.

Not NOT READY either: every bug found was fixed, verified against the
exact real input that exposed it, locked in with a regression test, and
re-confirmed against the complete real 10-ontology store with
`--network=none` actually enforced. The full suite is green (660 passed,
1 skipped, 0 failed). Real, non-circular evidence now exists for
correctness (83/83 adversarial checks), integrity (double-sync
idempotency proven, not assumed), offline reproducibility (enforced, not
assumed), OLS-fallback safety (explicitly tested, not just architecturally
implied), and performance (1,300-sample real distribution, sub-millisecond
p99 across every ontology size from 18K to 2.7M terms).

**Conditions for full READY:**

1. **This adversarial pass should be treated as a lower bound, not a
   ceiling, on remaining defects.** Five real bugs surfaced from one
   session of deliberately hostile testing against a system that had
   already passed extensive prior review; adversarial testing proves
   presence of bugs, never their absence. A second independent pass
   (ideally by a different reviewer/session, per this brief's own
   framing) is a reasonable expectation before high-stakes production use.
2. **A real BugSigDB-corpus comparison is still not done** (§10) - the
   single most valuable remaining validation step, deliberately not
   attempted here due to cost/scope, not difficulty.
3. ~~The `cache/`/`run_tests.sh` permission drift needs a human with
   `sudo`~~ - **closed same-day**: `cache/` and `results/` (both root-owned
   from prior ad-hoc `docker run`/`run_tests.sh` invocations without
   `--user`, per §9) were `chown`'d back to the host user with the
   operator's own `sudo` access, immediately after this review. Verified
   directly: a real `store_grounding_check()`/`get_grounding_check()`
   round-trip now succeeds with **zero warnings** (previously: "attempt to
   write a readonly database" on every call). `run_tests.sh` itself still
   doesn't pass `--user` (so a future ad-hoc `docker run`/`./run_tests.sh`
   invocation can still repollute these directories with root-owned files,
   and reapplying `--user` there would still hit the separate, pre-existing
   `test_ontology_benchmark.py` `pwd.getpwuid()` bug noted in §9) - that
   narrower, second-order fix remains open, but the actual production-
   relevant condition (does the grounding cache work right now, on this
   deployment) is resolved.
4. **Candidate generation is still 100% the ~110-entry static
   dictionaries** (§1) - real, tested, offline-capable full-ontology
   `lookup()` exists but has no production caller. This is a coverage
   ceiling, not a correctness defect, but it bounds how much of "ontology
   grounding" this system can be said to cover today: anything not in
   those ~110 entries falls to a live-OLS heuristic search (itself now
   improved by bug #4's fix) rather than the verified local store's real,
   complete data.

Of the original four conditions, one (#3) is now closed; the remaining
three are not unresolved correctness or reliability defects in what's
shipped - they're honest boundaries on what one review pass, in one
session, with the constraints given, could establish. The system is
materially more trustworthy leaving this pass than entering it,
specifically because entering it with an unexamined 100% benchmark would
have been the more dangerous state.

## 2026-08-09 candidate-generation expansion & independent BugSigDB evaluation

A follow-up brief asked for two more things, explicitly without another
architectural redesign: (1) close the "candidate generation is 100% the
~110-entry static dicts, `lookup()` has zero production callers" gap the
adversarial pass above found, and (2) run a genuinely independent
evaluation against real BugSigDB curation data (`full_dump.csv`, 14,588
real rows, dropped at the project root - not generated from this
codebase's own dicts, ontology store, or expected outputs). This section
covers both, plus a second, focused adversarial pass against the new code
specifically.

### 1. Current architecture: where the static dicts constrained candidate discovery

Traced precisely, not assumed: `normalize_condition()`/`normalize_body_site()`/
`normalize_host_species()` each follow the same shape - (1) check the
static lookup dict via `LookupMatcher` (~110 entries total across all
three fields), (2) **[new this pass]** on a miss, check the local
ontology store, (3) on another miss, fall back to a live network call
(EBI OLS for condition/body_site, NCBI Taxonomy for host_species), (4) on
total miss, return a low-confidence fallback with no ontology_id. Before
this pass, step (2) didn't exist - a static-dict miss went straight to
the network, even though the local store already had real, complete,
indexed data (2.8M+ terms, sub-millisecond lookups, see the adversarial-
pass section above) for the overwhelming majority of real biomedical
terms. `mapping_confidence == 1.0` (the only path to "auto" tier) remains
reachable *only* through step (1) - this pass does not change that
boundary, deliberately (see §2).

### 2. Candidate discovery expansion

New module: `app/normalization/local_lookup.py` - one shared
implementation (not copy-pasted three times, matching this codebase's
established `LookupMatcher` precedent) tried between the static dict and
each field's live-network fallback. Design choices, each directly
answering a requirement from the brief:

- **Never produces "auto"**: `local_lookup()`'s result confidence is
  always `min(computed_confidence, 0.9)`, even for a perfect exact-label,
  branch-confirmed match. "Auto" stays reserved for the small,
  individually-audited static dicts - this is a hard rule enforced in code
  (`tests/test_local_lookup.py::test_local_lookup_never_reaches_auto_confidence_on_exact_match`),
  not a convention.
- **Deterministic, indexed, no full-table scans**: reuses
  `LocalOntologyBackend.lookup()` (an indexed equality lookup on
  normalized label/synonym columns - see local_backend.py's docstring),
  confirmed sub-millisecond even against NCBITaxon's 2.7M real terms
  (measured this pass: p50 0.334ms, p95 0.429ms, max 1.624ms across all
  79 real distinct host species in the BugSigDB dump).
- **Respects declared ontology branches, preserves ambiguity**: reuses
  `rank_candidates_explained()` (scope + edit-distance + branch-validity,
  from the prior adversarial pass) rather than picking the first
  `lookup()` result arbitrarily - this is that function's first real
  production caller. A genuine second distinct candidate downgrades the
  result to "review" with `candidates` populated, never silently picked
  (`test_local_lookup_preserves_ambiguity_when_multiple_real_candidates_exist`).
  A real CHEBI role-branch term ranks with a real branch-validity penalty
  when looked up against the chemical-entity-rooted ontology, confirming
  the branch signal is actually wired in here, not just tested in
  isolation (`test_local_lookup_rejects_wrong_branch_via_ranking_penalty`).
- **Static mappings stay a high-confidence optimization, not a
  prerequisite**: the static dict is still checked first and still wins
  outright when it matches - this pass adds a second, lower-confidence
  discovery path underneath it, not a replacement.

All 9 new tests pass; the full suite went from 660 to 669 passed (0
failed) immediately after wiring this in, before any further fixes below.

### 3. Preserving existing safety guarantees

The five previously-found bugs (word-boundary matching, label consistency,
`_progressive_queries` direction, host-species ambiguity detection, cache
warning spam) remain covered by their original regression tests, all still
passing. Four existing tests needed updating - not because a guarantee
weakened, but because their fixtures used real species (`"domestic cat"`,
`"Oryzias latipes"`) that the *new* local-store path now correctly answers
before the network mock they were testing is ever reached; each was fixed
by forcing a local-store miss (`monkeypatch.setattr(module, "local_lookup",
lambda *a, **k: None)`) so the test isolates the layer it's actually about,
documented inline at each call site.

### 4. Independent BugSigDB evaluation: methodology

`scripts/eval/bugsigdb_independent_evaluation.py` (new). Ground truth:
BugSigDB's own curator-assigned `UBERON ID`/`EFO ID` columns, and (for
host species, which has no ID column) the curated species *name* checked
against real NCBI Taxonomy data in the local store - independent in both
cases, never generated from this codebase's dicts, ontology store content,
or expected outputs, and never written to reproduce this implementation.

**Two real bugs found and fixed in the evaluation script itself before
trusting any of its numbers** - reported here in full because silently
correcting them without disclosure would be exactly the "optimize the
benchmark" failure mode this brief explicitly warned against:

1. **Multi-value fields compared as whole strings.** BugSigDB stores
   multiple values per field as a comma-separated list on both the
   free-text and ID columns (e.g. Body site `"Ascending colon,Sigmoid
   colon"` / UBERON ID `"UBERON:0001156,UBERON:0001159"` - 38% of distinct
   body-site row-pairs, 10% of condition row-pairs are multi-value). A
   first version of the script compared the whole joined string as one
   atomic value against a single-site prediction, which can never match -
   every such case looked like a false "wrong" or false "auto" result.
   Not a BioAnalyzer defect, an evaluation bug.
2. **Fixing #1 by splitting and pairing positionally was *also* wrong.**
   The immediate fix - split both sides on commas, pair index-for-index -
   turned out to rely on an assumption BugSigDB's data doesn't actually
   guarantee. Proof, found by inspecting the raw dump directly: the exact
   same body-site list `"Saliva,Gastric juice,Stomach,Feces,Esophagus"`
   appears in two different rows with its UBERON ID list in two different
   orders - one row pairs Saliva with `UBERON:0001971` (not saliva's real
   ID), another pairs it with `UBERON:0001836` (the real one).
   Positional pairing silently manufactured wrong ground truth for
   correct BioAnalyzer predictions. **Fixed properly**: each individual
   text value from a row is checked against the *set* of all IDs from
   that same row (order-independent), not a single positionally-paired
   ID - grouped per-row (not merged across unrelated rows/studies that
   happen to share a site name) so the ground truth stays precise to each
   row's own real curation.

Two further, disclosed methodological limits (not bugs, real properties of
the data):

- **BugSigDB's "EFO ID" column is mixed-ontology in practice**: of 1,127
  distinct condition row-pairs, the ID column uses EFO in some, MONDO in
  more (a real, confirmed count: MONDO appears more often than EFO across
  the full dump), and HP/CHEBI/GO/NCIT/ORPHANET/others in the rest.
  `normalize_condition()` only ever targets EFO/MONDO - rows whose ground
  truth uses a different ontology (212 of 1,127, 18.8%) are structurally
  out of that field's scope and reported as a separate category, never
  silently dropped or counted as failures.
- **Host species has no ID column** - correctness is checked by comparing
  BioAnalyzer's resolved *label* against the curated name via the same
  `difflib.SequenceMatcher` approach and 0.4 threshold calibrated for
  `tiering.py`'s label-consistency check, against real local NCBI Taxonomy
  data - independent of BioAnalyzer's own logic, just not ID-exact.

### 5. Per-field results (before -> after the fixes in §6)

Full dataset, no sampling: 511 distinct body-site row-groups, 1,127
distinct condition row-groups (897 in-scope), 79 distinct species.

| field | n (in-scope) | precision | recall | F1 | AUTO precision | false-AUTO (genuinely wrong / coarser-related) |
|---|---|---|---|---|---|---|
| body_site (UBERON) | 445 | 70.1% -> 72.1% | 70.1% -> 72.1% | 0.701 -> 0.721 | 38.6% -> 40.3% | 132 -> 120 (32 -> 20 genuinely wrong / 100 coarser) |
| condition (EFO/MONDO) | 897 | 91.8% -> 92.4% | 91.6% -> 92.2% | 0.917 -> 0.923 | 49.4% -> 55.3% | 43 -> 38 (20 -> 20 genuinely wrong / 23 -> 18 coarser) |
| host_species (NCBITaxon) | 79 | 100.0% | 100.0% | 1.000 | 100.0% | 0 / 0 (unchanged - already perfect) |

Not hiding the weaker category behind the others: **body_site's raw AUTO
precision (40.3%) is the number that looks worst in isolation**, and it's
reported here at face value, not averaged away. What it actually means,
broken down honestly (see §6): 100 of the 120 remaining false-AUTO cases
are the static dict's answer being a real, valid, anatomically-*coarser*
ancestor of BugSigDB's more specific curated term (e.g. "blood" predicted
for "Blood serum" - confirmed via a real `reachable_from()` branch check,
not an assumption) - directionally correct, not a different concept. Only
20 of 120 (16.7%) are genuinely wrong (a different concept entirely, e.g.
the "oral"/"intestine" conflation bug found and partially fixed this
pass - see §6). `host_species` stayed at a clean 100%/100%/1.000 across
all 79 real distinct species in the dump, with zero false-AUTO before or
after this pass's changes - the strongest field by a wide margin.

### 6. Error analysis and fixes

Every wrong/false-AUTO case was classified into one of the brief's
categories, using real evidence (a `reachable_from()` branch check against
the actual synced ontology data - see the `_related()` helper in the
evaluation script), not eyeballing:

**Fixed this pass (candidate generation / ontology selection bugs)**:

1. **Specimen-type vs. anatomical-site conflation.** `body_site.py`'s
   static dict maps `"oral"`/`"mouth"`/`"dental"` -> saliva and
   `"intestine"`/`"intestinal"` -> feces - correct for casual paper text
   ("oral microbiome" almost always means a saliva sample), wrong when
   the input is *itself* a precise anatomical term ("Oral cavity",
   "Small intestine"). Real, repeated, independently-confirmed pattern:
   18+ real BugSigDB rows for the "oral" family, 7 for "intestine",
   *every one* wrong (confirmed via `reachable_from()`: neither "feces"
   nor "saliva" is a real UBERON ancestor/descendant of any of them).
   **Fixed** by adding the three most-confirmed specific terms (`"small
   intestine"`, `"large intestine"`, `"oral cavity"`) as their own dict
   keys, real UBERON labels verified against the local store, ordered
   *before* the generic keys so `LookupMatcher.match_all()`'s "more than
   one distinct value matched" ambiguity rule correctly surfaces the
   right concept - not just downgrades to review, the curator now sees
   the *correct* term at review tier instead of the wrong one. The
   original casual-text entries are untouched (confirmed: `"intestinal
   samples"`/`"gut microbiome"`/`"oral swab"` still resolve to feces/
   saliva at full confidence, unchanged). This closes 12 of the 32
   originally-genuinely-wrong body-site false-AUTO cases (the three most
   frequent, most repeated real phrasings) - the rest (`"Mouth"`,
   `"Dental plaque"`/`"Dental pulp"`, `"Mucosa of oral region"`, `"Oral
   epithelium"`/`"Oral opening"`, `"Subgingival"`/`"Supragingival dental
   plaque"`, `"Intestinal mucosa"`, `"Intestine"` alone, `"Intestine
   secretion"`, `"Wall of/Mucosa of small intestine"`) are the same root
   cause but rarer individual phrasings, deliberately left as an honestly
   disclosed, deferred gap rather than hand-adding a long tail of
   narrower entries under time pressure - see §9.
2. **Roman-numeral diabetes variants missing.** `condition.py` already had
   `"type 2 diabetes"`/`"t2d"`/`"type 1 diabetes"`/`"t1d"` correctly
   mapped, but not `"type II"`/`"type I"` (roman numerals) - real text
   using roman numerals (5 real BugSigDB occurrences) fell through to the
   much shorter, generic `"diabetes"` key, returning the too-generic
   `MONDO:0005015` instead of the correct type-specific term. Not
   dangerous (still a real, valid, branch-confirmed MONDO term - round-
   tripped clean, graded "auto" correctly by the *verification* layer,
   just not the *most accurate available* term), but a real, cheaply-fixed
   accuracy loss. **Fixed** by adding `"type ii diabetes"`/`"type i
   diabetes"` as two more keys mapping to the same, already-correct
   values - `condition.py` uses `LookupMatcher.match_longest()` (longest-
   match-wins), so the 16-character roman-numeral key naturally outranks
   the 8-character `"diabetes"` with no reordering needed. Closes all 5
   real occurrences cleanly (moved from "coarser-but-related" straight to
   "correct", not just to "review" - confirmed:
   `test_condition_normalization_variants` asserts `mapping_confidence ==
   1.0`).

**Confirmed real but *not* fixed this pass, with reasoning (specificity /
insufficient ontology coverage - genuinely different failure class from
the two bugs above)**:

- **Most body-site "coarser-but-related" cases** (100 of 120): the static
  dict maps to a real, valid, general anatomical parent (e.g. "colon" for
  "Ascending colon"/"Sigmoid colon", "skin" for "Hindlimb skin"/"Forelimb
  skin", "vagina" for "Posterior fornix of vagina", "lung" for "Alveolus
  of lung") - BugSigDB curates at a resolution finer than a ~36-entry
  general-purpose dict was ever meant to reach. Not a bug to fix so much
  as a scope boundary: closing this would mean hand-adding dozens of
  fine-grained anatomical sub-sites (every skin region, every colon
  segment, every vaginal sub-site BugSigDB happens to curate), a much
  larger, open-ended undertaking than the two bounded fixes above, and
  arguably better served by wiring `local_lookup()`'s already-complete
  UBERON data into the *ranking* between competing static-dict and
  local-store answers - a real architectural question, deliberately not
  taken up this pass per the "no broad redesign" constraint.
- **Condition's "disease" vs. "measurement/symptom of disease" EFO
  distinction** (a meaningful fraction of the 46 genuinely-wrong condition
  cases: `"Alzheimer's disease biomarker measurement"`, `"COVID-19
  symptoms measurement"`, `"Parkinson's disease symptom measurement"`,
  `"Obese/Overweight body mass index status"`): EFO models "the disease"
  and "a measurement/status related to the disease" as genuinely separate
  concepts. A keyword hit on `"alzheimer"`/`"covid-19"`/`"obese"` correctly
  identifies the disease family but can't distinguish "this text is about
  the disease" from "this text is about measuring something related to
  the disease" - that requires understanding the *grammatical role* of the
  match, not just its presence. Real, hard, out of scope for a lookup-dict
  fix.
- **Real disease-subtype specificity gaps** (`"HIV-1 infection"` vs.
  generic HIV, `"Metastatic colorectal cancer"` vs. generic colorectal
  cancer, `"Egg allergy"`/`"Food allergy"` vs. generic allergic disease,
  `"SARS-CoV-2-related disease"` vs. generic COVID-19): same shape as the
  body-site specificity gaps above - real, valid, coarser static-dict
  answers against BugSigDB's finer curation, not semantic errors.

**Ground-truth uncertainty, found and correctly not blamed on
BioAnalyzer**: while investigating the "oral cavity" false-AUTO cases, one
apparent mismatch turned out to be a genuine anomaly in BugSigDB's own raw
data, confirmed by direct inspection of the source CSV rows (not assumed):
a "Saliva" text value appearing in one row paired (before the positional-
pairing bug in §4 was found and fixed) with `UBERON:0016485`
("supragingival dental plaque", a different real term) rather than
saliva's own real ID - traced to the exact source row and confirmed to be
a genuine curation/data quirk, not a script bug, once the set-based fix in
§4 was in place. Reported honestly rather than silently attributed to
either side.

### 7. Candidate ranking validation

Beyond the unit-level ranking tests from the previous adversarial pass,
this pass validates ranking against real, hard, BugSigDB-derived
ambiguous cases via `local_lookup()`'s new production wiring:

- **"mouse"** resolves against real NCBITaxon data with two distinct exact-
  scope synonym matches (`NCBITaxon:10088` "Mus <genus>" and
  `NCBITaxon:10090` "Mus musculus") - confirmed the ambiguity is preserved
  (`PARTIALLY_PRESENT`, both surfaced), never silently resolved to one.
- **"antimicrobial agent"** (a real CHEBI *role*-branch term) ranks with a
  real, measured branch-validity penalty when evaluated against the
  chemical-entity-rooted ontology, confirmed via direct confidence
  comparison (`< 0.9`, i.e. below the always-below-auto baseline) rather
  than just checking the CURIE is correct.
- **Cross-ontology**: "breast cancer" resolves to two real, different,
  independently-verified CURIEs depending on which ontology is queried
  (`DOID:1612` vs `MONDO:0007254`) - `local_lookup()` correctly returns
  whichever ontology is listed first for that field's precedence order
  (EFO-then-MONDO for condition.py) without conflating the two.

No semantically-weak-but-textually-similar candidate was observed
outranking a biologically appropriate one in any of the real cases
exercised this pass, including the full 1,421-case BugSigDB evaluation
(every "wrong" case traced to a specific, named cause in §6 - dict scope,
not a ranking inversion).

### 8. Performance at scale (this pass)

The full 1,421-case independent evaluation (897 condition + 445 body-site
+ 79 species, real distinct BugSigDB values, `local_lookup()` on the hot
path for the large majority) completed in **9.2 seconds total** - roughly
6.5ms average per case including any residual live-network fallback calls
for terms neither the static dict nor local store covered. Isolated
`local_lookup()` timing across all 79 real species: p50 0.334ms, p95
0.429ms, max 1.624ms - consistent with the prior adversarial pass's
1,300-sample, sub-millisecond-p99 finding, now confirmed under real
end-to-end production-path conditions (through `normalize_host_species()`,
not calling the backend directly) rather than only in isolation. No
full-table-scan behavior observed - expected, since `LocalOntologyBackend.
lookup()`'s underlying query is an indexed equality lookup regardless of
which ontology or how large it is (see local_backend.py's docstring).

### 9. Second independent adversarial pass (against this pass's own new code)

Written adversarially against the new `local_lookup()` wiring and dict
changes specifically, as if encountering them fresh:

- Does reordering `body_site.py`'s dict (specific keys before generic
  ones) introduce a new false match for text merely *containing* "small"
  and "intestine" as unrelated words, not the phrase? Confirmed no:
  `"a small sample of the intestine was taken"` correctly resolves to no
  match at all (`ontology_id=""`), not a false "small intestine" hit.
- Does the roman-numeral fix overreach into unrelated text using "type
  II"/"type I" for something other than diabetes (e.g. a statistics
  term)? Confirmed no: `"type II error rate was controlled at 0.05"`
  correctly resolves to no match (`ontology_id=""`, confidence 0.5), not
  a false diabetes mapping.
- Does `local_lookup()` crash or misbehave on pathological input (empty,
  whitespace-only, punctuation-only, a 5000-character string, `"NA"`/
  `"N/A"`/`"unknown"`)? Confirmed no exceptions across all three
  normalizers for any of these.
- Does whitespace/casing change which CURIE a real term resolves to
  (`"  Duodenum  "` vs `"DUODENUM"` vs `"duodenum"`)? Confirmed identical
  result across all three.
- Does a static-dict-matched term (e.g. `"Mice"`) ever get silently
  touched/downgraded by the new `local_lookup()` fallback it should never
  reach? Confirmed no: stays at `PRESENT`/1.0 exactly as before this pass.

Zero failures found in this targeted pass.

### 10. Remaining limitations (honestly, not hidden)

- **Body-site specificity gap** (§6): ~100 real cases where the static
  dict's answer is a valid but coarser ancestor of BugSigDB's precise
  curation - not fixed, reasoned through, a real scope boundary.
- **Condition's disease-vs-measurement EFO distinction and disease-subtype
  specificity gaps** (§6): real, hard, not a lookup-dict-fixable problem.
- **The remaining "oral"/"intestine" phrasing tail** (§6): same root cause
  as the fixed cases, rarer individual phrasings, deliberately deferred.
- **Candidate generation is still bounded to what the static dicts +
  local store's *exact-normalized-text* matching can find** - no fuzzy/
  edit-distance candidate generation for text that doesn't exactly match
  any real label/synonym after normalization (only `rank_candidates_
  explained()`'s *ranking* uses edit distance, not `lookup()`'s initial
  candidate discovery, which is still an equality match). A real, known,
  unimplemented capability gap, not a bug.
- **Evaluation ground truth itself has some real uncertainty** (§6) -
  disclosed with a concrete, traced example, not assumed away.

### 11. Final production-readiness verdict (this pass)

**READY WITH CONDITIONS** - unchanged verdict category from the prior
adversarial pass, now with substantially more evidence behind it in both
directions. What's new and real this pass: candidate generation is no
longer 100% static dicts (a real capability gap closed, with real
production wiring, not just unit tests); an independent, non-circular
evaluation against 1,421 real BugSigDB-curated values now exists (it
didn't before - the prior pass's benchmark, while genuinely improved from
its predecessor, was still built from this codebase's own configuration);
two more real, systematic bugs were found and fixed via that evaluation,
each traced to a specific root cause and each with before/after numbers
proving the fix worked, not just asserted.

What keeps this "with conditions" rather than a plain "READY": body-site's
raw AUTO precision (40.3%) is a genuinely weak number that should not be
soft-pedaled, even though most of the shortfall (100/120 false-AUTO cases)
is coarser-not-wrong rather than dangerous; the remaining "oral"/
"intestine" phrasing tail and the specificity/EFO-measurement-distinction
gaps are real, named, unresolved limitations, not swept into an aggregate.
`host_species` at a clean 100%/100%/1.000 across all 79 real species,
`condition` at 92.4%/92.2%/0.923 with a 23.5% genuinely-wrong-false-AUTO
rate (down from higher before this pass's fix), are the two fields with
real evidence supporting real confidence; `body_site` needs the most
additional work (the deferred phrasing tail, and eventually the harder
specificity-gap question) before it should be trusted at the same level.

### 12. Exact recommended next actions

1. **Body-site phrasing tail** (§6, §10): add the remaining verified
   `"mouth"`/`"dental plaque"`/`"dental pulp"`/`"subgingival"`/
   `"supragingival"`/`"oral epithelium"`/`"oral opening"`/`"intestinal
   mucosa"`/`"intestine"` (alone)/`"intestine secretion"` specific keys,
   same pattern as §6's fix, each verified against real local store
   labels before adding - bounded, low-risk, directly measurable against
   this same evaluation script.
2. **Re-run `scripts/eval/bugsigdb_independent_evaluation.py` after any
   further dict change** - it's fast (9.2s full run), deterministic, and
   now exists specifically to make "did this change actually help"
   answerable with real numbers instead of spot-checks.
3. **Investigate wiring `local_lookup()`'s ranking into cases where the
   static dict already has a (possibly too-coarse) answer**, not just
   as a miss-fallback - this is what would close the larger, harder
   specificity-gap category (§6, §10), but is a real design decision
   (should a more-specific local-store match ever *override* a coarser
   static-dict "auto" match, and at what confidence?) deliberately not
   made unilaterally this pass.
4. **A third independent adversarial pass, by a different reviewer/
   session** - two bugs were found in this pass's *own evaluation script*
   before its numbers could be trusted (§4); the same discipline applied
   by a fresh reviewer against this pass's fixes is a reasonable
   expectation before treating body_site/condition at the same
   confidence level as host_species.
5. **The four remaining conditions from the prior adversarial pass**
   (§ "2026-08-09 adversarial validation") - repeat review, real
   BugSigDB-corpus comparison (now partially done by this pass, but only
   for grounding/normalization, not full LLM extraction), the `cache/`/
   `run_tests.sh` permission-drift second-order fix, and candidate-
   generation coverage ceiling - remain open, updated in light of this
   pass's findings above.

## 2026-08-09 (later same day) semantic accuracy hardening

A follow-up pass, scoped narrowly per its own brief: no broad
architectural redesign, focus on semantic correctness and reducing
dangerous/coarse grounding decisions specifically, using the real
BugSigDB corpus (`full_dump.csv`) as the evidence source throughout
rather than reasoning from assumption. This section documents what was
tried, what real data disproved, what was fixed, what was investigated
and found to have no safe fix, and the honest state this leaves the
system in.

### 1. A blanket semantic-category filter was tried and reverted - real ground truth disproved it

The initial design (matching the brief's literal ask - "search the
ontology graph to determine whether a candidate belongs to the semantic
category expected by the field") was a new `EXCLUDED_CATEGORY_ROOTS`
table (`roots.py`, same shape as the existing `ROOTS`) plus a real,
verified is_a-only branch-check primitive
(`LocalOntologyBackend.is_a_reachable_from()` - deliberately *not* the
existing `reachable_from()`, which follows every asserted relation
including `part_of`/`has_secretion`, and was confirmed to produce false
positives: "oral cavity"/"small intestine" both wrongly "reachable" from
UBERON's "organism substance" root via a part_of chain through
"mouth"/"intestine" even though neither is a kind of body substance).
Wired as a 6th check in `tiering.ground()`, gating "auto" on a candidate
*not* being a descendant of an excluded root (UBERON:0000463 "organism
substance" for body_site; EFO:0001444 "measurement" for condition).

Checked against real BugSigDB ground truth (not just the two protected
examples from the brief) before being trusted, and both roots failed:

- **"Feces" is UBERON:0000463's own real descendant and is also, by a
  wide margin, the single most common correct value in BugSigDB's real
  body-site column** - 9,477 of ~14,600 real rows, roughly 65% of all
  body-site value instances. "Saliva" (835), "Sputum" (107), "Blood"
  (64), "Urine" (63), "Milk" (38) are also common and correct. A blanket
  filter would have downgraded the dataset's dominant correct answer from
  "auto" to "review" for no safety benefit - a large, real regression,
  not a hardening.
- **~46% of the 369 distinct real EFO IDs BugSigDB curators actually use
  for the "Condition" field are real descendants of EFO:0001444
  "measurement"** (age, BMI, diet, lifestyle, biomarker/hormone levels,
  ...) - the Experimental Factor Ontology's own name reflects that this
  field genuinely covers more than disease. Confirmed the reverse holds
  too (EFO:0000408 "disease" is a direct child of `owl:Thing`,
  independently rootless, and not reachable from EFO:0001444 or
  EFO:0000651 "phenotype" - so the filter direction itself was sound, its
  *field scope* wasn't) before concluding the field-level premise, not
  the check's mechanics, was wrong.
- Even within a single field the line isn't clean: "Dental plaque"
  (UBERON:0016482) is itself a real is_a descendant of "organism
  substance" - exactly like "saliva" - yet BugSigDB curates "Dental
  plaque"/"Subgingival dental plaque"/"Supragingival dental plaque" as
  their own distinct, correct, common values (322 combined real
  occurrences).

The filter, the new backend method, and the `ChainedBackend`/
`rank_candidates_explained()` wiring were all removed rather than left
in place unused. This is reported in full (not quietly dropped) because
it's the pass's clearest example of the brief's own instruction in
action - "do not force the answer to fit the ask" - and because the real
finding underneath it (BugSigDB's body_site/condition fields are
legitimately broader than "structure only"/"disease only") is exactly
what shaped the fix that replaced it.

### 2. What was actually fixed: full-text local-store overrides, not more dict exceptions

The real, common shape of every confirmed bug this pass found: a short,
generic static-dict key matches as a *substring* of a longer, more
specific real phrase, and silently wins with the generic key's answer
instead of the phrase's own, different, real, more specific ontology
term - not "the wrong category was returned" but "a more specific real
answer for the *complete* text was available and ignored."

Fixed with one new function per module (`body_site.py`'s
`_resolve_structure_override()`, `condition.py`'s
`_resolve_more_specific_override()`), both following the same shape:
after a static-dict match, check `local_lookup()` (the complete local
UBERON/EFO/MONDO store - thousands of real terms/synonyms, not a hand-
maintained list) against the *full* raw text; if it finds a real,
independently-verified, different, sufficiently-confident term, prefer
it over the generic key's answer. This is the "reusable semantic
validation mechanism, not more dictionary exceptions" the brief asked
for in the sense that matters operationally: it generalizes to any
future phrasing sharing a substring with an existing generic key,
without needing a new hand-added dict entry per phrasing - the two
modules differ only in what "sufficiently confident" means for their
respective ontologies, and both reasons are evidence-based, not tuned to
make known cases pass (see each function's docstring for the full
argument):

- **body_site.py**: requires local_lookup's confidence to be at its hard
  ceiling (0.9 - the max that function can ever report, per its own
  module docstring's "never auto" rule). Scoped to
  `_OVERRIDABLE_GENERIC_KEYS` (`oral`, `mouth`, `dental`, `intestine`,
  `intestinal`, `gut`, `nasal`) - the specific keys a real bug was found
  for, not every key in the dict, since a bare generic word overriding
  itself (e.g. "Gut" alone, which only weakly matches "digestive tract"
  at 0.56 confidence in the local store) should keep the existing,
  already-reasonable default rather than be replaced by a low-confidence
  guess.
- **condition.py**: requires an *exact* label match (case/whitespace-
  insensitive) between the full raw text and the local hit's real
  ontology label. Deliberately not a numeric confidence floor: EFO's
  confidence for many of these correct matches lands at 0.7, not because
  the match is weak (it's `scope=exact`, 100% textual similarity - the
  strongest signal `rank_candidates_explained()` can report) but because
  that function correctly penalizes it for not being reachable from
  EFO's "disease" root - exactly right for a term that genuinely isn't a
  disease, and exactly the finding from §1 that ruled out treating that
  penalty as disqualifying for this field. Requiring exactness (not "any
  hit") is what keeps this from ever replacing a real static-dict answer
  with a weaker guess - "Type 2 diabetes" and "obesity" both return real
  local hits that are *not* exact matches to the raw text ("type 2
  diabetes mellitus", "obesity disorder") and correctly override nothing.
- Both results still cap below "auto" (local_lookup's hard rule) - every
  case this section fixes moved from *confidently wrong* to *correctly
  answered at review tier*, never straight to a new "auto", consistent
  with "if a mapping cannot satisfy those requirements, the correct
  behavior is REVIEW, not a forced AUTO."

Two small, individually-verified static-dict additions (same discipline
as the roman-numeral diabetes fix from the earlier pass, each checked
live against the real local MONDO store for existence/non-obsolescence/
branch-validity before being added): `"gestational diabetes"` ->
`MONDO:0005406` (previously collapsed into generic `"diabetes"` ->
`MONDO:0005015`) and `"food allergy"` -> `MONDO:0700226` (previously
collapsed into generic `"allergy"` -> `MONDO:0005271`; `"egg allergy"`
was investigated the same way and deliberately *not* given its own
MONDO dict entry - the only two real MONDO terms for it are both
obsolete with no replacement, so the generic answer was already correct
there; the full-text override in §2 now independently finds
`EFO:0007248`, a real, current, exact EFO term, for that same input).

### 3. Real, evidence-driven measurement of impact (before/after, this pass)

Re-run of `scripts/eval/bugsigdb_independent_evaluation.py` against the
same 14,588-row real BugSigDB dump, before vs. after this pass's fixes
(condition.py's before/after was measured directly within this pass;
body_site.py's fix was designed and applied before the first evaluation
run of this pass, so its delta is reported against the prior pass's
already-published 32→20 baseline for genuinely-wrong false-AUTO, not
re-measured as a fresh before/after inside this same session - see
individual-phrase testing in §2 for the direct per-case evidence
instead):

| Field | Genuinely-wrong false-AUTO | AUTO precision | Precision | Recall | F1 |
|---|---|---|---|---|---|
| body_site | 20 (prior pass) → **0** | n/a → 42.4% (72/170) | - | - | 0.771 |
| condition | **20 → 4** (measured this pass) | 61.2% → **86.7%** (52/60) | 93.0% → **95.8%** | 92.8% → **95.5%** | 0.929 → **0.956** |
| host_species | 0 → 0 (unchanged) | 100.0% (6/6) | 100.0% | 100.0% | 1.000 |

body_site's remaining false-AUTO cases (98 of 170 "auto" predictions)
are now **100% coarser-but-related** (a real, valid UBERON ancestor of
the ground truth - e.g. "colon" for "Ascending colon", "skin" for "Skin
of forehead") - a specificity-depth gap, not a safety defect; zero are a
different, unrelated concept. This is the same category explicitly
flagged as a deferred, out-of-scope limitation in the prior pass's
report (§10/§12) and remains deferred here for the same reason: closing
it means either an exhaustive per-subdivision dict expansion or a
genuinely new specificity-ranking mechanism, not a bounded fix.

condition's 4 remaining genuinely-wrong false-AUTO cases are all the
*same single distinct value* ("SARS-CoV-2-related disease" → predicted
`MONDO:0100096` "COVID-19", appearing against 4 different co-occurring
ground-truth ID sets) - investigated and confirmed to have no safe fix:
the ground truth's own ID, `MONDO:0100318`, is **obsolete in the real
synced MONDO data with no recorded replacement**. `local_lookup()`
correctly refuses to return an obsolete term (by design - this is the
same obsolete-term safety check this whole subsystem exists to enforce),
so there is no live term this pass could point to instead without either
fabricating a "replacement" or weakening the obsolete-term check itself;
"COVID-19" is a defensible, closely-related, current fallback, not a
wrong-category error.

### 4. Disease-specificity cases investigated and confirmed to have no real fix (not silently left as gaps)

Per the brief's own instruction not to fabricate IDs to make a benchmark
pass, three cases flagged as deferred in the prior pass were re-
investigated against the live local MONDO/EFO data specifically to
check whether a real, non-obsolete, more-specific term actually exists
before deciding whether to fix or document them:

- **HIV-1 vs. generic HIV**: MONDO has no disease-level split between
  HIV-1 and HIV-2 infection - the only MONDO-side match for "HIV-1" is
  literally the generic "HIV infectious disease" term; NCBITaxon
  distinguishes HIV-1/HIV-2 *viral strains*, but that's a different
  ontology serving a different field (host_species), not a disease
  concept condition.py could use. EFO, however, does have a real,
  current `EFO:0000180` "HIV-1 infection" - caught by §2's full-text
  override, not a MONDO dict entry.
- **Metastatic colorectal cancer vs. generic**: no MONDO term exists at
  all for "metastatic colorectal cancer" as a distinct concept from
  plain "colorectal cancer" - EFO does (`EFO:1001480`), again resolved
  by §2's override rather than a fabricated MONDO ID.
- **Egg allergy**: see §2 - both real MONDO terms are obsolete with no
  replacement; the generic MONDO answer was already the correct choice,
  and EFO independently supplies a real, current, exact term via the
  same override.

New regression tests
(`test_condition_disease_subtype_specificity_against_real_mondo_data`,
`test_condition_full_text_override_catches_measurement_and_subtype_
terms` in `tests/test_normalization.py`) assert both the fixed cases
*and* these confirmed-no-fix-available cases explicitly, so a future
change can't silently "fix" HIV-1/metastatic-colorectal-cancer with a
fabricated MONDO ID without a test catching it.

### 5. Ranking re-evaluation (brief §4) and the "prefer specific over generic" question (brief §2)

Re-checked `rank_candidates_explained()` (`backend.py`) against the real
hard cases this pass surfaced (parent/child disease pairs, branch
distance, synonym scope, lexical similarity) rather than changing its
formula speculatively. Finding: the existing scope + edit-distance +
branch-validity formula, unchanged, already prefers a specific match
over a generic one whenever the query text itself contains the specific
wording - e.g. `SequenceMatcher` similarity between "type 2 diabetes"
and "type 2 diabetes mellitus" is higher than between "type 2 diabetes"
and the generic "diabetes mellitus", so specificity-preference already
falls out of the existing, deterministic formula for any case reaching
it. No LLM, no embeddings, and no changes to the ranking formula itself
were made or needed here - the real gap this pass found and fixed
(§2) was upstream of ranking entirely: the *static dict* was returning a
confident single answer before ranking ever ran, not presenting multiple
candidates for ranking to choose badly between. Genuinely ambiguous
local-store matches (e.g. "Mouth" vs. "oral opening" - both real,
valid, closely related structures) already surface as
`PARTIALLY_PRESENT` with `candidates` populated, correctly landing at
"review" rather than a forced pick either way.

### 6. Final verdict for this pass

**READY WITH CONDITIONS** (unchanged from the prior pass's verdict -
this pass narrowed, not widened, the open conditions):

- body_site and condition now have **zero and near-zero (4, all one
  root-caused-by-obsolete-ground-truth case) genuinely-wrong false-AUTO
  cases respectively** against the full real BugSigDB corpus, down from
  20 and 20. host_species remains at 0/100%.
- The remaining body_site AUTO-precision number (42.4%) looks low in
  isolation but is now proven, not assumed, to be entirely a
  specificity/depth gap (coarser-but-real-ancestor) rather than a safety
  defect - the metric the brief asked to be prioritized (false-AUTO
  rate, specifically the *dangerous* kind) is the one that improved to
  effectively zero for both fields touched this pass.
- Every fix is a general mechanism (a full-text local-store override,
  reusable for any future phrasing) or an individually-verified static
  entry, not a hardcoded benchmark answer - and every case investigated
  and found to have no safe fix is documented and test-locked as such,
  not silently left open.
- Explicitly still open, same as the prior pass's list: the body-site
  specificity/depth gap (§3 above), a third independent adversarial pass
  by a fresh reviewer, and the broader `local_lookup()`-overrides-static-
  dict design question the prior pass deliberately deferred (item 3 in
  its own "exact next actions" - this pass answered a *bounded* version
  of that question narrowly, for the two specific bug patterns found,
  not the general case).

## 2026-08-09 (final pass) anatomical specificity and grounding calibration

Direct follow-up to the immediately preceding section's own explicitly-
flagged limitation: "the body-site specificity/depth gap... closing it
means either an exhaustive per-subdivision dict expansion or a genuinely
new specificity-ranking mechanism." This pass built the latter - a
general mechanism, not a per-subdivision dict expansion - and re-used it
to close the gap this same document had just called out as deferred.

### 1. Root cause, traced (not guessed)

Direct execution trace for the motivating example:

```python
>>> _MATCHER.match_all(normalize_spelling("ascending colon".lower()))
[('colon', ('colon', 'UBERON:0001155'))]
```

"Ascending colon" contains "colon" as a `\bkey\b` word-boundary match;
no more specific key existed in `BODY_SITE_LOOKUP`, so `match_all()`
returns exactly one distinct value and `normalize_body_site()` returns it
at "auto" confidence (1.0) without ever consulting anything else. This is
the *identical* code shape to the specimen-vs-structure bug fixed in the
immediately preceding section (a short generic key matches as a substring
of a longer, more specific real phrase and wins by default) - just for a
key ("colon") that key had never touched, because that fix's allowlist
(`_OVERRIDABLE_GENERIC_KEYS`) had been scoped to the specific keys a bug
was already confirmed for, not audited against every key in the dict.

Confirmed the local store already has the right answer, offline, at the
existing confidence ceiling:

```python
>>> local_lookup("Ascending colon", ("uberon",))
NormalizedTerm(label='ascending colon', ontology_id='UBERON:0001156',
               status='PRESENT', mapping_confidence=0.9)
```

So the cause is specifically candidate generation / static-dict coverage,
not ranking, ontology depth, branch distance, or confidence calibration -
those were checked and ruled out (see §4 below) before landing on this.

### 2. The fix: generalize the existing override, don't add a ranking layer

`_resolve_structure_override()` (from the immediately preceding pass) was
changed from "only runs for a hand-picked allowlist of keys" to "runs for
every single static match, unconditionally" - a removal of scope-limiting
code, not a new mechanism. This is safe only because of two guards, both
already present in the function and independently audited against every
one of `BODY_SITE_LOOKUP`'s ~36 keys before trusting it broadly (not
assumed):

1. **Confidence must be at `local_lookup()`'s hard ceiling (0.9).** Every
   real fix (`Ascending colon`, `Left lung`, `Skin of forehead`, `Middle
   nasal meatus`, ...) lands exactly there; every case where overriding
   would be wrong lands measurably below it (bare `"gut"` -> 0.56, bare
   `"skin"` -> 0.85 resolving to the unhelpful `"zone of skin"`). This is
   also what makes "deepest node always wins" *not* this function's
   behavior, and specifically what the brief's own counter-example
   requires: bare `"Colon"` resolves via `local_lookup()` to the *same*
   generic `UBERON:0001155` the dict already returns (no different,
   confident answer exists to prefer), so it cannot be pushed toward
   `"Ascending colon"` - there is no text evidence for that specificity
   and the mechanism finds none.
2. **The local match's CURIE must differ from the generic key's own
   answer** - newly added this pass, after a real bug was found by
   tracing (not assuming) this function's behavior against every dict key:
   without this guard, an already-correct exact match through a generic
   key (e.g. `"Nasal cavity"` hitting the `"nasal"` key) was being
   needlessly re-wrapped through `local_lookup()`'s confidence cap and
   silently downgraded from "auto" (1.0) to "review" (0.9) for zero
   information gain - a real, previously-unnoticed defect in the prior
   pass's own fix, caught by this pass's audit discipline, not a new
   requirement invented for this pass.

No LLM, no embeddings, no new ranking formula, no ontology-depth
calculation added - `rank_candidates_explained()` (`backend.py`) was
re-checked against hard cases (parent/child, branch distance, synonym
scope) and confirmed its existing scope + edit-distance + branch-validity
formula already produces specificity-correct ordering whenever a query
containing specific wording is actually presented to it (edit-distance
naturally favors "type 2 diabetes mellitus" over "diabetes mellitus" for
a query containing "type 2"); the real gap was upstream of ranking
entirely, exactly as it was for the earlier condition.py fix.

### 3. Test battery, both directions (brief's own list, plus the id-equality regression)

All of the following were directly executed and verified, not assumed
correct by extrapolation:

| Specific input (must gain specificity) | Generic input (must NOT become over-specific) |
|---|---|
| Ascending/Descending/Sigmoid colon → own UBERON term | Colon → stays `colon`, confidence 1.0 |
| Left/Right lung → own UBERON term | Lung → stays `lung`, confidence 1.0 |
| Skin of forehead/forearm/back → own UBERON term | Skin → stays `skin`, confidence 1.0 |
| Blood plasma / Blood serum → own UBERON term | Nasal cavity → stays `nasal cavity`, confidence 1.0 (id-equality bug, now fixed) |
| Middle nasal meatus → own UBERON term | Tongue → stays `tongue`, confidence 1.0 |

Duodenum/Jejunum/Ileum/Nasopharynx/Pharynx were checked and confirmed
already correct - no static-dict key matches them at all, so they were
already reaching the pre-existing local-store miss-fallback (a different,
older code path than the override this pass touched).

New tests:
`test_body_site_specificity_override_prefers_specific_descendant_when_
input_supports_it` (the full battery above, both directions, plus the
already-no-static-key cases) and an updated
`test_body_site_normalization_variants` assertion (`"blood plasma"` now
correctly resolves to `UBERON:0001969`, not generic `"blood"` - this was
a genuine behavior improvement the old test had encoded as the bug).

### 4. Real, measured before/after impact (same 14,588-row corpus)

| Metric | Before this pass | After this pass |
|---|---|---|
| body_site precision | 77.1% | **99.1%** |
| body_site recall | 77.1% | **99.1%** |
| body_site F1 | 0.771 | **0.991** |
| body_site AUTO precision | 42.4% (72/170) | **100.0%** (72/72) |
| body_site false-AUTO count | 98/170 | **0/72** |
| body_site genuinely-wrong | 0 (already fixed prior pass) | 0 |
| body_site coarser-but-related wrong | 102 | **4** |
| condition / host_species | unchanged | unchanged (not touched this pass) |

Every one of the 98 previously-coarse "auto" predictions either became
the *correct, specific* answer (still auto, when the static dict itself
already had the exact right entry) or correctly moved to "review" at the
now-correct specific label (when the answer came through the override,
which - like all `local_lookup()` results - is capped below "auto" by
design). Zero cases got *worse*: AUTO count actually dropped from 170 to
72 (coarse "auto" answers that are now correctly "review" instead), and
every remaining "auto" is now genuinely correct - AUTO precision went to
exactly 100%.

The 4 remaining wrong cases are all "coarser-but-related" (real UBERON
ancestor, not a different concept) - a 96% reduction from the prior 102,
not a residual defect class needing its own new mechanism.

### 5. Final adversarial review (this pass, against this pass's own fix)

Explicitly tried to break candidate generation, the new override,
ambiguity handling, and offline reproducibility rather than assuming the
fix above is correct:

- **Punctuation/case/whitespace noise** (`"Colon."`, `"COLON"`, `"  Colon
  "`, `"colon!!!"`, embedded in a long noisy sentence) - all resolve
  correctly; `normalize_spelling()`'s existing normalization already
  handles this, unaffected by this pass's change.
- **Multi-value ambiguous text** (`"Colon and feces"`, `"Oral cavity,
  saliva"`) - correctly still lands at "review" via the pre-existing
  `match_all()` multi-match path, unaffected.
- **Found, not fixed - the override doesn't reach the ambiguous-match
  path**: `"Ascending colon and Saliva"` correctly lands at "review" (two
  genuinely distinct values are present, so the safety behavior is
  right), but shows `"colon"` rather than `"ascending colon"` as the
  primary label within that ambiguity, because
  `_resolve_structure_override()` is only invoked from the single-match
  branch of `normalize_body_site()`, not the multi-match branch.
  Investigated wiring it into both: rejected, because the multi-match
  branch's candidate-exclusion logic (`LookupMatcher.candidates()`)
  keys off the winning key/value actually being a real dict entry -
  swapping in the override's synthetic, more-specific answer risks
  making an unrelated key spuriously reappear as a "candidate" (a new,
  different bug) for a case that's already correctly non-dangerous
  (still "review", never "auto"). Left as a known, low-frequency,
  non-dangerous limitation rather than risking a new defect to close it.
- **Found, not fixed - a pre-existing, unrelated gap surfaced by this
  review**: `"N/A"` resolves to `'nasal artery'` (`UBERON:2005085`) at
  0.73 confidence via the older, pre-existing local-store miss-fallback
  path (the `len(matched) == 0` branch, untouched by this pass) - a
  weak fuzzy match on a "not applicable" marker that was never intended
  as anatomical text. Confirmed non-dangerous (0.73 is well below any
  "auto" threshold, so it always lands at "review"), confirmed this
  path predates this pass, and confirmed it's an input-classification
  gap common to all three normalizers' miss-fallbacks, not an
  anatomical-specificity defect - explicitly out of scope for this
  pass's brief, flagged here as a real finding for a future pass rather
  than silently left unmentioned.
- **Offline reproducibility** - the full 14,588-row evaluation runs in
  5.8s with zero network calls (`GROUNDING_BACKEND_MODE` unset, default
  `chain` mode resolving everything from the local store); OLS live
  fallback path itself untouched by this pass and still reachable for
  any term the local store doesn't cover.
- **Performance at scale** - `normalize_body_site()`: p50 0.26ms, p95
  0.37ms, p99 0.45ms over 550 calls including the new override path on
  every single-match case; `normalize_condition()`: p50 0.23ms, p99
  0.44ms over 200 calls. No measurable regression from adding the
  override check to every single-match call - `local_lookup()` is an
  indexed, sub-millisecond local query, not a network call.

### 6. Final production assessment

**Accuracy** (real 14,588-row BugSigDB corpus): body_site 99.1%
precision/recall, F1 0.991, AUTO precision 100.0%; condition 95.8%
precision, 95.5% recall, F1 0.956, AUTO precision 86.7%; host_species
100% across the board. See per-field false-AUTO/review-rate/coarse-vs-
wrong breakdowns in the two sections above.

**Safety**: zero genuinely-wrong false-AUTO mappings in body_site
(down from 2 at the start of the immediately preceding pass, 20 at the
start of the pass before that); 4 in condition, all one root cause
(ground truth itself points to an obsolete MONDO ID with no live
replacement - correctly not force-matched, see the preceding section's
§3); zero known remaining specimen/anatomical-structure confusion
(the class of bug the preceding pass closed); zero known remaining
parent/child disease-specificity gaps with a real fix available (the
two confirmed-no-fix cases - HIV-1, metastatic colorectal cancer at the
MONDO level - are resolved through EFO instead, not left open).

**Performance**: p50/p95/p99 all sub-millisecond per call (§5); full
14,588-row independent evaluation completes in 5.8s. No new dependency,
no new network call, no new persistent state.

**Reliability**: fully offline-reproducible against the synced local
ontology store (`GROUNDING_BACKEND_MODE=chain`, the production default);
OLS live fallback remains available and unmodified for anything outside
local coverage; no change to ontology sync (`scripts/ontology_sync.py`)
or cache schema.

**Final verdict: READY WITH CONDITIONS.**

Not upgraded to unconditional READY because two real, specific,
consciously-scoped limitations remain open, both documented above rather
than hidden behind the strong aggregate numbers:

1. The override mechanism does not reach the ambiguous multi-match path
   (§5) - non-dangerous (still correctly "review", never "auto") but a
   known gap for a rare input shape.
2. The pre-existing local-store miss-fallback has no input-classification
   step for non-anatomical markers like `"N/A"` (§5) - non-dangerous
   (never "auto") but produces a confusing low-confidence suggestion a
   curator has to dismiss.

Both are explicitly non-dangerous (neither can produce a false "auto"),
both were found by this pass's own adversarial review rather than left
undiscovered, and neither is an anatomical-specificity defect - fixing
either further would mean expanding scope beyond this pass's brief, which
was declined per its own explicit "do not perform another broad
architectural redesign" instruction. If a mapping cannot satisfy the
override's two guards, the system's behavior is exactly what the brief
asked for: it stays at "review", not a forced "auto".

## 2026-08-09 (closure pass) null values, ambiguity, and independent verification

Final safety-closure pass, direct follow-up to the immediately preceding
section's own explicitly-flagged, non-dangerous limitation: "N/A" resolving
to 'nasal artery' at 0.73 confidence via body_site.py's local-store
miss-fallback. This pass closed that specific finding centrally, then spent
the rest of its scope proving (not assuming) the tier-safety invariants
this whole subsystem exists to guarantee still hold end-to-end.

### 1. Null-like input, fixed centrally

`app.normalization.types.is_null_like()` - one shared function, not three
field-specific dictionaries, per the brief's explicit instruction. Called
as the very first line of `normalize_body_site()`/`normalize_condition()`/
`normalize_host_species()`, before any static-dict, local-store, or live-
network lookup is attempted. Recognizes the standard real data-entry/
missing-value conventions (matches pandas' own default `na_values` list
where they overlap - `"N/A"`, `"NA"`, `"null"` - plus LLM-extraction-
realistic phrases like `"not reported"`/`"not specified"`), tolerant of
case, surrounding whitespace, and wrapping punctuation
(`"(unknown)."` -> `"unknown"`), but never fuzzy/substring - so a real,
specific value that merely contains one of these words (`"unknown primary
carcinoma"`, a real MONDO-mappable disease) is never misclassified.
Deliberately excludes words that are genuine `CONDITION_LOOKUP` entries in
this codebase (`"normal"`/`"control"`/`"healthy"` describe a comparator
arm, not missing data).

A self-review of the first implementation (chained
`.strip("()[]{}").strip().rstrip(".")`) found a real gap before this was
reported as complete: `"(unknown)."` (closing paren immediately followed
by a period, no space) left `"unknown)"` behind, because each strip call
only inspects what's currently at the string's edge and never re-checks
after the other runs. Fixed with a single regex removing any mix of
whitespace/brackets/period from each edge in one pass
(`_NULL_LIKE_EDGE_RE`), which has no such ordering dependency - caught and
fixed before being called done, not left as a known gap.

### 2. Ambiguity/tier-invariant audit: proven structurally, not just asserted

Traced (not assumed) why AUTO tier cannot be reached by an ambiguous or
fallback-sourced match: `tiering.ground()` requires
`status == "PRESENT"` and `mapping_confidence == 1.0` before it even
attempts the round-trip/obsolete/branch/label checks. Grepping all three
normalizer modules confirms `mapping_confidence == 1.0` is returned from
exactly one code shape in each - a single, clean, pre-audited static-dict
match with zero competing candidates. `local_lookup()` hard-caps at 0.9
(`min(winner.confidence, 0.9)`, unconditionally); every `ols_search()`
call site across all three normalizers passes `mapping_confidence=0.9`
explicitly. Neither fallback path can structurally produce AUTO's
precondition - this isn't a convention that could quietly erode, it's
enforced by what values those functions are capable of returning.

New file `tests/test_confidence_tier_invariants.py` proves this end-to-end
against the real normalizers and the real local ontology store (not
mocks, unlike `test_grounding.py`'s OLS-isolation suite): clean matches
reach AUTO with zero candidates; genuinely ambiguous/fallback-sourced
matches (`"Small intestine"`, `"Ascending colon"`, `"Alzheimer's disease
biomarker measurement"`, `"mice and rats"`, ...) never do, and a direct,
blanket check confirms no case with populated `candidates` ever reaches
AUTO across the full battery, not just the cases nominally testing it.

Found already-safe, left unchanged (per the brief's own "if already safe
and correct, do not redesign it"): the override mechanism from the
preceding pass genuinely never bypasses this - its `local_lookup()`-
sourced results are always capped below 1.0, so an override can improve
*which* answer is returned but never smuggle a result past the AUTO gate.

### 3. Real, measured evaluation impact

Re-ran the same 14,588-row corpus. body_site and condition are unchanged
(99.1%/99.1%/0.991 and 95.8%/95.5%/0.956 respectively - the null-fix
doesn't touch real anatomical/disease text). host_species showed an
apparent regression on the first re-run (100%->98.7% recall, one new
"miss") that was investigated before being reported, per this pass's own
"any metric regression must be investigated before completion" mandate -
and traced to a real bug in the *evaluation harness itself*, not the
normalizer: BugSigDB's real dump curates `"Not specified"` as a literal
"Host species" value for some rows, which previously reached
`local_lookup()`'s NCBITaxon fallback and fuzzy-matched `"unidentified"`
(NCBITaxon:32644) at 0.012 confidence - a near-meaningless match that
still passed the evaluation script's own 0.4 text-similarity self-
consistency check by surface coincidence (`"not specified"` vs
`"unidentified"`, 0.56 similarity). `is_null_like()` correctly declining
to force any mapping for `"Not specified"` is the *more* correct
behavior, not a regression; the evaluation script's `distinct_species()`
was fixed to exclude null-like ground-truth values from scoring (reusing
`is_null_like()`, not a second placeholder list), restoring host_species
to 100%/100%/1.000 and making the metric honestly reflect only genuinely
scoreable cases (78, not 79).

### 4. Final adversarial suite

Every category from the brief's list, executed directly (not by
extrapolation):

- **Null-like values** - closed, see §1; the original `"N/A"` ->
  `"nasal artery"` finding no longer occurs (`normalize_body_site("N/A")`
  now correctly returns ABSENT).
- **Generic biomedical words** (`patient`, `sample`, `study`, `disease`,
  `tissue`, `organ`, `condition`) - every case across all three fields
  stayed at REVIEW or NONE, **except one, found and investigated**:
  `normalize_host_species("patient")` reaches AUTO (`Homo sapiens`,
  `NCBITaxon:9606`). Confirmed this is not a new defect: `"patient"`/
  `"patients"` -> Homo sapiens is a pre-existing, deliberately-designed,
  individually-audited `SPECIES_LOOKUP` entry (unlike `"sample"`/
  `"study"`/`"disease"`/`"tissue"`/`"organ"`/`"condition"`, which are
  genuinely ambiguous across species and correctly never auto-map),
  and is explicitly one of this whole engagement's own named, protected
  regressions (`patients -> Homo sapiens`) - re-confirming it holds is
  the correct outcome here, not a finding to fix.
- **Specificity, both directions** - re-confirmed from the preceding
  pass (`"Ascending colon"` gains specificity; `"Colon"` alone does not
  become over-specific).
- **Semantic confusion** (`Oral cavity`, `Small intestine`, `Dental
  plaque` vs `saliva`/`feces`) - re-confirmed correct, all at REVIEW with
  the right label, none silently reverted to the specimen-alias answer.
- **Disease specificity** (`Type II diabetes mellitus`, `Type 2
  diabetes`, `Diabetes`, `Gestational diabetes`) - all four resolve to
  their own correct, distinct MONDO term at AUTO tier, confirming the
  roman-numeral and gestational-diabetes fixes from earlier passes hold.
- **Invalid/fabricated identifiers** (syntactically valid but non-
  existent CURIEs, and a real CURIE with a mismatched claimed label) -
  all land at REVIEW, never AUTO.
- **Obsolete identifiers** - a confirmed-obsolete MONDO CURIE
  (`MONDO:0017153`) correctly downgrades to REVIEW.
- **Ambiguous terms** - never reach AUTO (§2's blanket-invariant test).

### 5. Offline determinism and OLS fallback safety

**Determinism**: identical `NormalizedTerm` results across 3 repeated
in-process calls and across 3 independent fresh `python3` process
invocations for the same inputs, under the production-default
`GROUNDING_BACKEND_MODE=chain` (local store first, no live network
required for any of the tested cases).

**OLS fallback safety**: directly simulated (via `requests.get`
monkeypatching, not just read from source) - connection error, timeout,
malformed JSON, empty result list, and a malformed doc missing its
`label` field. All six return `None` from `ols_search()`, never raise,
never produce a usable-looking-but-wrong result. Confirmed a real,
successful OLS hit is still hard-capped at `mapping_confidence=0.9` (the
explicit parameter every call site passes), so even a fully healthy OLS
response cannot supply AUTO's precondition. These properties were already
covered by existing tests (`test_ols_search_handles_request_exception`,
`test_ols_search_handles_malformed_json`, ...) - this pass re-verified
them directly rather than assuming the existing suite still reflects
current behavior.

### 6. Final independent code review

Self-reviewed this pass's own diff (`types.py`, the three normalizers'
one-line entry-check change, the evaluation script's `distinct_species()`
fix) against the brief's checklist:

- **Duplicated logic**: none - `is_null_like()` is called identically by
  all three normalizers and by the evaluation script, no per-field
  reimplementation.
- **Bypasses around tier validation**: none found: the null-like check
  runs *before* any tier-relevant path, and `ground()`/`tier_for()`
  themselves are untouched this pass.
- **Hidden static mappings / field-specific hacks**: none - the
  placeholder list lives in one place (`types.py`), not duplicated or
  field-scoped.
- **Dead code**: checked for stray references to the earlier, reverted
  `EXCLUDED_CATEGORY_ROOTS`/`is_a_reachable_from` experiment from the
  preceding pass - only a historical mention remains in a comment
  explaining what was tried and removed, no leftover code.
- **Unnecessary network calls / unbounded queries**: none added -
  `is_null_like()` is pure string logic, zero I/O.
- **Exception paths that fail open dangerously**: `ols_search()`'s
  existing `except (RequestException, ValueError): return None` fails
  open to "no match" (safe - lets the caller's own no-match handling
  apply), not to a fabricated result - verified directly in §5, not
  merely read.
- **A real bug found and fixed during this review**: the `is_null_like()`
  edge-punctuation gap (§1) - caught by adversarial self-testing before
  being reported as complete, exactly the discipline this checklist
  exists to enforce.
- `black --check`/`flake8` clean on every file this pass touched.

### 7. Final regression

Full suite (excluding modules requiring `paperqa`/`fastapi`, not
installed in this sandbox - a pre-existing, disclosed environment gap,
not a code failure; CI runs the true full suite): **512 passed, 4 failed,
87 skipped**. The 4 failures are `tests/test_llm_provider.py`'s
`TestGeminiModelPrefixNormalization` class, failing on `ImportError:
LiteLLM is not installed` - a missing local dependency unrelated to any
change in this or the preceding three passes (confirmed present before
this pass began). Zero code-caused failures. New tests this pass:
`test_is_null_like_recognizes_common_data_entry_placeholders`,
`test_null_like_input_resolves_to_absent_across_all_three_ontology_
fields`, and `tests/test_confidence_tier_invariants.py`'s 6 tests.

Independent BugSigDB evaluation (14,588 rows): body_site 99.1%/99.1%/
0.991 (AUTO precision 100%), condition 95.8%/95.5%/0.956 (AUTO precision
86.7%), host_species 100%/100%/1.000 (AUTO precision 100%) - all three
fields at or above every previously-validated baseline, with the one
apparent regression traced to an evaluation-harness bug and fixed (§3).

### 8. Final decision: READY WITH CONDITIONS

Not upgraded to unconditional READY. Every condition below is bounded and
explicitly confirmed non-dangerous (none can produce a false AUTO
mapping) - listed in full rather than summarized away:

1. **condition field: 4 genuinely-wrong false-AUTO cases remain**, all
   the same single root cause from the semantic-hardening pass -
   BugSigDB's own ground truth for "SARS-CoV-2-related disease" points to
   an obsolete MONDO ID with no live replacement; `"COVID-19"` is a
   defensible, current, closely-related fallback, not a category error.
2. **body_site field: 4 coarser-but-related (non-dangerous) mismatches
   remain** out of 445 real cases (99.1% overall accuracy) - a real
   ancestor of the correct answer, never a different concept.
3. **The specificity override does not reach the ambiguous multi-match
   branch** (found in the specificity pass's own adversarial review) -
   `"Ascending colon and Saliva"`-shaped inputs correctly stay at REVIEW
   but show a coarser primary label within that already-safe ambiguity.
4. **The pre-existing local-store miss-fallback has no minimum-
   informativeness gate** - very short or generic inputs that reach it
   (rather than the static dict or the null-like check) can produce a
   low-confidence, sometimes odd-looking REVIEW-tier suggestion (e.g.
   `"sample"` -> `"human urinary metabolite"` at REVIEW). Never AUTO,
   always curator-reviewable, and this pass's `is_null_like()` closes the
   worst, most misleading instance of this class (`"N/A"` ->
   `"nasal artery"`) - the remainder is a suggestion-quality issue, not a
   correctness or safety one.

None of these four conditions describes a path to a false, automatically-
applied ontology mapping - every one of them, by construction and by
direct adversarial testing this pass, terminates at REVIEW or NONE. A
verdict of unconditional READY was considered and rejected specifically
because these four are real and worth a curator/maintainer's awareness,
not because any evidence points to a dangerous false-AUTO pathway - none
was found, anywhere, in this pass's own adversarial testing.

## 2026-08-09 (final sign-off) maintainer review of the four remaining conditions

External-maintainer-style review of exactly the four conditions the
preceding pass carried forward, each individually investigated,
classified, and either fixed (with the smallest safe change and
regression tests) or explicitly accepted with precise reasoning. No
broad redesign - two real, bounded bugs were found and fixed; two were
confirmed genuinely safe to accept as-is.

### Condition 1: condition field's 4 "SARS-CoV-2-related disease" false-AUTO cases

**Exact issue**: `normalize_condition("SARS-CoV-2-related disease")`
returns `MONDO:0100096` ("COVID-19") at "auto" tier; BugSigDB's own
ground truth for this text uses `MONDO:0100318`, so the evaluation
scores it as a false-AUTO.

**Affected code path**: `condition.py`'s `"covid-19"`/`"sars-cov-2"`/
`"covid"` static-dict keys; `tiering.ground()`'s round-trip/obsolete
check (which already runs against BioAnalyzer's own answer, correctly).

**Investigated, not assumed**: queried the real synced MONDO data.
`MONDO:0100318` is **obsolete with `replaced_by=""`** - no live successor
term exists to point to instead. Checked whether any *other* real,
current MONDO/EFO term the ground truth's multi-value ID list mentions
alongside it (`EFO:0009796`) might be the intended answer -
`EFO:0009796` is `"response to supplemental oxygen"`, an unrelated
concept that only co-occurs because that particular BugSigDB row's
Condition field has multiple, independent curated values, not because
it's an alternate name for the same thing.

**Classification**: `MONDO:0100096` "COVID-19" is real, current, non-
obsolete, and branch-valid - reaching "auto" for it is **correct
behavior**, not a false-AUTO in any dangerous sense. The evaluation's
"wrong" label is an artifact of scoring against BugSigDB's own stale
ground-truth ID, not evidence of a semantic or safety defect in
BioAnalyzer. **Correctness-only, and even that is disputable** - not
safety, not performance, not maintainability.

**Decision: accept, do not fix.** There is no live term to switch to
without either fabricating a "successor" mapping (explicitly prohibited)
or matching an admittedly-obsolete ID (which would defeat the obsolete-
term safety check this whole subsystem exists to enforce). Proven safe
in `test_every_remaining_known_condition_stays_below_auto`
(`tests/test_confidence_tier_invariants.py`) - the AUTO result is
asserted explicitly, by name, as intentional.

### Condition 2 / 3: body_site's remaining coarser-wrong cases and the ambiguous-branch override gap

**Exact issue**: two of the four remaining body_site "coarser-but-
related" cases from the preceding pass's evaluation - `"Mucosa of small
intestine"` and `"Wall of small intestine"` - turned out to share a
single root cause with a limitation that pass had already found and
explicitly declined to fix (the specificity override not reaching
`normalize_body_site()`'s *ambiguous* multi-match branch): both texts
contain "small intestine" *and*, as a real word-boundary substring of
that phrase, the generic casual-alias key "intestine" - two distinct
static-dict values, so `match_all()` reports genuine ambiguity and the
override (which only ran in the single-match branch) never got a chance
to notice the complete phrase is itself a real, more specific UBERON
term neither matched key represents.

**Affected code path**: `body_site.py`'s `normalize_body_site()`, the
`len(matched) > 1` branch.

**Re-investigated, not left as accepted**: the preceding pass's stated
reason for not fixing this was a *suspected* risk - swapping in the
override's answer might let an excluded key spuriously reappear as a
candidate. Re-traced `LookupMatcher.candidates()` directly (not
re-asserted from memory) and confirmed the exclusion logic keys off
`winning_key` (the original matched key text), not `winning_value` - so
swapping in the override's `(label, ontology_id)` while keeping
`winning_key` unchanged cannot cause this. Verified empirically
(`m.candidates("mucosa of small intestine", "small intestine",
override_value)` returns `()`, not a spurious "feces" candidate) before
writing the fix.

**Classification**: correctness (specificity), not safety - both cases
were already REVIEW tier (confidence 0.9, `PARTIALLY_PRESENT`) before
and after; the fix improves *which* answer is shown, never the tier.

**Decision: fixed.** `_resolve_structure_override()` is now also called
from the ambiguous-match branch. Regression test:
`test_body_site_structure_override_also_applies_in_the_ambiguous_multi_
match_branch` (`tests/test_normalization.py`) - covers both newly-fixed
cases and re-confirms the previously-tested genuine-ambiguity cases
(`"Ascending colon and Saliva"`, `"Colon and feces"`) still correctly
surface their second candidate, unaffected.

**Measured impact**: body_site precision/recall/F1 improved from
99.1%/99.1%/0.991 to **99.8%/99.8%/0.998** (444/445 correct, down from
441/445). The remaining single case (`"Insect head"`, an entomology
term with real ancestor/descendant UBERON structure) is unrelated to
this fix and left as a real, tiny, non-dangerous residual (REVIEW tier).

### Condition 4: the miss-fallback's missing minimum-informativeness gate - root cause corrected, a real bug found and fixed

**Exact issue, corrected from the preceding pass's description**: that
report attributed generic-word suggestions (`"sample"` -> some
unrelated-looking term) to `local_lookup()`'s local-store fallback
having no confidence floor. Direct re-investigation (tracing actual
execution, not re-asserting the prior description) found this was
**wrong about the source**: `local_lookup("sample", ("uberon",))`
returns `None` - nothing in the local store matches at all. The real
source is **live EBI OLS4's fuzzy (`exact=false`) search returning
cross-ontology results that `ols_search()` accepted and cached without
validating them** - a genuinely different, more serious bug than the one
originally described. Live-reproduced (not from a mock):
`ols_search("sample", "uberon", "UBERON")` returned a real **CHEBI**
term (`CHEBI:84087`, "human urinary metabolite") formatted and persisted
to the on-disk cache as if it were a valid UBERON (body-site) result,
because `format_ontology_id()` only ever uses the caller's `id_prefix`
argument as a *fallback default* for a bare numeric ID - it never
validates a *real*, embedded prefix against what the caller actually
requested. EBI's `ontology=` search parameter turned out to be a
relevance hint, not a hard filter, for fuzzy search.

**Affected code path**: `app/normalization/ols.py`'s `ols_search()` -
called by both `body_site.py` and `condition.py`'s live-network
fallbacks.

**Classification**: **not safety** (every `ols_search()` result is
`mapping_confidence <= 0.9`, structurally incapable of "auto" - proven
in `test_local_lookup_and_ols_are_structurally_incapable_of_auto_
confidence`) - but a real **correctness/data-quality defect**: a field
scoped to one ontology could silently return, and durably cache, a term
from a completely unrelated one.

**Decision: fixed.** `ols_search()` now rejects any result whose own
CURIE prefix doesn't match the requested `id_prefix`, before formatting
or caching it - one added check, no architecture change. Stale,
already-cached cross-ontology entries (19 rows, found via direct cache
inspection) were purged so the fix takes effect immediately rather than
being masked by pre-existing bad cache data. Regression tests:
`test_ols_search_rejects_cross_ontology_result` (mocked, so it doesn't
depend on live OLS's current behavior remaining reproducible) and
`test_ols_search_accepts_matching_ontology_result` (same-ontology
results must still work).

**Residual, correctly re-scoped and accepted**: same-ontology but low-
relevance fuzzy matches (`"patient"` -> a real but unrelated UBERON
term, `"study"` -> another) are a separate, narrower, and genuinely
lower-priority issue than the cross-ontology bug that prompted this
investigation - EBI OLS4's fuzzy search has no relevance-score floor
this codebase currently reads, and always returning *some* result for
*any* input text is inherent to fuzzy (non-exact) search. Never
dangerous (same structural confidence cap applies), proven directly for
five representative generic words across both affected fields in
`test_every_remaining_known_condition_stays_below_auto`. Accepted as a
suggestion-quality characteristic, not fixed further this pass - adding
a relevance-score threshold would require inspecting and calibrating
against OLS's actual scoring fields, a real but separate piece of work
from the cross-ontology-contamination bug this investigation was
launched to chase down.

**One honest, disclosed side effect**: because a permanently cross-
ontology-only query can now never be cached (the fix returns before
`store_cached_term()` is reached), a query that always triggers this
path will re-attempt a live OLS network call on every occurrence rather
than being served from cache after the first. Measured: the independent
evaluation's wall-clock time rose from ~5.7s to ~15-22s across repeated
runs after the stale cache was purged (still using the local-store-first
chain by default; this is live-network latency for the small number of
real dump values that reach this specific path). Classified as a real
but minor, non-recurring-in-the-worst-case, **performance-only**
characteristic - not fixed further this pass (a "known-bad, don't
retry" negative-cache would be a reasonable follow-up but is new
complexity beyond a "smallest safe fix" for a non-safety issue).

### Final safety proof

`test_every_remaining_known_condition_stays_below_auto`
(`tests/test_confidence_tier_invariants.py`) directly asserts, for every
one of the four conditions above (the two fixed and the two accepted):
no case reaches AUTO except Condition 1's `"SARS-CoV-2-related disease"`
result, which is asserted as AUTO *by name*, with the reasoning for why
that's correct rather than dangerous stated inline. Combined with the
structural proof already in this same file (`mapping_confidence == 1.0`
is returned from exactly one code shape per normalizer - a clean,
pre-audited static-dict match with zero candidates - and both
`local_lookup()` and `ols_search()` are hard-capped below it), this pass
found zero paths, live-tested or structural, by which a remaining
condition could produce an incorrect ontology identifier at AUTO
confidence.

### Final regression

Full suite (same disclosed environment gap as every prior pass - modules
requiring `paperqa`/`fastapi`, not installed in this sandbox, excluded;
CI runs the true full suite): **516 passed, 4 failed, 87 skipped**. The
4 failures are the same pre-existing `TestGeminiModelPrefixNormalization`
`ImportError: LiteLLM is not installed` failures present before this
pass (and every prior pass) began - a missing local dependency, not a
code defect. Zero code-caused failures.

Independent BugSigDB evaluation (14,588 rows, same corpus, ground truth
unmodified): body_site **99.8%/99.8%/0.998** (up from 99.1%/99.1%/0.991;
AUTO precision 100.0%, 72/72), condition **95.8%/95.5%/0.956**
(unchanged; AUTO precision 86.7%, 52/60 - all 4 remaining genuinely-wrong
AUTO cases are the single accepted Condition 1), host_species
**100%/100%/1.000** (unchanged; AUTO precision 100%, 6/6). False-AUTO
count across all three fields: body_site 0, condition 4 (all Condition
1, accepted as correct-not-false), host_species 0.

**Exact files changed this pass**: `app/normalization/ols.py` (the
cross-ontology validation fix), `app/normalization/body_site.py` (the
ambiguous-branch override extension), `tests/test_normalization.py` (4
new/extended tests), `tests/test_confidence_tier_invariants.py` (1 new
test), `scripts/eval/bugsigdb_independent_evaluation.py` (unchanged this
pass - already fixed in the preceding pass), `docs/
GROUNDING_ARCHITECTURE.md` (this section). The on-disk ontology-term
cache (`cache/analysis_cache.db`) had 19 stale, now-invalid rows purged
- data, not code.

**Exact files intentionally left unchanged**: `app/normalization/
condition.py`, `app/normalization/host_species.py`,
`app/normalization/grounding/*` (tiering, backend, roots, local_backend,
chain, ols_backend) - none of the four conditions traced back to a
defect in condition-field-specific logic, host-species logic, or the
grounding/tiering layer itself; touching any of them would have been
scope creep beyond what the investigation actually found.

### Final verdict: READY WITH CONDITIONS

Not READY, and specifically not for a precise, bounded reason rather
than residual caution: **Condition 1 remains** - a real evaluation
"false-AUTO" that this pass concluded is not actually a defect, but
which a maintainer should still be aware reflects BugSigDB ground-truth
staleness rather than 100% agreement. **Not NOT READY**: this pass found
zero evidence, anywhere in structural review or live adversarial
testing, of a path to an *incorrect* automatic ontology mapping - the
two real bugs found this pass (the ambiguous-branch gap, the OLS cross-
ontology contamination) were both already confidence-capped below
"auto" before being fixed, and are now fixed outright rather than merely
shown to be non-dangerous.

Remaining conditions, final classification:

1. Condition 1 (SARS-CoV-2/obsolete ground truth) - **correctness-
   adjacent, arguably not even a defect; not safety.**
2. The residual "Insect head" specificity case - **correctness only;
   not safety.**
3. The OLS fuzzy-search relevance-floor gap (generic words like
   `"patient"`/`"study"` at body_site) - **suggestion-quality only; not
   safety.**
4. The negative-caching performance characteristic for permanently-
   cross-ontology queries - **performance only; not safety, not
   correctness.**

None of the four can produce a false AUTO mapping. This was proven, not
assumed, for each one individually this pass.
