# BioAnalyzer-Backend — Production Readiness Audit

Date: 2026-07-11
Scope: full repository (`app/`, `scripts/`, `tests/`, Docker/CI config, docs). The
nested `curator_table_r/` directory is a separate git repository and was out of
scope for code changes, though its consumer contract is referenced where relevant.

This audit is a point-in-time snapshot. File:line references may drift as the
code evolves — verify against the current source before acting on any single
finding in isolation.

---

## Executive Summary

BioAnalyzer's core extraction pipeline (PubMed/PMC retrieval → LLM extraction →
ontology normalization → curator-desk CSV) is thoughtfully engineered for a
single-tenant research tool: credential masking is genuinely careful, retries
and cache-TTL exist on the primary path, async wrapping of sync I/O is mostly
correct, and the exception-handling/rate-limiting middleware shows real
production instinct. It is **not**, however, safe to expose as a public-facing
service today. Three gaps dominate the risk picture:

1. **No authentication anywhere** — every endpoint, including LLM-cost-incurring
   ones, is open to any network-reachable caller.
2. **Unbounded batch/URL-analysis endpoints** — no request-size caps, so a
   single anonymous request can fan out unlimited concurrent LLM calls.
3. **The more expensive v2/RAG pipeline never reads its own cache** — every
   `/api/v2/analyze/{pmid}` call fully re-runs a multi-LLM-call pipeline even
   for a PMID analyzed seconds earlier.
4. **(Found and fixed during this audit)** `app/normalization/condition.py`'s
   hardcoded EFO ontology-ID lookup table was largely wrong — 14 of 27 IDs
   pointed at an unrelated concept entirely (e.g. the code claiming COVID-19
   silently returned the ID for an obsolete anatomy term), and 12 more pointed
   at EFO terms since deprecated by the ontology itself. Every ID was
   re-verified against the live EBI OLS API and corrected; see "Ontology
   Mapping Correctness" below. This was shipping silently at "auto"
   confidence tier — no curator review was ever triggered.

None of these are architecturally hard to fix — they're additive (an auth
dependency, a few `Field()` constraints, one missing cache-read call) rather
than requiring a redesign. The codebase's layering (CLI/API → Services →
Models/Normalization → Utils) is sound and consistently followed.

As part of this audit, the **Taxa Level** field (one of the original six
BugSigDB curation fields) was removed end-to-end per an explicit product
decision — see "Taxa Level Removal" below.

---

## Architecture Assessment

- **Layering is consistently followed.** CLI/API → Services →
  Models/Normalization → Utils, with v1 (`simple_analysis.py`) and v2
  (`rag_analysis.py`) sharing `field_extraction.py`/`parsing.py`/`constants.py`
  under `app/services/bugsigdb_analyzer/`. Dependency direction is correct
  throughout.
- **Two config systems** (`app/core/settings.py`, Pydantic, and
  `app/utils/config.py`, flat `os.getenv`) are bridged rather than duplicated
  — `config.py` overlays structured settings onto its constants at import
  time — but this means anything importing `app.utils.config` gets settings
  frozen at process start, while `get_settings()` callers get live values.
  Two sources of truth for ~20 knobs is real maintenance risk even with the
  bridge (Medium).
- **In-memory, unbounded state in two places**: `job_store` (dict, in
  `app/api/routers/study_analysis.py`) and the rate-limiter's
  `_rate_limit_store` (`app/api/middleware/rate_limit.py`). Neither evicts
  entries. Both are lost on restart and not shared across worker processes
  (already flagged for `job_store` in `CLAUDE.md`; the rate-limit store has
  the identical defect, undocumented until now). **High** for `job_store`
  (holds full extraction payloads), **Medium-High** for the rate-limit store.
- **Redis is a hard startup dependency with no functional purpose.**
  `docker-compose.yml`'s app service has `depends_on: redis: condition:
  service_healthy`, but nothing in `app/` imports or talks to Redis — the
  comment in `rate_limit.py` says "use Redis in production" but it was never
  wired up. If the Redis container fails its healthcheck, the whole app fails
  to start for no reason (Medium-High).
- **DI is informal but workable.** Services are wired via lazy
  module-level singletons (`singletons.py`: `get_unified_qa`,
  `get_pubmed_retriever`, `get_cache_manager`) rather than FastAPI's
  `Depends()`. Not a SOLID violation for this codebase's size, but call
  sites depend on concrete classes, so tests rely on `unittest.mock.patch`
  rather than constructor injection (Low).
- **Global exception handling is solid** — every unhandled exception routes
  through `mask_exception_message` before logging/returning
  (`app/api/app.py`), and `study_analysis.py`'s separate handler (documented
  in `CLAUDE.md` as bypassing the global one) was independently verified to
  call the same masking function correctly.

## Security Assessment

Full findings from a dedicated security-focused pass; see the summary table
below for severity/location. Nothing here found actual SQL/command injection,
unsafe deserialization, or hardcoded secrets — the codebase's baseline
hygiene (parameterized SQLite, no `eval`/`pickle`/unsafe YAML, CVE-aware
dependency floors with inline comments) is good.

| # | Finding | Severity | Location |
|---|---|---|---|
| 1 | No authentication/authorization on any endpoint | **Critical** | `app/api/app.py`, all routers |
| 2 | Unauthenticated endpoints can trigger unbounded LLM spend (`refresh=true`, unbounded batch, `analyze-url`, `/qa`, `/health/gemini`) | **High** | `bugsigdb_analysis.py:34`, `bugsigdb_analysis_v2.py:149-152`, `study_analysis.py:45`, `system.py:370,122` |
| 3 | SSRF guard doesn't re-validate redirects (aiohttp follows them by default) | Medium | `web_scraper.py:165-171,264-268`, `url_safety.py` |
| 4 | Rate limiter trusts client-supplied `X-Forwarded-For`/`X-Real-IP`, trivially bypassable | Medium | `rate_limit.py:80-91` |
| 5 | `POST /qa` skips Pydantic validation, raw dict input | Medium | `system.py:370-371` |
| 6 | CORS defaults to `*` unless `ENVIRONMENT=production` is explicitly set | Medium | `app.py:58` |
| 7 | Anthropic-style `sk-ant-` keys not matched by credential-masking regex | Medium | `credential_masking.py:70` |
| 8 | `job_store` in-memory dict never evicted — unbounded memory growth | Medium | `study_analysis.py:24` |
| 9 | Full raw LLM responses (incl. paper text) logged at INFO by default | Low | `gemini_qa.py:205` |
| 10 | No security response headers (CSP/X-Frame-Options/HSTS) | Low | `app.py` (absent) |

**Deployment-context note:** `docker-compose.yml` publishes the API port
directly to the host with no reverse proxy or TLS termination in the repo.
Nothing in the docs suggests this is meant to sit behind an authenticating
gateway, so the "no auth" finding is treated as a genuine gap, not an
accepted internal-tool tradeoff.

**What's already solid:** parameterized SQLite everywhere, a working SSRF
hostname/IP allowlist check on scrape and image-download paths, correct
credential masking wired through both the global handler and
`study_analysis.py`'s independent one, deliberate avoidance of
`allow_credentials=True` with wildcard CORS, PMID input validation on v1,
no unsafe deserialization anywhere, CVE-aware dependency floors.

## Ontology Mapping Correctness (Critical — found and fixed)

While answering a follow-up question about whether `tests/test_normalization.py`
was hardcoding ontology data, every static ontology ID in
`app/normalization/`'s lookup dicts was individually checked against the live
EBI OLS API (`https://www.ebi.ac.uk/ols4/api`) — the same authoritative
source the code itself falls back to for terms not in the static dicts.

**`condition.py`'s `CONDITION_LOOKUP` (EFO IDs) was severely wrong:**

| Category | Count | Example |
|---|---|---|
| Pointed at a completely unrelated concept | 14 of 27 | `EFO:0003601` was hardcoded as "COVID-19" — it actually resolves to an obsolete anatomy term ("somite 13"). `EFO:0000189` was hardcoded as "HIV infection" — it actually resolves to an obsolete liver-cancer term. |
| Pointed at the right disease but a since-deprecated EFO term | 12 of 27 | `EFO:0002508` ("Parkinson disease") is now `obsolete_Parkinson's disease` in EFO — the live term moved to MONDO. |
| Verified correct and live | 1 of 27 | `EFO:0000400` ("diabetes mellitus"). |

This has the fingerprint of an LLM having generated plausible-looking EFO IDs
without verifying them — EFO IDs are sequential and semantically unguessable,
so a wrong one isn't a typo, it's fabricated. Critically, these were all
`mapping_tier="auto"` — the tier that skips curator review — so a paper about
asthma, HIV, or NAFLD would have silently written a **confidently wrong**
ontology ID into the curator-desk CSV's `Condition Ontology ID` column.

**`body_site.py`'s `BODY_SITE_LOOKUP` (UBERON IDs) was largely correct** — of
9 spot-checked IDs, only `rectum` was wrong (`UBERON:0000096` doesn't resolve
to anything; the real ID is `UBERON:0001052`).

**`host_species.py`'s `SPECIES_LOOKUP` (NCBITaxon IDs)** — spot-checked
entries (chicken, dog) were correct; NCBITaxon IDs are stable, well-known
identifiers with much lower fabrication risk than EFO's.

**Fix applied:** every `CONDITION_LOOKUP` entry was corrected against a live
OLS lookup (EFO where a live EFO term exists, MONDO where EFO has retired the
term — MONDO is what OLS itself reports as the successor). Two entries
("healthy"/"control"/"normal" and "antibiotic") had no clean disease-ontology
equivalent at all (they're comparator-arm/exposure descriptors, not
diagnoses) and were changed to return an empty `ontology_id` rather than a
fabricated one — `mapping_tier` correctly falls to `"none"` for these now
instead of falsely claiming `"auto"`. The `rectum` UBERON ID was corrected.
`scripts/eval/ontology_benchmark.py`'s gold-standard test cases had the same
wrong IDs baked in as "ground truth" and were corrected too — the benchmark
would otherwise have scored a now-correct `condition.py` as *wrong* against
an equally-wrong gold standard.

**Also extended:** `condition.py`'s live-lookup fallback (for terms not in
the static dict) now tries MONDO after EFO comes up empty, since EFO has
retired most disease terms in favor of MONDO. Both providers already went
through `app.normalization.ontology_cache`'s persistent SQLite-backed cache
(`ols_search()`), so a term only needs a live lookup once — this is the
existing "cache first, live-lookup-and-store second" mechanism, not new
infrastructure.

**Not yet independently re-verified:** `sequencing_type.py`'s controlled
vocabulary has no ontology IDs by design (BugSigDB's own vocab, not an
external ontology — confirmed nothing to check there). The `condition.py`
static dict's remaining entries beyond what's listed above (all 27 keys)
were checked exhaustively; `body_site.py` and `host_species.py` were spot-
checked, not exhaustively — a full pass on those two would be worth doing in
a follow-up session using the same method (query each ID against
`https://www.ebi.ac.uk/ols4/api/terms?iri=<full IRI>` and diff the returned
label against what the code claims).

## Performance Assessment

| Finding | Severity | Location |
|---|---|---|
| v2/RAG pipeline never reads its own cache — every call fully re-runs a multi-LLM-call pipeline | **High** | `rag_analysis.py` (no cache-read call; only `store_analysis_result` at line 199) |
| `BatchAnalysisRequestV2` has no `pmids` length cap or `max_concurrent` ceiling | **High** | `api_models.py:146-152`, `bugsigdb_analysis_v2.py:171-218` |
| Blocking sync PubMed call inside async health-check route | Medium-High | `system.py:191` (`ncbi_health_check` calls the sync `fetch_paper_metadata` instead of the existing async variant) |
| No retry/backoff on LLM calls (PubMed calls do have hand-rolled retries) | Medium-High | `app/models/llm_provider.py` |
| Sequential (non-`asyncio.gather`) LLM calls in chunk re-ranking | Medium | `chunk_reranking.py:114-135` (contrast with `contextual_summarization.py`, which batches correctly) |
| Blocking `requests.get` inside async image-analysis fallback | Medium | `unified_qa.py:361` |
| `cache_manager.get_metadata`/`get_fulltext` are dead code — PubMed content is refetched every time regardless of cache | Medium | `cache_manager.py:272-360` |
| SQLite cache has no WAL mode / busy_timeout — risk of `database is locked` under concurrent batch writes | Medium | `cache_manager.py:28-36` |
| v2 never validates PMID format before a network round-trip | Medium | `bugsigdb_analysis_v2.py` (doesn't call `validate_pmid`) |
| `/metrics`' `cache_hit_rate` is always 0.0 (dead metric) | Low-Medium | `cache_manager.py:442-491`, `system.py:237-239` |
| Container healthcheck only checks a shallow `/health`, not DB/cache/NCBI/LLM reachability | Medium | `docker-compose.yml`, `app.py:101-106` |

## Maintainability Assessment

- Consistent naming and folder structure; `scripts/cli_rendering.py` was
  already split out of `scripts/cli.py` for separation of concerns.
- `FIELD_KEYS`/`ANALYSIS_FIELDS`/`ESSENTIAL_FIELDS_INFO` are defined in three
  separate places (`bugsigdb_analyzer/constants.py`,
  `scripts/cli_rendering.py`, `app/api/utils/constants.py`) that must be kept
  in sync by hand — confirmed all three were updated consistently for the
  Taxa Level removal in this pass, but this is a standing single-source-of-
  truth risk for the next field-schema change.
- `docs/ARCHITECTURE.md` describes a materially larger aspirational system
  (Postgres, Prometheus, Kubernetes, circuit breakers) not reflected in the
  actual codebase — already flagged in `CLAUDE.md` as a roadmap sketch, not
  ground truth; still worth a header disclaimer in the file itself so new
  contributors don't take it at face value.
- See `docs/REMOVAL_CANDIDATES.md` for dead code, duplicate implementations,
  and other technical debt found during this pass.

## Testing Assessment

- Full suite mocks external calls (PubMed, LLM providers); no live
  network/LLM dependency, consistent with `CLAUDE.md`.
- `app/services/agent_orchestrator.py` and its router
  (`study_analysis.py`) — CLAUDE.md already notes no test coverage exists
  for the router itself; `AgentOrchestrator`'s helper functions do have
  dedicated unit tests (`tests/test_agent_orchestrator.py`), which were
  updated as part of this pass.
- `app/utils/field_validator.py` and `app/utils/common.py` have dedicated
  test files but **zero production call sites** — see
  `docs/REMOVAL_CANDIDATES.md`; their tests currently validate dead code.
- Taxa Level removal: all references removed from
  `tests/test_api_endpoints.py`, `test_bugsigdb_analyzer.py`,
  `test_integration.py`, `test_curator_desk_csv_format.py`,
  `test_agent_orchestrator.py`, `test_field_validator.py`,
  `test_normalization.py`, `test_api_utils.py`. See "Taxa Level Removal"
  below for what each change covered.

## Technical Debt Summary

See `docs/REMOVAL_CANDIDATES.md` for the full list with confidence levels.
Highlights:

- `app/utils/common.py` and `app/utils/field_validator.py` — zero production
  call sites, only referenced by their own dedicated test files.
- `scripts/ops/log_cleanup.py`, `log_dashboard.py`, `performance_monitor.py`
  — each file's own docstring says it was archived/moved out of the active
  tree, but they still live in `scripts/ops/` with zero references anywhere.
- `redis` service in `docker-compose.yml` — provisioned, hard-depended-on at
  container startup, never used by application code.
- `torchvision`/`torchaudio` in `requirements.txt` — declared, never
  imported (needs confirmation they aren't required for a pinned-triple
  convention before removing).
- `html2text` — used in `web_scraper.py` but **not declared** in
  `requirements.txt`/`pyproject.toml` at all (an undeclared-dependency bug,
  not a removal candidate).
- `UnifiedQA(use_gemini=...)` — marked deprecated in its own docstring, but
  is what 2 of 3 production call sites actually use; the "new" `provider=`
  form is used by only one call site.

## Taxa Level Removal (Phase 6)

Taxa Level was originally one of six BugSigDB curation fields BioAnalyzer
extracted (Host Species, Body Site, Condition, Sequencing Type, Sample Size,
**Taxa Level**). A prior session (2026-07-02, "curator schema simplification")
had already dropped it from the LLM extraction prompt and the curator-facing
CSV, while deliberately keeping it in the internal API contract and the
`--format detailed_csv` validation export, per an explicit decision at the
time. This audit's Phase 6 reversed that decision and removed it completely,
per direct instruction, after confirming with the requester that this is an
intentional product change (not incidental cleanup) given the field's
prominence in `CLAUDE.md`'s description of the product.

**Removed from:**
- `app/normalization/taxa_level.py` — deleted entirely (the module).
- `app/api/utils/constants.py`, `app/api/utils/api_utils.py` — the
  `/api/v1/fields` essential-fields listing and default-field-structure
  fallback.
- `app/utils/field_validator.py` — validation regex patterns and the
  five/six-field iteration lists (this module has no production call sites —
  see Technical Debt Summary — but was kept internally consistent regardless).
- `app/services/agent_orchestrator.py` — `_avg_confidence`,
  `_check_missing_fields`, the URL-analysis LLM prompt, and the
  key-alias parser used to build `ExperimentFields` from free-text LLM output.
- `app/services/bugsigdb_analyzer/{constants,field_extraction,__init__}.py`
  — `FIELD_KEYS`, `STATUS_COLUMNS`, `ESSENTIAL_FIELDS`, the heuristic-payload
  extractor, and the unified-payload-to-`FieldResult` mapper.
- `app/models/gemini_qa.py`, `app/models/paperqa_agent.py` — prompts and
  fallback-JSON schemas for the Gemini-direct and Paper-QA-agent paths.
- `scripts/cli.py`, `scripts/cli_rendering.py`,
  `scripts/eval/confusion_matrix_analysis.py`,
  `scripts/dev/cli_smoke_check.py` — CLI field-info display, `ANALYSIS_FIELDS`
  (used by both `--format detailed_csv` and the XML renderer), and the
  confusion-matrix evaluation variable list.
- 8 test files (see Testing Assessment above).
- Documentation: `CLAUDE.md`, `docs/DEVELOPER_GUIDE.md`,
  `docs/CURATOR_DESK_CSV_FORMAT.md`, `docs/CLI_DOCUMENTATION.md`,
  `docs/CURATOR_TABLE_USER_GUIDE.md`, `docs/FOLDER_STRUCTURE.md`,
  `docs/ARCHITECTURE_FLOW.md`, `docs/CURATOR_DESK_ALIGNMENT.md`,
  `docs/ARCHITECTURE.md`, `docs/QUICK_REFERENCE.md`,
  `docs/CURATOR_TABLE_DESIGN.md`.

**Correction (found during a later hardening audit, verified against git
history):** this section originally also listed `app/models/
extraction_schemas.py` — `ExperimentFields.taxa_level`,
`ExperimentMetadata.taxa_level` — as removed. `git show <the Phase 6
commit> -- app/models/extraction_schemas.py` produces no diff: that file
was never actually touched. `taxa_level` remains a live field on
`ExperimentFields`/`ExperimentMetadata` today, used only by the separate
URL-analysis pipeline (`app/services/agent_orchestrator.py`,
`app/api/routers/study_analysis.py`) — never by the PMID-based v1/v2
pipelines this Phase 6 pass targeted. It's functionally inert there:
`agent_orchestrator.py`'s `_flush()` never populates it, so it always
serializes as `status="ABSENT", value=""` in `StudyAnalysisResult`
responses - not fabricated data, just a vestigial always-empty field. Left
unremoved rather than fixed here, since removing a live field is a
separate, deliberate decision (the same kind Phase 6 itself required
"direct instruction" and requester confirmation for above), not a
documentation fix.

**Deliberately NOT touched** (different concept, same surface vocabulary):
- `has_differential_abundance`/`MicrobialSignature.taxon_name` and all
  "specific microbial taxa reported as differentially abundant" language —
  this is BioAnalyzer's separate differential-abundance-signature feature,
  unrelated to the Taxa Level *curation field*.
- `app/api/utils/api_utils.py::extract_taxa()` — a generic genus/species-name
  regex extractor. It has zero production call sites (only its own tests),
  so it's dead code, but it's a distinct concept from the Taxa Level field
  and was left for a separate technical-debt decision — see
  `docs/REMOVAL_CANDIDATES.md`.
- `NCBITaxon:*` ontology IDs throughout (host-species ontology mapping) —
  unrelated "taxon" in the NCBI Taxonomy sense.
- `curator_table_r/` (nested, separate git repo) — not in scope; it never
  had a Taxa Level column to begin with, so no consumer-side change is
  required there.

**Residual/downstream impact:** `scripts/eval/confusion_matrix_analysis.py`
previously computed a confusion matrix over "Taxa Level Status" as one of six
fields, per earlier guidance from the project's PI. That variable has been
dropped from the analysis; the script now evaluates five fields. If Taxa
Level accuracy tracking is still wanted for curator QA purposes, that
guidance should be revisited with the PI — it's no longer possible to
reconstruct from this pipeline since the field is no longer extracted at all.

**Verification:** `black`, `flake8` (project's documented invocation), and
the full Docker-based `pytest` suite were run after all changes — see the
final section of this document / the conversation this audit was produced
in for pass/fail status at time of writing.

## Production Readiness Score: 4.5 / 10

The core extraction pipeline is well-engineered for a single-tenant/internal
research tool. It is not yet safe to expose publicly: no authentication on
cost-incurring LLM endpoints, an unbounded batch endpoint any anonymous
caller can use to fan out unlimited concurrent LLM calls, and a broken
cache path on the more expensive v2/RAG pipeline that silently defeats the
one mechanism meant to control that cost. Add in-memory job/rate-limit
stores, a shallow container health check, and no LLM-call retry coverage,
and the picture is: solid engineering for its current usage pattern, not
yet production-hardened for public/multi-tenant exposure.

## Risk Assessment

| Risk | Likelihood | Impact | Priority |
|---|---|---|---|
| Unauthenticated public exposure leads to LLM cost abuse | High if ever deployed publicly | High ($ spend, potential outage) | Address before any public deployment |
| v2 cache-bypass inflates LLM spend/latency for legitimate use | Certain (every v2 call) | Medium-High | Fix soon — single-function change |
| `job_store`/rate-limit-store unbounded growth | Medium (depends on traffic/uptime) | Medium (memory exhaustion over long uptime) | Fix before long-running production deployment |
| Redis hard dependency causes spurious startup failure | Low-Medium (depends on infra reliability) | Medium (full outage) | Cheap fix — remove `depends_on` or wire Redis up |
| SSRF via redirect bypass on URL-analysis pipeline | Low (requires attacker-supplied URL + redirect chain) | Medium (internal network access) | Fix if `analyze-url` is ever exposed to untrusted input |

## Prioritized GitHub Issues

See `docs/REMOVAL_CANDIDATES.md` for technical-debt items; the issues below
are production-readiness/security/performance gaps suitable for direct
copy-paste into GitHub Issues.

---

### 1. No authentication on any API endpoint

**Severity:** Critical
**Category:** Security

**Description:** No authentication or authorization exists anywhere in
`app/api/`. Every router, including LLM-cost-incurring ones, is fully open
to any network-reachable caller.

**Current behavior:** Any request to any endpoint succeeds regardless of
caller identity.

**Expected behavior:** Cost-incurring/data-returning endpoints require at
minimum a shared-secret API key or bearer token.

**Why it matters:** `docker-compose.yml` publishes the API port directly to
the host with no reverse proxy in the repo. If ever deployed on a
publicly-reachable host, anyone can run up real LLM API spend.

**Recommended solution:** Add a `Depends()`-based API-key/bearer-token check
in front of `/api/v1/*` and `/api/v2/*` routers.

**Estimated effort:** Small-Medium (1-2 days, including tests).

**Files likely affected:** `app/api/app.py`, all files under
`app/api/routers/`, new `app/api/dependencies/auth.py`.

**Acceptance criteria:** Unauthenticated requests to protected routes return
401/403; existing tests updated with auth fixtures; documented in
`.env.example`/`CLAUDE.md`.

---

### 2. Unbounded batch-analysis and URL-analysis endpoints

**Severity:** High
**Category:** Security / DoS

**Description:** `BatchAnalysisRequestV2.pmids` and `.max_concurrent` have no
length/range constraints; `POST /api/v1/analyze-url` has no per-caller
concurrent-job cap.

**Current behavior:** A single request can submit thousands of PMIDs or an
arbitrarily large `max_concurrent`, fanning out unlimited concurrent LLM
calls.

**Expected behavior:** Request-size and concurrency are bounded.

**Why it matters:** Combined with issue #1 (no auth), this is a trivial,
unauthenticated cost-blowup/DoS vector.

**Recommended solution:** Add `Field(max_length=50)` to `pmids`, `Field(le=10)`
to `max_concurrent`, and a global concurrent-job semaphore for
`analyze-url`.

**Estimated effort:** Small (half a day).

**Files likely affected:** `app/api/models/api_models.py`,
`app/api/routers/bugsigdb_analysis_v2.py`,
`app/api/routers/study_analysis.py`.

**Acceptance criteria:** Requests exceeding the new limits return 422;
covered by a new test case.

---

### 3. v2/RAG pipeline never reads its own cache

**Severity:** High
**Category:** Performance / Cost

**Description:** `analyze_paper_with_rag` only writes to the cache
(`store_analysis_result`), never reads it — every `/api/v2/analyze/{pmid}`
call re-runs the full multi-LLM-call RAG pipeline even for a PMID analyzed
seconds earlier.

**Current behavior:** No cache hit is ever possible on the v2 path.

**Expected behavior:** v2 checks the cache first, mirroring v1's
`is_cache_valid`/`get_analysis_result` pattern.

**Why it matters:** This is the single biggest avoidable cost/latency
driver identified in this audit.

**Recommended solution:** Add the same cache-read guard used in
`simple_analysis.py` to the top of `rag_analysis.py::analyze_paper_with_rag`.

**Estimated effort:** Small (a few hours, plus a regression test).

**Files likely affected:** `app/services/bugsigdb_analyzer/rag_analysis.py`.

**Acceptance criteria:** A second call to `/api/v2/analyze/{pmid}` for the
same PMID within the TTL window returns a cached result without a new LLM
call (verifiable via a mock-call-count assertion in tests).

---

### 4. In-memory `job_store` and rate-limit store grow unbounded

**Severity:** Medium
**Category:** Reliability / Memory

**Description:** Neither `job_store` (`study_analysis.py`) nor
`_rate_limit_store` (`rate_limit.py`) ever evicts entries.

**Current behavior:** Both dicts grow for the lifetime of the process.

**Expected behavior:** Entries expire after a TTL, or the stores are backed
by something with native expiry (e.g. Redis, if it's kept).

**Why it matters:** Long-running deployments accumulate memory
indefinitely; `job_store` entries embed full extraction output.

**Recommended solution:** Add TTL-based eviction (e.g. a background sweep,
or move to Redis now that it's already provisioned in
`docker-compose.yml`).

**Estimated effort:** Medium (1-2 days if adopting Redis; less for an
in-process TTL sweep).

**Files likely affected:** `app/api/routers/study_analysis.py`,
`app/api/middleware/rate_limit.py`.

**Acceptance criteria:** A load test confirms bounded memory growth over
an extended run.

---

### 5. Redis is a hard startup dependency with no functional purpose

**Severity:** Medium
**Category:** Reliability

**Description:** `docker-compose.yml`'s app service has
`depends_on: redis: condition: service_healthy`, but no application code
talks to Redis.

**Current behavior:** If the Redis container fails its healthcheck, the
whole app fails to start.

**Expected behavior:** Either remove the dependency, or actually wire Redis
into the cache/rate-limit/job-store layers (see issue #4).

**Recommended solution:** Decide one way or the other; if keeping Redis for
future use, wire at least one consumer; otherwise remove the service and
the `depends_on`.

**Estimated effort:** Small (remove) or Medium (wire up), see issue #4.

**Files likely affected:** `docker-compose.yml`, `docker-compose.prod.yml`.

**Acceptance criteria:** `docker compose up` never fails due to an unused
service's healthcheck.

---

### 6. Rate limiter trusts client-supplied IP headers

**Severity:** Medium
**Category:** Security

**Description:** `_get_client_ip` in `rate_limit.py` trusts
`X-Forwarded-For`/`X-Real-IP` unconditionally, with no check that the
request came through a trusted proxy.

**Current behavior:** Any caller can set a fresh header value per request
to get a fresh rate-limit bucket.

**Expected behavior:** Only trust forwarding headers when behind a known,
configured proxy; otherwise use `request.client.host`.

**Recommended solution:** Add a `TRUSTED_PROXY_IPS` setting; only honor
`X-Forwarded-For` when the immediate peer is in that list.

**Estimated effort:** Small (half a day).

**Files likely affected:** `app/api/middleware/rate_limit.py`,
`app/core/settings.py`.

**Acceptance criteria:** Rate-limit bypass via spoofed headers no longer
works in a test that simulates direct (non-proxied) exposure.

---

### 7. SSRF guard doesn't re-validate redirects

**Severity:** Medium
**Category:** Security

**Description:** `assert_public_url` validates the initial hostname/IP, but
`aiohttp` follows redirects by default and neither `_fetch_html` nor
`_download_single_file` re-validate each hop.

**Current behavior:** A public URL that redirects to an internal address
(e.g. `169.254.169.254`, `localhost`) would be silently followed.

**Expected behavior:** Each redirect hop is re-validated, or redirects are
disabled and handled manually.

**Recommended solution:** Pass `allow_redirects=False` and manually
validate each `Location` header against `assert_public_url` before
following it.

**Estimated effort:** Small-Medium (a day, including tests with a mock
redirect chain).

**Files likely affected:** `app/services/web_scraper.py`,
`app/utils/url_safety.py`.

**Acceptance criteria:** A test simulating a redirect to a private IP is
rejected.

---

### 8. Anthropic-style API keys not matched by credential-masking regex

**Severity:** Medium
**Category:** Security

**Description:** `credential_masking.py`'s OpenAI-style pattern requires
16+ contiguous alphanumeric characters after `sk-`; Anthropic keys
(`sk-ant-api03-…`) break on the literal hyphen after `ant`.

**Current behavior:** An Anthropic key embedded mid-sentence in a raw
provider error string would not be masked.

**Expected behavior:** Both key formats are masked.

**Recommended solution:** Broaden the regex to
`sk-(?:ant-)?[0-9A-Za-z\-_]{16,}`.

**Estimated effort:** Trivial (under an hour, plus a test case).

**Files likely affected:** `app/utils/credential_masking.py`,
`tests/test_credential_masking.py`.

**Acceptance criteria:** A test asserting an `sk-ant-…` key is masked
passes.

---

### 9. Blocking synchronous call inside async health-check route

**Severity:** Medium
**Category:** Performance

**Description:** `ncbi_health_check` calls the synchronous
`fetch_paper_metadata` instead of the existing `fetch_paper_metadata_async`,
blocking the event loop for the duration of an NCBI round-trip (with up to
3 retries) on every call.

**Current behavior:** `/api/v1/health/ncbi` can stall the single event loop
for several seconds under NCBI latency.

**Expected behavior:** Uses the async variant already present in the
codebase.

**Recommended solution:** Swap the call in `system.py:191` to
`fetch_paper_metadata_async`.

**Estimated effort:** Trivial (under an hour).

**Files likely affected:** `app/api/routers/system.py`.

**Acceptance criteria:** No regression in existing health-check tests;
confirmed non-blocking via a concurrent-request test.

---

### 10. No retry/backoff on LLM provider calls

**Severity:** Medium
**Category:** Reliability

**Description:** `app/models/llm_provider.py` has no retry/backoff logic,
unlike the PubMed retrieval code which has hand-rolled retries.

**Current behavior:** A single transient LLM API error fails the whole
analysis request.

**Expected behavior:** Transient errors are retried with backoff, matching
the resilience already present on the PubMed leg.

**Recommended solution:** Add `tenacity`-based (or hand-rolled, matching
existing style) retry around `litellm.acompletion` calls for
retryable error classes (timeouts, 5xx, rate limits).

**Estimated effort:** Small-Medium (a day, including tests with a mocked
transient failure).

**Files likely affected:** `app/models/llm_provider.py`.

**Acceptance criteria:** A test simulating one transient failure followed
by success confirms the overall call succeeds.

---

### 11. Container healthcheck doesn't verify real dependencies

**Severity:** Medium
**Category:** Operability

**Description:** The `docker-compose.yml` healthcheck only calls the
shallow top-level `/health`, which returns a timestamp with no DB/cache/
NCBI/LLM reachability check. Deeper checks exist
(`/api/v1/health/ncbi`, `/api/v1/health/gemini`) but aren't wired in.

**Current behavior:** The container reports "healthy" even if the SQLite
cache DB is unwritable or upstream services are unreachable.

**Expected behavior:** The compose healthcheck reflects real dependency
health (or a dedicated lightweight `/health/ready` endpoint that checks
cheap local state like DB writability, without the latency cost of a live
NCBI/LLM call on every healthcheck tick).

**Recommended solution:** Add a `/health/ready` endpoint checking local
dependencies only (not live upstream calls, to avoid healthcheck-induced
LLM spend), and point the compose healthcheck at it.

**Estimated effort:** Small (half a day).

**Files likely affected:** `app/api/routers/system.py`,
`docker-compose.yml`, `docker-compose.prod.yml`.

**Acceptance criteria:** Killing the SQLite cache file's write permission
causes the container healthcheck to fail.
