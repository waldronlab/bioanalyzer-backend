# BioAnalyzer-Backend & curator_table_r Renovation — Final Deliverables

**Status: a second, substantially larger renovation pass on top of the
first.** This report supersedes the version written after the first pass
(7 milestones). That version is preserved in git history
(`79ae786`) if you want the prior snapshot. This update reflects the real,
verified state after a second pass covering dependency cleanup, dead-code
removal, a performance fix, logging/error-handling fixes, two new test
files (closing the single largest test-coverage gap), curator_table_r's
first-ever test suite (which caught a real data-loss bug), and a
documentation sweep for staleness. As before: written against verified
current state, not aspiration.

All work is on local, unpushed feature branches:
`BioAnalyzer-Backend@chore/repo-hygiene-and-fixes` (21 commits ahead of
`main`, plus this pass's changes staged/pending commit) and
`curator_table_r@fix/taxa-level-schema-and-renv` (6 commits ahead of
`main`, plus this pass's changes pending commit). Nothing has been pushed
or merged; both branches need review before that happens. Per explicit
instruction this pass, all changes were accumulated as working-tree edits
and will be committed in logical groups in one batch rather than
incrementally — see §21.

---

## 1. Executive Summary

This pass picked up from the first report's "Remaining Technical Debt" /
"Future Recommendations" list and worked through it systematically:
dependency audit (done), dead code elimination (done), performance review
(done, found and fixed one real event-loop-blocking issue), logging review
(done, found and fixed credential-masking gaps), error handling review
(done), test coverage for the previously-zero-coverage URL-analysis
pipeline (done, 33 new tests), curator_table_r's first test suite (done,
24 new tests — which immediately caught a real bug), a CSV-pipeline
review against the newly-committed `SPEC.md` (done, found a real internal
inconsistency in that document), a style-consistency pass (done, found
nothing — both repos were already clean), and a documentation sweep (done,
found and fixed several stale references to files deleted in this same
pass).

One genuinely significant bug was found and fixed in `curator_table_r`
while writing its first tests: a single malformed PMID in the source CSV
silently caused the *entire* curator table to render empty (not just drop
that one row) — see §7.6.

What this pass still does **not** cover, by explicit user decision (not a
deferral — confirmed declined, see §18): aggressive refactoring,
folder/package restructuring, evaluating or performing an R-package
conversion for `curator_table_r`, any dependency *version upgrade* (as
opposed to removing confirmed-dead dependencies or fixing version-pin
inconsistencies, which were done), and deciding CI gating policy for the
new tests.

---

## 2. Dependency Audit (BioAnalyzer-Backend Python side — closes a gap from the first report)

`config/requirements.txt`, `pyproject.toml`, and `setup.py` were all
checked consistently against actual `import` usage in `app/`, `scripts/`,
and `main.py`.

**Removed (confirmed zero usage via direct grep, not just an audit
agent's claim):** `biopython`, `transformers`, `tokenizers`,
`sentencepiece`, `accelerate`, `datasets`, `python-multipart`,
`typing-extensions`, `lxml`, `websockets`, `wsproto`, `h11`, `httptools`,
`openpyxl`, `xlrd`, `aiofiles`, `tqdm`, `click`, `watchfiles[watchdog]` —
18 packages, none imported anywhere. The networking-stack entries
(`websockets`, `wsproto`, `h11`, `httptools`) are already pulled in
transitively by `uvicorn[standard]` (still present, untouched), so removing
the redundant top-level pins doesn't change what actually gets installed —
it only removes duplicate, independently-drifting version constraints.

**Added (confirmed real, previously undeclared anywhere):**
`sentence-transformers>=2.2.0` (used only in
`tests/test_integration_workflow.py`, guarded by try/except + skip) and
`pytest-asyncio>=0.21.0` (moved from a misleadingly-labeled "Curator table"
comment to a new "Test-only" section — both packages are test-only, not
runtime dependencies, and are now labeled as such).

Also fixed: the `cli` extras group in `pyproject.toml`/`setup.py`
(`click`/`rich`/`tabulate` — all confirmed unused, no docs reference
installing it) was removed entirely; placeholder URLs
(`your-repo/bioanalyzer-backend`, `your-repo/bioanalyzer-package`) in both
files were corrected to the real `waldronlab/bioanalyzer-backend` remote.

**Verified safe:** full Docker test suite (333 tests, see §13) run against
the actual installed environment with these exact import statements
removed from the source files that used to import them — not just a static
grep claim.

**Not done:** no dependency *version* upgrades (explicitly gated, see
§18), no `pip-audit`/`safety` CVE scan (`bandit` and these tools aren't
installed in this sandbox or the test Docker image; this remains a real
gap from the first report, still open).

---

## 3. Dead Code Elimination

**Removed:**

- `app/services/pubmed_retrieval_service.py` (273 lines) — confirmed zero
  importers anywhere (grep for every plausible import form); an orphaned
  thin wrapper superseded by `standalone_pubmed_retriever.py`, which is
  what `scripts/cli.py` actually imports.
- `app/utils/field_validator.py`'s `FieldValidationResult` dataclass —
  confirmed zero references; the larger `EnhancedFieldValidator`/
  `FieldExtractionEnhancer` classes in the same file were investigated and
  found to be exercised only by their own test files, never from
  production code — left in place and flagged (§9) rather than removed,
  since that's a bigger, less mechanical call than removing one dead
  dataclass.
- `app/utils/performance_logger.py`'s `log_performance()` decorator (98
  lines, the entire tail of the file) — confirmed zero callers, distinct
  from the actively-used `log_performance_metrics()` method in the same
  file.
- `app/utils/config.py`'s `check_required_vars()` and
  `validate_gemini_key()` — confirmed zero callers each. (`validate_env_vars()`,
  which looked similar, was *not* removed — it's genuinely called at
  module-import time.)
- Unused imports, each individually confirmed before removal: `Tuple`/
  `Union` in `field_validator.py`; `wraps`/`Path`/`Optional`/`asyncio` in
  `performance_logger.py` (after the decorator removal made `wraps` dead
  too); `chunk_text`/`Doc` in `converter_service.py`; `Path`/`Doc`/`Docs`
  in `vector_store_service.py`; `requests` in `web_scraper.py`.
- `docs/CLEANUP_CHECKLIST.md` — a stale internal planning checklist whose
  entire premise was already executed (all 5 "Phase 1" files it
  instructs you to remove are already gone; its "Phase 2" question, about
  whether to keep `pubmed_retrieval_service.py`, is now moot since that
  file no longer exists). Left in the repo it would actively mislead a
  future contributor into thinking obsolete cleanup work is still pending.

**Verified:** full Docker test suite (333 passed) plus `black`/`flake8`
clean on every touched file, run after each removal, not just at the end.

**Not removed, flagged instead (deliberately, not an oversight):**

- `EnhancedFieldValidator`/`FieldExtractionEnhancer` in `field_validator.py`
  — tested but never invoked from `app/services/`, `scripts/`, or
  `main.py`. Bigger, riskier removal than the dataclass; needs a human
  decision on whether this was meant to be wired in somewhere and isn't,
  or is genuinely obsolete.
- `curator_table_r/R/feedback.R` — 6 functions, confirmed zero callers
  anywhere in the R repo, but self-documented in its own header as "for
  local or Shiny use" (a deployment mode that isn't currently active; the
  real deployed site uses `js/feedback-form.js` instead). Per this
  session's standing rule — things self-documented as "intentionally kept
  for X reason" get flagged, not unilaterally deleted — left in place.

---

## 4. Security Review (second pass)

Building on the first report's one fix (the credential-leak in
`study_analysis.py`), this pass found and fixed three more:

1. **SSRF gap** in the URL-analysis pipeline — `app/services/web_scraper.py`
   and `image_processor.py` fetched user-supplied URLs (and any image URLs
   scraped from them) with no check that the resolved address was public.
   New `app/utils/url_safety.py::assert_public_url()` resolves the
   hostname and rejects private/loopback/link-local/multicast/reserved/
   unspecified addresses before any fetch; wired into both `_fetch_html()`/
   `_download_single_file()` and `_download_image()`.
2. **CORS wildcard + credentials** — `app/api/app.py`'s `CORSMiddleware`
   had `allow_origins=["*"]` (non-production) combined with
   `allow_credentials=True`. An earlier security-audit subagent claimed
   this wasn't practically exploitable because "browsers reject the
   combination" — independently re-verified and found **incorrect**:
   Starlette's `CORSMiddleware` (like most implementations) works around
   that browser restriction by reflecting the request's actual `Origin`
   header instead of sending a literal `"*"`, meaning any origin could
   make credentialed requests. Fixed by removing `allow_credentials=True`
   (verified: this app has no cookie/session-based auth anywhere, so
   there's no legitimate use of credentialed cross-origin requests to
   preserve).
3. **Predictable shared-`/tmp` directories** — `web_scraper.py`'s download
   directory and `agent_orchestrator.py`'s Paper-QA directory both used
   fixed, predictable names directly under the shared, world-writable
   system temp dir, created with no restrictive permissions. Low severity
   (needs local multi-user access, not network-exploitable) but real.
   Fixed with `mode=0o700` on creation plus an explicit `os.chmod()`
   afterward (the `mode=` kwarg only applies at creation time, so a
   pre-existing directory from an earlier run needed the explicit chmod
   too).

**Not done:** still no `pip-audit`/`safety`/`bandit` CVE scan (tooling not
available in this sandbox); no path-traversal, subprocess, or
deserialization review beyond what surfaced incidentally.

---

## 5. Performance Review

Dispatched a verification-disciplined audit (cross-checked every finding
against the actual code before acting, consistent with this session's
"don't trust an audit agent's claim without re-confirming it" rule).

**Fixed — genuinely blocks the event loop today, not just "would matter at
scale":** `app/normalization/host_species.py` and `ols.py` (used by
`condition.py`/`body_site.py`) make blocking `requests.get()` + `time.sleep()`
calls on their NCBI/OLS network-fallback paths (reached whenever a value
isn't in the static local lookup dict). These were called synchronously
from inside `async def analyze_paper_simple`/`analyze_paper_with_rag` (via
`_field_results_from_unified_payload()`), with no `asyncio.to_thread`/
`run_in_executor` wrapper — meaning an uncached field lookup could stall
*every other concurrent request* on that worker for up to ~1 second.
Fixed by wrapping the synchronous call site in `asyncio.to_thread()` at
both call sites in `bugsigdb_analyzer.py`.

**Found, lower severity, not fixed (flagged):** the URL-analysis
pipeline's image-processing loop (`study_analysis.py`) awaits each image's
download/description sequentially instead of using `asyncio.gather()`;
bounded by the documented 10-image cap, so real but limited impact — left
as a future optimization, not bundled into this pass.

**Found and fixed on the R side:** `curator_table_r/R/data.R`'s
`normalize_dataset()` called `apply(df, 1, priority_score)`, which
coerces the whole data.frame to a character matrix and re-parses each
already-normalized status cell per row — redundant, since the same
columns were just normalized two lines above. Replaced with a vectorized
`vapply()` + `rowSums()` equivalent; verified byte-for-byte identical
output against the original row-by-row version on real data
(`all.equal()` true, only difference was an incidental row-name attribute
nothing downstream reads).

**Checked, no issue found:** `cache_manager.py`'s per-call
`sqlite3.connect()` (intentional, documented, cheap for SQLite);
`web_scraper.py`/`image_processor.py` correctly use `aiohttp`, not
blocking `requests`.

---

## 6. Logging Review

**Fixed — silent failures with zero diagnostic trail (`except Exception:
pass`, no logging at all):**

- `app/api/routers/system.py` — cache-hit-rate computation in the
  `/metrics` endpoint; now logs a warning.
- `app/services/bugsigdb_analyzer.py` — RAG rerank-metrics computation;
  now logs a masked warning (routed through `mask_exception_message`
  since the underlying call can touch LLM provider config).
- `curator_table_r/R/data.R::load_data()` — CSV/Parquet read failures
  silently returned an empty data.frame with zero `message()`/`warning()`
  output; a curator pointing the page at a malformed file would just see
  an empty table with no clue why. Now emits `message("Failed to load
  ", path, ": ", conditionMessage(e))`, matching the pattern already used
  elsewhere in the R codebase.

**Fixed — `print()` used where library code should log:**
`app/utils/config.py`'s missing-env-vars warning. Note: this function runs
at *module-import time*, before this same module's own `logger` variable
exists (it's assigned later in the file, at the point `setup_logging()` is
called) — using `logger.warning()` directly would have crashed with
`NameError`. Used `logging.getLogger(__name__)` instead, which doesn't
depend on that module-level assignment order.

**Fixed — inconsistent credential masking in `app/models/unified_qa.py`:**
several `except Exception as e` blocks around `LLMProviderManager`/LiteLLM
calls logged or returned the raw exception (`{e}`, `str(e)`) instead of
routing through `mask_exception_message()`, even though `llm_provider.py`
deliberately masks these same exception types because LiteLLM errors can
embed API keys/URLs. Two of these (`ask_question()`, `analyze_paper()`)
even put the raw string into a dict returned up the call chain — a
real leak path, not just an inconsistent log line. All 8 call sites fixed
to use the already-established masking helper consistently.

---

## 7. Error Handling Review

Folded into §6 above (most error-handling gaps found this pass were
logging gaps — silent swallows or unmasked leaks). One additional item
not yet mentioned:

**A real data-loss bug, found while writing curator_table_r's first
tests** (not from a code-reading audit — this is exactly the kind of bug
that's invisible without a test exercising the actual failure path):

`R/data.R::normalize_dataset()`'s PMID-coercion step was:

```r
df$PMID <- tryCatch(
  as.integer(as.numeric(df$PMID)),
  warning = function(e) NA,
  error = function(e) NA
)
```

`tryCatch`'s `warning` handler replaces the result of the *entire*
expression the moment **any** warning occurs anywhere inside it — and
`as.numeric()` on a vector with even one unparseable element raises
exactly one such warning for the whole call, not per-element. So
`df$PMID` became a single scalar `NA` (then recycled to every row) the
instant *any one* PMID in the file was malformed — and the very next line,
`df[!is.na(df$PMID), , drop = FALSE]`, then dropped **every row**, not
just the bad one. Verified directly: corrupting one PMID out of 29 real
rows in `data/sample.csv` reduced the rendered table from 29 rows to 0.

Fixed with `suppressWarnings(as.integer(as.numeric(df$PMID)))` — lets
R's actual per-element `NA` coercion happen as intended, only suppressing
the (now harmless, since the surrounding code already filters `NA` rows
explicitly) warning message. Verified: the same corrupted-data test case
now correctly drops only the 1 bad row, keeping the other 28.

This is the single most consequential fix in this pass — a silent,
total-data-loss failure mode that would have been very hard to notice in
production (the page renders successfully, just empty, with the existing
missing-status-columns notice not even triggering since it's a different
code path).

---

## 8. Test Coverage Added

**`tests/test_agent_orchestrator.py`** (new, 23 tests) — covers
`AgentOrchestrator`, previously **zero** test coverage (confirmed via
grep, documented as a known gap in the first report). Tests the pure
helpers (`_field_result_from_raw`, `_avg_confidence`,
`_check_missing_fields`), the experiment/signature response parsers
(including verifying that parsed values correctly flow through the real
`app/normalization/*` normalizers — caught several of my own first-draft
test assertions that assumed raw, un-normalized values), and
`analyze_study()` end-to-end with `paperqa.agent_query()` mocked out
(real network/LLM calls aren't available in any test environment for this
repo).

**`tests/test_study_analysis.py`** (new, 10 tests) — covers
`app/api/routers/study_analysis.py`, also previously zero coverage. Tests
the three router endpoints (404/400/500 cases, happy path) via
`TestClient`, and `process_url_analysis()`'s full 7-step background task
with all five services mocked. Includes a dedicated regression test for
the credential-leak fix from the first report (§7.3 there): asserts that
a failure containing a fake API-key-shaped string in its exception text
does **not** appear in `job_store[job_id].error` — confirmed this test
actually exercises the masking (verified `mask_exception_message()`
genuinely redacts the test secret, not just that the test happens to
pass).

**`curator_table_r/tests/` — first test suite this repo has ever had**
(new, 24 tests, `testthat`). Covers `R/config.R` (schema generation,
explicitly asserts the 5-field/no-Taxa-Level invariant from the first
report's bug fix) and `R/data.R` (status normalization, priority scoring,
PMID link generation, `load_data()`/`normalize_dataset()` including the
malformed-file and malformed-PMID paths). This suite is what caught the
§7 data-loss bug — writing a test for "does `normalize_dataset()` drop
just the bad row" immediately failed against the *un-fixed* code, which
is how the bug was found, not the other way around. `testthat` was
installed into the renv environment and added to `renv.lock` via the same
explicit-`packages=` snapshot approach established in the first report's
R dependency fix (`renv::dependencies()` doesn't auto-detect it either,
consistent with that known scanner limitation). Both `ci.yml` and
`quarto-publish.yml` now run `Rscript tests/testthat.R` before rendering.

**Current verified state (Docker, full dependency set including
`paper-qa`, not the partial host-Python state from the first report):**
333 tests passed, 1 skipped, 0 failed — up from 300 before this pass's two
new Python test files (the +33 are exactly the new tests, no regressions
in the existing 300). `curator_table_r`: 0 tests before this pass, 33
assertions across 24 `test_that()` blocks now, all passing, 0 failures,
0 warnings (after fixing the two test cases whose own premises were
initially wrong — `read.csv()` turned out to be far more lenient about
malformed CSV content than expected; switched to a directory-named-`.csv`
trick to reliably trigger the real error path instead).

---

## 9. Flagged for User Decision (not unilaterally resolved)

1. **`curator_table_r/SPEC.md` has an internal inconsistency.** §6.2
   ("Required Columns") correctly states there are 5 prediction fields
   (Taxa Level excluded — matches the shipped code and the first report's
   bug fix). §9.2 ("Feedback Schema") contradicts this: it claims "24
   total" feedback columns and explicitly lists
   `pred__Taxa_Level_Status`/`true__Taxa_Level_Status`/
   `col_feedback__Taxa_Level_Status`. The real, shipped
   `feedback_schema()` (verified directly, and now covered by a test
   asserting exactly this) produces 21 columns (6 base + 5×3 prefixed),
   with no Taxa Level anywhere. Since `SPEC.md` was provided verbatim as
   an already-negotiated document ("result of lengthy back-and-forth
   between Claude and Levi"), it was **not edited** as part of this pass —
   this is flagged for whoever owns that negotiation to correct §9.2 to
   match §6.2 and the real code.
2. **`curator_table_r/SPEC.md` §6.2's documented CSV schema is narrower
   than the real `curator_desk_csv` output**, but verified this is
   *intentional scope*, not an error: §6.2 documents the curator-facing
   *display* columns (matches `index.qmd`'s `DISPLAY_COLUMNS` exactly),
   while the full CSV (`scripts/cli_rendering.py::_render_curator_desk_csv`,
   26 columns including per-field ontology ID/mapping-confidence columns,
   `Summary`, `Processing Time`) is already fully and correctly documented
   separately in `docs/CURATOR_DESK_CSV_FORMAT.md` on the Python side. No
   action needed — noted here so it isn't mistaken for a gap on a future
   pass.
3. **`curator_table_r/R/feedback.R`** — see §3, flagged not deleted.
4. **`app/utils/field_validator.py`'s `EnhancedFieldValidator`/
   `FieldExtractionEnhancer`** — see §3, flagged not deleted.

---

## 10. Documentation Sweep

Found and fixed several stale references, mostly to files that no longer
exist (some deleted in this very pass, others apparently removed in
earlier, undocumented work):

- `CLAUDE.md` and `docs/ARCHITECTURE.md` both still listed
  `pubmed_retrieval_service.py` (deleted in §3 of this pass) as a real
  module — fixed.
- `README.md`'s "Validation & Benchmarking" section and
  `docs/CURATOR_TABLE_DESIGN.md` both referenced `align_pmids.py` and
  `create_validation_dataset.py` as real, runnable tools — neither exists
  anywhere in the repo (confirmed via `find`), and no successor script
  was found either. Rather than invent a replacement, both docs now state
  plainly that these no longer exist, instead of leaving instructions that
  would fail partway through if followed.
- `docs/CLEANUP_CHECKLIST.md` deleted — see §3.
- `curator_table_r/README.md` — added a "Tests" section and updated the
  file-layout listing to include the new `tests/` directory.

**Not done:** no full re-read of every doc file for staleness (would be a
large, separate effort); this sweep was targeted at references to files
touched/removed in this pass plus what surfaced while reviewing the CSV
pipeline (§9).

---

## 11. Style Consistency Pass

Ran `black --check`/`flake8` across the **entire** `app/`, `tests/`,
`scripts/cli.py`, `scripts/main.py` (not just files touched this pass) —
both fully clean, 89 files, zero diffs, zero lint findings. On the R side,
ran `lintr::lint_dir("R", ...)` (with line-length/naming/commented-code
linters disabled, matching this project having no existing R style
convention to violate) — found and fixed one minor hanging-indent issue
introduced by this pass's own `vapply()` rewrite in `data.R`; the
pre-existing `feedback.R` has one similar minor finding, left alone since
that file is itself flagged for possible deletion (§3/§9).

**Conclusion: both repos were already in good style shape** going into
this pass (consistent with the first report's "Documentation: 80" score
reflecting generally careful prior work) — this item closes clean rather
than finding a backlog of fixes.

---

## 12. CSV Pipeline Review (against the now-committed `SPEC.md`)

Cross-checked `SPEC.md` §6 (Curator Desk Table) and §9 (Feedback Schema)
against the real producing/consuming code on both sides
(`scripts/cli_rendering.py::_render_curator_desk_csv`,
`curator_table_r/R/config.R`, `curator_table_r/index.qmd`'s
`DISPLAY_COLUMNS`). Findings are in §9 above (the Taxa Level
inconsistency, and the display-vs-full-CSV scope clarification). No
further discrepancies found — the 5-field spec, the `pred__`/`true__`/
`col_feedback__` naming convention, and the Priority-score formula all
match the real, shipped code exactly.

---

## 13. Full Verification Summary

- **Python:** full test suite run inside the project's actual Docker
  image (`bioanalyzer-package:latest`, has `paper-qa` and every other
  declared dependency installed — unlike this sandbox's host Python,
  which is missing several heavy deps and was the reason the first
  report's test run had 6 files fail to collect). **333 passed, 1
  skipped, 0 failed.** `black --check`/`flake8` clean across the whole
  `app/`/`tests/`/`scripts/cli.py`/`scripts/main.py` tree.
- **R:** `Rscript tests/testthat.R` — 24 `test_that()` blocks, all
  passing, 0 failures, 0 warnings. `quarto render` succeeds; output
  verified to actually contain the rendered table (spot-checked with both
  normal data and deliberately corrupted data for the §7 bug fix).
  `lintr` clean.
- Every fix in this report was verified against real data/real execution,
  not just read-through — re-stated here because several findings in this
  pass (the PMID bug, the masking gaps, the unused-import removals) were
  specifically things that *looked* fine on a read-through and only
  surfaced under direct testing.

---

## 14. Breaking Changes

None to public behavior. The PMID-coercion fix (§7) changes behavior, but
strictly from "silently broken" (drops all rows on any malformed PMID) to
"correct" (drops only the malformed row) — this is a bug fix, not a
breaking change, and was flagged explicitly per the standing rule that
data-correctness-altering changes get called out before being applied.

---

## 15. Files Removed (this pass)

- `app/services/pubmed_retrieval_service.py`
- `docs/CLEANUP_CHECKLIST.md`
- (R) nothing removed; `R/feedback.R` was considered and explicitly left
  in place, flagged.

## 16. Files Added (this pass)

- `app/utils/url_safety.py`
- `tests/test_agent_orchestrator.py`
- `tests/test_study_analysis.py`
- `curator_table_r/tests/testthat.R`,
  `curator_table_r/tests/testthat/test-data.R`,
  `curator_table_r/tests/testthat/test-config.R`

## 17. Folder Restructuring

None performed — explicitly gated as high-risk per this pass's working
rules; see §18.

---

## 18. High-Risk Items — Explicitly Declined (user decision, not just deferred)

These were raised as gated/needs-sign-off items; the user has since
confirmed none of them should be pursued. This is now a closed decision,
not an open question carried to a future pass:

1. **Aggressive refactoring** beyond the mechanical dead-code removal in
   §3 — no function/class restructuring, no design-pattern changes.
2. **Folder/package restructuring** for either repo.
3. **R-package conversion evaluation for `curator_table_r`** — raised in
   the original request; will not be evaluated.
4. **Dependency version upgrades** — distinct from what *was* done
   (removing confirmed-dead dependencies, adding confirmed-missing ones,
   fixing version-pin inconsistencies/placeholder URLs). No package's
   pinned minimum version will be bumped.
5. **CI safety-check gating policy** (e.g., making the new R tests or a
   `pip-audit` run a hard CI gate vs. advisory) — the new R tests *do* now
   run in CI (§8) and report failures, but whether a failure should block
   merge/deploy will not be decided or changed.

---

## 19. Final Quality Scores (0–100)

Updated from the first report's scores. Each includes the one-line reason
it isn't higher — and, where it changed, why.

| Dimension | Score | Δ | Why not higher |
|---|---|---|---|
| Architecture | 60 | — | Unchanged this pass — no structural work attempted (§17/§18) |
| Maintainability | 68 | +10 | Real dead-code/dependency cleanup landed; still no broader refactor |
| Readability | 64 | +2 | Marginal — mostly logging/error-handling clarity, not a readability-focused pass |
| Security | 62 | +12 | SSRF, CORS, predictable-tmp-dir fixes landed; still no CVE/injection scan |
| Reliability | 68 | +12 | The PMID data-loss bug (§7) and masking-consistency fixes are real, verified reliability wins |
| Performance | 48 | +8 | One real, verified event-loop-blocking fix; still no profiling or broader review |
| Documentation | 82 | +2 | Stale-reference sweep (§10) closes small real gaps; still not a full re-read |
| Testing | 62 | +17 | Closed the single largest gap (one whole pipeline + one whole repo); R `paperqa`-path tests still depend on Docker, not runnable on bare host |
| Scientific correctness | 65 | — | Unchanged here — the data-loss bug (§7) is a data-integrity fix, not a scientific-extraction-correctness one; no new extraction-logic bugs found this pass |
| Overall production readiness | 60 | +10 | Real, verified, two-repo improvements; high-risk structural items (§18) and the CVE-scan gap remain; nothing pushed/merged yet |

---

## 20. Future Recommendations

In rough priority order, carried forward and updated:

1. **Get CVE-scan tooling (`pip-audit`/`safety`/`bandit`) into the actual
   dev/CI environment** — still never run; this sandbox and the test
   Docker image both lack it.
2. **Decide on the 4 items flagged in §9** — two are genuine spec-document
   decisions (not code), two are "tested but never invoked from
   production" code questions.
3. **`job_store`'s cross-worker persistence** (carried over from the first
   report, still unresolved) — would block correctly deploying
   `/analyze-url` behind multiple workers/replicas.

The 5 items in §18 (refactoring, restructuring, R-package conversion,
dependency version upgrades, CI gating policy) are **not** on this list —
the user has explicitly declined all of them; they're a closed decision,
not a backlog item.

## 21. Commit Plan

All changes in this pass were accumulated as uncommitted working-tree
edits per explicit instruction, rather than committed incrementally. They
will be committed in logical groups (dependency/dead-code cleanup;
security fixes already landed earlier in this branch's history;
performance/logging/error-handling fixes; new test files; R test suite +
bug fix; documentation sweep) immediately after this report is finalized.
**Pushing to the remote requires separate, explicit confirmation** — per
the standing session-wide rule, committing locally is not the same
approval as pushing.

---

*Generated from the actual git history of both branches, direct
verification via Docker-based test runs and real `quarto render`/`Rscript`
execution, and line-by-line citation of every finding against the current
code — not from memory of intended work.*
