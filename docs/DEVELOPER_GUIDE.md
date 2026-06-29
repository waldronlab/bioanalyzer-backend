# Developer Guide

Practical, task-oriented notes for extending BioAnalyzer-Backend. For *what
exists today*, see [`CLAUDE.md`](../CLAUDE.md) (architecture/module
reference) and [`FOLDER_STRUCTURE.md`](FOLDER_STRUCTURE.md) (directory map).
This guide is about *how to add to it* without breaking conventions that
aren't obvious from reading any single file.

## Environment

```bash
pip install -e .[dev]          # local install with test/lint tooling
./run_tests.sh                 # full suite, inside the prebuilt Docker image (recommended)
pytest tests/ -v                # if you have the full dependency set installed locally
```

Docker is recommended for day-to-day work because the full dependency set
(PyTorch, transformers, sentence-transformers) is heavy; the prebuilt image
already has it. Either path runs the same tests.

## Extending the field-extraction pipeline

The six BugSigDB curation fields (Host Species, Body Site, Condition,
Sequencing Type, Sample Size, Taxa Level) flow through a fixed shape end to
end: `app/services/bugsigdb_analyzer/` extracts raw text per field via an
LLM call, then `app/normalization/*.py` maps that raw text to a controlled
vocabulary term, returning a `NormalizedTerm` (`app/normalization/types.py`).

**If you're adding a new normalization rule to an existing field** (e.g. a
new disease alias in `condition.py`, a new sequencing-method alias in
`sequencing_type.py`): add the entry to that module's lookup dict. Two
things to check before you do:

1. **Longest-match lookups pick the longest matching *key*, not the most
   scientifically specific one.** `host_species.py` and `condition.py` both
   had real bugs from this: short, specific terms ("mice", "IBD") lost to
   longer, generic ones ("adult", "controls") that happened to also appear
   in the same sentence. Before adding a new key, ask whether it's a
   generic word that could co-occur with an unrelated specific term in the
   same sentence - if so, it needs the same kind of "specific terms win"
   guard those two modules now have, not a bare lookup entry.
2. Check whether the term is already covered by a *different* key with
   different casing/pluralization rather than adding a near-duplicate.

**If you're adding a wholly new field** (beyond the six BugSigDB fields):
expect to touch, in order: the extraction prompt
(`bugsigdb_analyzer/constants.py`'s `EXTRACTION_PROMPT`), the payload-to-
field-result mapping (`field_extraction.py`'s
`_field_results_from_unified_payload`), a new `app/normalization/<field>.py`
if it needs controlled-vocabulary mapping, the CSV/table column lists in
`scripts/cli_rendering.py`, and the curator-desk CSV contract
(`docs/CURATOR_DESK_CSV_FORMAT.md`) - that last one is consumed by
`curator_table`/`curator_table_r`, so a field rename or column reorder there
is a cross-repo breaking change, not just a local one.

## The `_pkg` self-import pattern (why it exists, when you need it)

`app/services/bugsigdb_analyzer/singletons.py`, `simple_analysis.py`, and
`rag_analysis.py` all start with:

```python
import app.services.bugsigdb_analyzer as _pkg
...
cache_manager = _pkg.get_cache_manager()
```

instead of `from .singletons import get_cache_manager`. This isn't
stylistic - `tests/test_integration.py` patches names like
`@patch("app.services.bugsigdb_analyzer.PubMedRetriever")`, i.e. it patches
the attribute on the *package's* namespace. A direct `from .singletons
import get_cache_manager` binds the name at import time inside that
submodule, and `@patch` on the package wouldn't reach it. Going through
`_pkg.X(...)` defers the lookup to call time, against the package's own
(patchable) namespace.

**If you add a new submodule to this package that needs to call another
function the package re-exports** (anything listed in `__init__.py`'s
`__all__`), use the same `import app.services.bugsigdb_analyzer as _pkg`
pattern rather than a direct relative import - otherwise a test patching
the package-level name silently won't affect your new code.

## Credential masking is mandatory on every exception you log or return

`app/utils/credential_masking.py::mask_exception_message()` must wrap any
exception text that reaches a log line, a returned dict, or an HTTP
response. This has been the single most common bug class found in this
codebase's history (10+ call sites fixed across `bugsigdb_analyzer.py`,
`standalone_pubmed_retriever.py`, `gemini_qa.py`, `study_analysis.py`) -
`except Exception as e: logger.warning(f"...: {e}")` is the wrong pattern
even when the immediate exception looks harmless, because the *type* of
exception that lands in that branch isn't fixed - a future change upstream
could start raising something that embeds a credential, and nothing here
would catch it.

```python
# Wrong
except Exception as e:
    logger.warning(f"Thing failed: {e}")

# Right
except Exception as e:
    logger.warning("Thing failed: %s", mask_exception_message(e))
```

Routers have their own exception handling only when they bypass
`app/api/app.py`'s global handler (currently just
`study_analysis.py`, documented in `CLAUDE.md`) - everywhere else, the
global handler already calls `mask_exception_message`, but any *local*
try/except inside a service function still needs its own call before the
masked-or-not text gets logged or stored (e.g. in `job_store`).

## Test conventions

- Tests mock external calls (PubMed, LLM providers) - there's no live
  network/LLM dependency in the suite. Follow the existing
  `monkeypatch.setattr(requests, "get", ...)` / `@patch(...)` patterns in
  the test file for the module you're touching rather than inventing a new
  mocking approach.
- Markers: `unit`, `integration`, `smoke`, `regression`, `asyncio` (see
  `pytest -m <marker>`).
- When you fix a bug found by reading code (not by a failing test), add a
  regression test in the same commit. Every fix in this codebase's history
  that didn't do this had to be re-verified later anyway - it's cheaper to
  write the test once, at the point where you already understand exactly
  what was wrong.
- Run the *full* suite with `--cov=app --cov-report=term-missing` rather
  than scoping `--cov` to a single submodule when checking coverage for one
  file - scoping coverage while the test imports the full FastAPI app (which
  imports many other submodules) can trigger spurious collection errors
  unrelated to your change.

## Before opening a PR

```bash
black app/ tests/ scripts/cli.py scripts/main.py
flake8 app/ tests/ scripts/cli.py scripts/main.py --max-line-length=120 \
  --extend-ignore=E203,W503,E501,F401,F403,F811,F841,W291,W293,E402,E722,F541
mypy -p app --ignore-missing-imports --no-strict-optional --show-error-codes  # informational; CI doesn't block on this
bandit -r app/ -ll
pytest tests/ -v
```

See [`CONTRIBUTING.md`](../CONTRIBUTING.md) for the PR process itself.
