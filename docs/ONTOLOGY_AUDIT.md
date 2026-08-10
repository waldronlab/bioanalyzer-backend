# Ontology Mapping Verification Audit

Date: 2026-07-12. Scope: every static ontology ID hardcoded in
`app/normalization/{condition,body_site,host_species}.py`, checked against
the live EBI OLS API (`https://www.ebi.ac.uk/ols4/api`) — the same
authoritative source these modules already fall back to for terms not in
their static dicts.

This is a bounded correctness audit, not an architecture redesign. The
normalization system continues to return one ontology ID per field
(EFO/MONDO for condition, UBERON for body site, NCBITaxon for host species,
BugSigDB's own controlled vocab for sequencing type — no ontology ID). A
broader multi-ontology architecture (simultaneous EFO+MONDO+DOID+UBERON+HPO+
NCIT+MeSH+SNOMED+ICD mappings per concept, with per-mapping provenance/
confidence/versioning) was proposed and explicitly declined for this pass —
see "Scope decision" below.

## Executive summary

`condition.py`'s EFO lookup table was severely broken: 26 of 27 hardcoded
IDs were wrong or obsolete. `body_site.py`'s UBERON table had 2 wrong IDs out
of 17. `host_species.py`'s NCBITaxon table was fully correct (8 of 8). All
identified errors have been corrected in this pass; see
`docs/PROJECT_AUDIT.md`'s "Ontology Mapping Correctness" section for the
`condition.py` findings and fix details (not duplicated here).

## Verification method

For each unique ontology ID in a lookup dict: query
`GET /api/terms?iri=<full PURL/OBO IRI>` (or `/api/search` when the terms
endpoint returned nothing, to find the correct replacement) and compare the
returned `label` against the label the code claims for that ID. A mismatch
of unrelated concepts is scored "Incorrect"; a match where OLS marks the term
`obsolete_<label>` is scored "Deprecated" (right concept, retired ID).

## body_site.py — UBERON coverage (17 of 17 unique IDs checked)

| Keyword(s) | Claimed label | ID | Status | Evidence |
|---|---|---|---|---|
| feces/fecal/stool/gut/intestine/intestinal | feces | UBERON:0001988 | ✓ Correct | OLS label: "feces" |
| colon/colonic | colon | UBERON:0001155 | ✓ Correct | OLS label: "colon" |
| rectal/rectum | rectum | ~~UBERON:0000096~~ → **UBERON:0001052** | ✗→↺ Fixed | Old ID: 0 results (does not resolve). New ID confirmed via OLS search. |
| saliva/salivary/oral/mouth/dental | saliva | UBERON:0001836 | ✓ Correct | OLS label: "saliva" |
| tongue | tongue | UBERON:0001723 | ✓ Correct | OLS label: "tongue" |
| buccal | cheek | UBERON:0001567 | ✓ Correct | OLS label: "cheek" |
| vagina/vaginal | vagina | ~~UBERON:0000992~~ → **UBERON:0000996** | ✗→↺ Fixed | Old ID resolves to "ovary"/"female gonad" — wrong organ entirely. New ID confirmed via OLS search (exact match: "vagina"). |
| cervical | uterine cervix | UBERON:0000002 | ✓ Correct | OLS label: "uterine cervix" |
| uterine | uterus | UBERON:0000995 | ✓ Correct | OLS label: "uterus" |
| skin/cutaneous/dermal | skin | UBERON:0002097 | ✓ Correct | OLS label: "skin of body" (same concept) |
| lung/pulmonary/sputum | lung | UBERON:0002048 | ✓ Correct | OLS label: "lung" |
| bronchial | bronchus | UBERON:0002185 | ✓ Correct | OLS label: "bronchus" |
| nasal | nasal cavity | UBERON:0001707 | ✓ Correct | OLS label: "nasal cavity" |
| nasopharyngeal | nasopharynx | UBERON:0001728 | ✓ Correct | OLS label: "nasopharynx" |
| blood/serum/plasma | blood | UBERON:0000178 | ✓ Correct | OLS label: "blood" |
| urine | urine | UBERON:0001088 | ✓ Correct | OLS label: "urine" |
| urinary/bladder | urinary bladder | UBERON:0001255 | ✓ Correct | OLS label: "urinary bladder" |

**Result: 15/17 correct, 2 wrong (fixed).**

## host_species.py — NCBITaxon coverage (8 of 8 unique IDs checked)

| Keyword(s) | Claimed label | ID | Status | Evidence |
|---|---|---|---|---|
| human/humans/patient(s)/participant(s)/volunteer(s)/subject(s)/children/homo sapiens | Homo sapiens | NCBITaxon:9606 | ✓ Correct | OLS label: "Homo sapiens" |
| mouse/mice/mus musculus | Mus musculus | NCBITaxon:10090 | ✓ Correct | OLS label: "Mus musculus" |
| rat/rats/rattus norvegicus | Rattus norvegicus | NCBITaxon:10116 | ✓ Correct | OLS label: "Rattus norvegicus" |
| zebrafish/danio rerio | Danio rerio | NCBITaxon:7955 | ✓ Correct | OLS label: "Danio rerio" |
| pig/pigs/swine/sus scrofa | Sus scrofa | NCBITaxon:9823 | ✓ Correct | OLS label: "Sus scrofa" |
| chicken/gallus gallus | Gallus gallus | NCBITaxon:9031 | ✓ Correct | OLS label: "Gallus gallus" |
| rabbit/rabbits | Oryctolagus cuniculus | NCBITaxon:9986 | ✓ Correct | OLS label: "Oryctolagus cuniculus" |
| dog/dogs/canine | Canis lupus familiaris | NCBITaxon:9615 | ✓ Correct | OLS label: "Canis lupus familiaris" |

**Result: 8/8 correct.** Consistent with NCBITaxon IDs being stable,
widely-known identifiers with much lower fabrication risk than EFO's.

## condition.py — EFO/MONDO coverage

Full 27-entry table and fix details are in `docs/PROJECT_AUDIT.md`'s
"Ontology Mapping Correctness" section (not duplicated here to avoid drift
between two copies of the same table). Summary: 1/27 correct as shipped,
14/27 pointed at an unrelated concept, 12/27 pointed at a deprecated EFO term
whose live successor is in MONDO. All 27 corrected; 2 (comparator-arm/
exposure terms with no real disease-ontology equivalent) intentionally left
with no ontology ID rather than a fabricated one.

## Root cause

The pattern across all three modules — wrong/fabricated IDs concentrated in
`condition.py`'s EFO table, essentially none in the UBERON/NCBITaxon tables
— points at how the original dicts were likely built: NCBITaxon and (mostly)
UBERON IDs for these terms are common enough to appear correctly in general
training data, while EFO disease IDs are sequential, numerous, and largely
unmemorable, making them exactly the kind of identifier an LLM will
confidently fabricate a plausible-looking value for without a grounding
lookup. This is the generic risk of hardcoding any bibliographic/ontology ID
from memory rather than from a live or cached authoritative source.

## Scope decision: no architecture redesign

A follow-up request asked for a full multi-ontology redesign (per-concept
mappings across EFO/MONDO/DOID/UBERON/HPO/NCIT/MeSH/SNOMED/ICD with
per-mapping confidence/method/source/version/date-validated metadata) plus
end-to-end MeSH support (normalization output, API responses, curator CSV
columns, evaluation scripts, benchmark datasets). This was explicitly scoped
out of the current work for three reasons:

1. **No product requirement exists yet.** BugSigDB curation and this
   codebase's curator-desk CSV schema are driven by explicit PI review (see
   `docs/CURATOR_DESK_CSV_FORMAT.md`'s change history) — nobody has asked
   for MeSH support. Building it speculatively risks the wrong shape being
   built, then needing to change again once real requirements arrive.
2. **Cross-repo breaking change.** `curator_table_r` and `curator_table`
   both hardcode the curator-desk CSV's column list
   (`VALUE_COLUMNS`/`ONTOLOGY_ID_COLUMNS`); adding columns there requires
   coordinated changes across three repos, not one.
3. **Complexity-to-value ratio.** The current one-ontology-per-field design
   is what the entire pipeline (`FieldResult`, `NormalizedTerm`,
   `ExperimentFields`, the CSV renderer, `grounding.py`'s tier
   classification) is built around. A multi-ontology-per-field redesign
   touches every one of those, for a benefit (multiple simultaneous ontology
   mappings) that has no current consumer.

If MeSH support or multi-ontology mapping becomes an actual requirement
(e.g. requested by Levi Waldron or the curator team, or needed for
interoperability with an external system), it should be scoped as its own
project with the real requirement driving the design — not built ahead of
need. The existing `ols_search()` + `ontology_cache.py` "live lookup, cache
for reuse" mechanism (extended in this pass to also try MONDO after EFO)
already generalizes reasonably well to a new ontology/provider if that need
arises: adding MeSH would mean one new `ols_search(query, "mesh", "MESH")`
call site, not a schema redesign.

## What was NOT re-verified

- `sequencing_type.py`'s controlled vocabulary has no ontology IDs by
  design (it's BugSigDB's own vocabulary, not an external ontology) —
  nothing to check.
- The live-lookup fallback paths themselves (`ols_search()`,
  `normalize_host_species()`'s NCBI Taxonomy fallback) were not re-audited
  here since they resolve dynamically against the live source at call time
  by construction — there's no static value to go stale.
- `curator_table_r`'s own ontology-related code (a separate git repo) was
  out of scope for this pass.

## Verification

`pytest tests/test_normalization.py tests/test_ontology_benchmark.py` — 41
passed. Full suite (`./run_tests.sh`) — 626 passed (see
`docs/PROJECT_AUDIT.md` for the full-suite run covering the `condition.py`
fix; the `body_site.py` vagina/rectum fixes in this document were verified
against the same suite with no additional failures).

## Follow-up: continuous grounding, not just a one-time fix (2026-07-21)

Everything above was a **manual, one-time** re-verification of the static
lookup dicts. That fixes the specific IDs found wrong on 2026-07-12, but it
doesn't stop the same failure mode recurring silently: if EFO deprecates a
currently-correct static ID next year, `grounding.py::tier_for()` had no way
to notice and would keep returning `"auto"` for it indefinitely.

`app/normalization/grounding.py` now runs a four-step grounding
discipline against any match that would otherwise earn `"auto"`, downgrading it to
`"review"` if any step fails:

1. **Lookup** — unchanged; still the existing static-dict substring match in
   `condition.py`/`body_site.py`/`host_species.py`.
2. **Round-trip** — `app.normalization.ols.fetch_term()` re-fetches the
   `ontology_id` directly from OLS by IRI and confirms it still resolves to
   something. A miss here is the strongest signal of a fabricated or
   since-deleted ID.
3. **Branch check** — `app.normalization.ols.is_in_branch()` confirms the
   term is still reachable from its ontology's declared root
   (`grounding.py`'s `ROOTS`: EFO→`EFO:0000408` "disease",
   MONDO→`MONDO:0000001` "disease or disorder",
   UBERON→`UBERON:0001062` "anatomical entity",
   NCBITaxon→`NCBITaxon:2759` "Eukaryota"). Catches a static ID that now
   resolves to an unrelated concept even though the ID itself still exists —
   exactly the "COVID-19 pointing at an obsolete anatomy term" failure mode
   from the original incident, but caught automatically instead of by a
   human spot-check.
4. **Obsolete check** — `fetch_term()` also surfaces OLS's own `is_obsolete`
   flag and `term_replaced_by`, so a deprecated-but-still-resolving term
   doesn't slip through as `"auto"` either.

**Scope, deliberately narrow:** this only ever downgrades `auto → review`,
never the reverse, and never touches live-OLS-lookup results (those were
already `"review"` per the existing source-based tiering and stay there —
loosening that to a match-quality-based tiering
would reopen the hole this whole system exists to close).

**Cost:** the static dicts contain on the order of 50 unique `ontology_id`s
total across all three modules. Results are cached
(`grounding_check_cache`, SQLite, TTL-based via `GROUNDING_CACHE_VALIDITY_HOURS`
— unlike `ontology_term_cache`, this cache is *meant* to expire, since
obsolescence is exactly the drift it exists to catch) — so this is one OLS
round-trip per unique ID per TTL window, not per request.

**Failure mode if OLS is unreachable:** treated as "unable to verify," and
the match keeps whatever tier it already had (fail open) rather than forcing
every result to `"review"` during an OLS outage.

**Not implemented — a local ontology store:** a
DuckDB/semantic-sql-derived local ontology backend was considered as a faster, offline
alternative to live OLS. Given this codebase's static dicts only need to
verify ~50 IDs (not run arbitrary free-text search against a full ontology),
the cost/benefit didn't justify a new heavy dependency and a multi-GB
ontology-dump ETL/refresh pipeline for this pass — flagged as a future
option if OLS latency/availability becomes an actual problem, not built
ahead of that need (same reasoning as "Scope decision" above).

**Caveat:** the exact OLS4 JSON field names used here (`is_obsolete`,
`term_replaced_by`, `_embedded.terms`) are based on OLS's documented/
historically-stable REST API rather than a live call made during this
change (this session's network access to `ebi.ac.uk` was blocked). Every
parse path degrades to "unable to verify" rather than raising on an
unexpected shape, but this should get a real smoke-test against live OLS
before anyone relies on the round-trip/branch/obsolete checks actually
firing correctly in production.
