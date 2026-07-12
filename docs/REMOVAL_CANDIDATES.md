# Removal Candidates

Date: 2026-07-11. Companion document to `docs/PROJECT_AUDIT.md`. Nothing in
this document has been deleted automatically unless explicitly marked as
already done (Taxa Level, see `docs/PROJECT_AUDIT.md`'s "Taxa Level Removal"
section) — everything below is flagged for human review per the audit's
scope.

---

## Safe to Remove

### `app/utils/common.py`

- **Reason:** Zero production call sites. `Config`, `create_cache_key`,
  `save_json`, `load_json`, `validate_pmid`, `get_sequencing_types`,
  `get_body_sites`, `format_prediction_output` are only imported by
  `tests/test_utils.py` and `tests/test_integration.py:271,283` for unit
  testing — no `app/` or `scripts/` module imports this file.
- **Files:** `app/utils/common.py`, `tests/test_utils.py`.
- **Expected impact:** None on running behavior; removes ~130 lines and one
  test file that currently test unreachable code.
- **Confidence:** High.

### `app/utils/field_validator.py`

- **Reason:** Zero production call sites. `EnhancedFieldValidator` and
  `FieldExtractionEnhancer` are only imported by `tests/test_field_validator.py`
  and `tests/test_integration.py:152`. The actual extraction pipeline
  (`app/services/bugsigdb_analyzer/field_extraction.py`) uses the
  `app/normalization/*` normalizers directly and never touches this module.
- **Files:** `app/utils/field_validator.py`, `tests/test_field_validator.py`.
- **Expected impact:** None on running behavior. Note: this module's Taxa
  Level references were already cleaned up as part of this audit's Phase 6
  (for internal consistency) even though the module itself is a removal
  candidate — the two are independent decisions.
- **Confidence:** High.

### `scripts/ops/log_cleanup.py`, `log_dashboard.py`, `performance_monitor.py`

- **Reason:** Each file's own docstring states it was archived / moved out
  of the active backend runtime ("not part of the core backend runtime"),
  yet they still live in `scripts/ops/` rather than an archive directory.
  Zero references anywhere in CI, docs, or other scripts.
- **Files:** `scripts/ops/log_cleanup.py`, `scripts/ops/log_dashboard.py`,
  `scripts/ops/performance_monitor.py`.
- **Expected impact:** None on running behavior. Either delete outright or
  physically move to a `scripts/archive/` directory to match what their own
  docstrings already claim.
- **Confidence:** High.

---

## Needs Manual Review

### `app/api/utils/api_utils.py::extract_taxa()`

- **Reason:** Zero production call sites (only its own tests in
  `tests/test_api_utils.py`) — a generic genus/species-name regex
  extractor, distinct from the now-removed Taxa Level curation field.
- **Dependencies:** None found, but it's plausible this was intended as a
  building block for the differential-abundance-signature feature
  (`has_differential_abundance`/`MicrobialSignature`) and never wired in.
- **Risk:** Low to remove, but worth a quick check with whoever built the
  differential-abundance feature before deleting, in case it's a known gap
  rather than dead code.
- **Recommendation:** Confirm intent, then remove if genuinely unused.

### `app/core/settings.py` vs `app/utils/config.py`

- **Reason:** Not dead code — both are actively used (`config.py` bridges
  to `settings.py` and is imported by ~15 production modules for flat
  constants; `settings.py` is used directly by `scripts/cli.py`'s `settings`
  subcommands). Flagged here only because two sources of truth for the same
  ~20 config knobs is a standing maintenance risk (see
  `docs/PROJECT_AUDIT.md`'s Architecture Assessment), not because either is
  unused.
- **Dependencies:** Both have real, distinct call sites.
- **Risk:** Consolidating would be a non-trivial refactor touching ~15
  files; do not attempt without a dedicated pass and full test coverage.
- **Recommendation:** Leave as-is for now; consider consolidating to a
  single settings source in a future dedicated session, not as an
  incidental cleanup.

### `redis` service in `docker-compose.yml` / `docker-compose.prod.yml`

- **Reason:** Provisioned and hard-depended-on at container startup
  (`depends_on: redis: condition: service_healthy`), but never imported or
  referenced by any code in `app/` — see `docs/PROJECT_AUDIT.md` issue #5.
- **Dependencies:** None functional; `scripts/cli.py:309` references the
  container name only for `docker rm` teardown.
- **Risk:** Low to remove the `depends_on`, but there may be a future plan
  to wire Redis into caching/rate-limiting/job-store (see
  `docs/PROJECT_AUDIT.md` issues #4-#5) — removing it outright forecloses
  that without a decision.
- **Recommendation:** Decide whether Redis has a near-term purpose; if not,
  remove the service and `depends_on` entirely rather than leaving unused
  infrastructure with a hard startup coupling.

### `torchvision` / `torchaudio` in `requirements.txt`

- **Reason:** Declared, never imported anywhere in `app/`/`scripts/`/`tests/`
  (only bare `torch` is imported directly). These add large multi-hundred-MB
  wheels for no confirmed runtime benefit.
- **Dependencies:** Possibly required only to satisfy a pinned
  torch/torchvision/torchaudio compatible-triple convention referenced in a
  CI comment — not confirmed either way.
- **Risk:** Medium — could break a Docker build's dependency resolution if
  the triple-pin theory is correct.
- **Recommendation:** Check the CI comment's rationale before removing; if
  no longer applicable, drop both from `requirements.txt`.

### `html2text` — undeclared dependency (not a removal candidate, but a bug)

- **Reason:** Imported in `app/services/web_scraper.py:14` but not declared
  in `requirements.txt` or `pyproject.toml` at all — currently works only
  because something else pulls it in transitively.
- **Dependencies:** `web_scraper.py`'s HTML-to-Markdown conversion depends
  on it directly.
- **Risk:** A future dependency-tree change could silently break
  `web_scraper.py` if the transitive source of `html2text` goes away.
- **Recommendation:** Add `html2text` to `requirements.txt` explicitly (this
  is an addition, not a removal — flagged here because it surfaced during
  the same dependency audit).

### `UnifiedQA(use_gemini=...)` deprecated constructor argument

- **Reason:** Marked deprecated in favor of `provider='gemini'`, but the
  deprecated form is what 2 of 3 production call sites actually use
  (`app/api/routers/study_analysis.py:140`, `app/api/routers/system.py:46`);
  only `app/services/bugsigdb_analyzer/singletons.py` uses the new form.
- **Dependencies:** Both call sites depend on the deprecated path currently
  working.
- **Risk:** Low to migrate, but it's a 2-call-site behavioral change, not a
  pure deletion.
- **Recommendation:** Migrate the two remaining call sites to
  `provider="gemini"`, then remove the deprecated `use_gemini` parameter in
  a follow-up.

### `analyze_single_field` (backward-compat export)

- **Reason:** Marked "backward compat" in `rag_analysis.py`, exported via
  `bugsigdb_analyzer/__init__.py`, but has zero callers within this repo
  (only self-reference/export).
- **Dependencies:** Unknown — could be a public API surface used by
  external scripts/notebooks not in this repo.
- **Risk:** Medium — removing a "public" export is a breaking change for
  any out-of-repo consumer.
- **Recommendation:** Confirm no external consumer before removing;
  otherwise leave in place.

### `scripts/feedback_aggregate.py`, `scripts/eval/ontology_benchmark.py`

- **Reason:** Listed in `docs/FOLDER_STRUCTURE.md`/`CLAUDE.md` but not
  invoked by any CI workflow or other script (unlike their siblings
  `curator_daily_pipeline.py` and `confusion_matrix_analysis.py`, which
  are wired into automation).
- **Dependencies:** None found in automation; plausibly manual-only tools.
- **Risk:** Low confidence for removal — could be intentional
  manually-invoked utilities for the curator team.
- **Recommendation:** Confirm with the maintainers whether these are still
  used manually before removing.

### `StudyAnalysisResult.to_analyzer_result()` / `to_legacy_dict()` helpers

- **Reason:** Documented in `agent_orchestrator.py` as the intended
  conversion path ("callers can convert via `result.to_analyzer_result()`"),
  but `study_analysis.py` (the only caller of `AgentOrchestrator`) never
  calls it — it returns `StudyAnalysisResult` directly as JSON. Only
  exercised by `tests/test_field_payload_mapping.py`.
- **Dependencies:** Unknown — may be intended for a not-yet-wired curator
  CSV export consumer.
- **Risk:** Medium — don't remove without confirming `curator_table_r`
  (external repo) doesn't expect this shape from a future integration.
- **Recommendation:** Leave in place; revisit if/when a CSV-export path for
  URL-analysis results is built.

### `curator_table_r/data/predictions.csv` path written by CI

- **Reason:** `.github/workflows/curator-daily-update.yml` writes/commits to
  `curator_table_r/data/predictions.csv`, but that directory does not exist
  in this repo's history (`curator_table_r` is a separate, external repo per
  project context). `scripts/curator_daily_pipeline.py` creates the
  directory with `mkdir(parents=True)`, so the workflow won't crash — it
  will just create and commit a new `curator_table_r/` tree inside *this*
  repo daily, which likely isn't the intended destination.
- **Dependencies:** CI automation; `docs/CURATOR_DESK_CSV_FORMAT.md`
  already references confusion around this naming.
- **Risk:** Medium — may be causing silent, unwanted daily commits inside
  this repo rather than the intended external `curator-desk` repo.
- **Recommendation:** Verify the workflow's actual behavior on its next
  scheduled run and correct the destination path if it's writing to the
  wrong repo.

---

## Orphaned/Scratch Files at Repo Root (left untouched, confirmed not required)

These are untracked (`git status` shows `??`, `git log --follow` returns
empty for each — never committed) and not referenced by any code or docs as
required inputs:

- `pmids.xls`, `predictions.csv` — filenames match exact examples in
  `docs/CLI_DOCUMENTATION.md`/`curator_table/README.md`, almost certainly
  local run output from following the docs.
- `managed_context/`, `test_suite_analysis/` — each contains only a small
  `metadata.json`, not referenced anywhere.

No action taken or recommended on these — they appear to be the requester's
own local working files, not something for this audit to touch.
