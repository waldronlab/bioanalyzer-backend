# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

BioAnalyzer extracts BugSigDB curation fields (Host Species, Body Site, Condition, Sequencing Type, Sample Size, Taxa Level) from scientific papers. It pulls metadata/full text from PubMed/PMC, then uses an LLM (via LiteLLM — Gemini, OpenAI, Anthropic, or Ollama) to determine whether each field is `PRESENT`, `PARTIALLY_PRESENT`, or `ABSENT`, with a confidence score. There is a FastAPI service, a CLI (`bioanalyzer` / `BioAnalyzer` / `scripts/cli.py`), and a Streamlit curator review table.

## Commands

### Tests

CI runs plain `pytest` on the host (not Docker) — see `.github/workflows/ci.yml`. Locally, this requires the full dependency set (PyTorch, transformers, etc.), so Docker is the recommended path for day-to-day work; either is fine for actually invoking pytest:

```bash
# In Docker (matches CI's runtime environment, avoids installing torch locally)
./run_tests.sh                                  # full suite
./run_tests.sh tests/test_utils.py -v           # single file (extra args pass through to pytest)

# Directly with pytest (if deps are installed, e.g. inside a configured venv or container)
pytest tests/ -v
pytest tests/test_utils.py -v                   # single file
pytest tests/test_utils.py::test_name -v        # single test
pytest -m unit                                  # by marker: unit | integration | smoke | regression | asyncio
pytest tests/ --cov=app --cov-report=term-missing
```

`conftest.py` (root) and `tests/conftest.py` exist solely to force `app` onto `sys.path`/`PYTHONPATH` so tests import correctly both on the host and inside Docker — don't remove them even though they look redundant with `pytest.ini`'s `pythonpath = .`.

### Lint / format / type-check

These match what CI enforces (`.github/workflows/ci.yml`):

```bash
black --check --diff --target-version py311 app/ tests/ scripts/cli.py scripts/main.py
black app/ tests/ scripts/cli.py scripts/main.py   # auto-format

flake8 app/ tests/ scripts/cli.py scripts/main.py \
  --max-line-length=120 \
  --extend-ignore=E203,W503,E501,F401,F403,F811,F841,W291,W293,E402,E722,F541

mypy -p app --ignore-missing-imports --no-strict-optional --show-error-codes   # CI treats failures as non-blocking
bandit -r app/ -ll
```

`./scripts/format_code.sh [--check]` and `./scripts/fix_linting.sh` run Black (and whitespace fixes) inside a throwaway `python:3.11-slim` container if you'd rather not install Black locally.

### Running the app

```bash
./install.sh && BioAnalyzer build && BioAnalyzer start && BioAnalyzer status   # Docker, via global CLI wrapper
docker compose up                                                              # equivalent, manual
python main.py                                                                # run API directly (uvicorn, port 8000)
```

API docs at `http://localhost:8000/docs`. The CLI and dev/ops scripts read the API base URL from `BIOANALYZER_API_URL` (root URL or `/api/v1` base, no hardcoded localhost).

```bash
BioAnalyzer analyze 12345678                  # or: python scripts/cli.py analyze 12345678
BioAnalyzer analyze --file pmids.txt
BioAnalyzer retrieve 12345678
BioAnalyzer run table                          # launches the Streamlit curator table
```

### Required env vars

`NCBI_API_KEY`, `EMAIL` (for NCBI), plus one LLM key: `GEMINI_API_KEY` (default/cheapest), `OPENAI_API_KEY`, `ANTHROPIC_API_KEY`, or `OLLAMA_BASE_URL`. Provider auto-detects from whichever key is set; override with `LLM_PROVIDER`. See `.env.example` for the full list (RAG tuning, timeouts, cache TTL, rate limiting).

## Architecture

Layered: CLI/API → Services → Models/Normalization → Utils. Two analysis pipelines share the same field-extraction core but differ in depth:

- **v1** (`app/api/routers/bugsigdb_analysis.py`, `/api/v1/analyze/{pmid}`) — direct LLM query per field via `app/services/bugsigdb_analyzer.py::analyze_paper_simple`. Fast, cheap.
- **v2** (`app/api/routers/bugsigdb_analysis_v2.py`, `/api/v2/analyze/{pmid}?use_rag=true`) — adds the RAG pipeline (`app/services/advanced_rag.py`) with chunk re-ranking (`chunk_reranking.py`) and contextual summarization (`contextual_summarization.py`) before querying the LLM, via `analyze_paper_with_rag`. Slower, more accurate.

A third, separate pipeline takes an arbitrary URL instead of a PMID:
**URL analysis** (`app/api/routers/study_analysis.py`, `POST /api/v1/analyze-url`) — a 7-step background-task workflow (scrape → describe ≤10 images via an LLM → merge into enhanced Markdown → chunk → vectorize with an in-memory NumPy store → extract multi-experiment/multi-signature results via Paper-QA's `agent_query`, orchestrated by `app/services/agent_orchestrator.py::AgentOrchestrator`) producing a `StudyAnalysisResult` (`app/models/extraction_schemas.py`) shaped to be drop-in compatible with v1/v2's output. Job status/results are tracked in an in-memory `job_store` dict in `study_analysis.py` — **lost on restart, unbounded, and not shared across worker processes**; don't assume this endpoint works behind multiple Uvicorn/Gunicorn workers or survives a redeploy. No test coverage exists for this router or `AgentOrchestrator` itself (the upstream scrape/image/chunk/vectorize steps are tested in isolation elsewhere). This router has its own exception handling and does not go through `app/api/app.py`'s global handler — `mask_exception_message` has to be (and is) called explicitly inside it.

Key modules:

- `app/services/data_retrieval.py`, `standalone_pubmed_retriever.py` — PubMed/PMC fetching (metadata + full text), rate-limited to NCBI's 3 req/s.
- `app/services/cache_manager.py` — SQLite-backed cache (`cache/analysis_cache.db`), default 24h TTL. This is the actual cache; `redis` in `docker-compose.yml` is provisioned but not wired into the app code — don't assume cache reads/writes touch Redis.
- `app/models/llm_provider.py` — LiteLLM-based provider abstraction (Gemini/OpenAI/Anthropic/Ollama/Llamafile); `app/models/unified_qa.py` is the common QA interface; `app/models/gemini_qa.py` and `paperqa_agent.py` are provider-specific implementations.
- `app/normalization/` — maps extracted free-text fields to controlled ontology vocabularies before they reach the curator-desk CSV format: `host_species.py` → NCBITaxon, `body_site.py` → UBERON, `condition.py` → EFO (via `ols.py`, which queries EBI's OLS4 API), `sequencing_type.py` / `taxa_level.py` → BugSigDB's own controlled vocab, `sample_size.py` → numeric parsing (including word-to-number). Each returns a `NormalizedTerm` (`types.py`): label, ontology ID, status, mapping confidence.
- `app/utils/credential_masking.py` — scrubs API keys/secrets from logs and exception messages; the global exception handler in `app/api/app.py` always routes through it before logging or returning error detail.
- `app/core/settings.py` — Pydantic-based settings (separate from the simpler `os.getenv` reads in `app/utils/config.py`); supports loading from JSON/YAML and presets (see `BioAnalyzer settings` subcommands: `view`, `save`, `load`, `preset`, `migrate`).
- `curator_table/app.py` — Streamlit dashboard (`BioAnalyzer run table`) for reviewing predictions against curator ground truth; writes feedback to `results/curator_feedback.csv`/`.parquet`, upserted by PMID + curator ID. Used to build confusion-matrix validation reports (`scripts/eval/confusion_matrix_analysis.py`, `scripts/eval/ontology_benchmark.py`).
- `scripts/cli.py` — the actual CLI implementation (`cli.py` at repo root is just a backward-compat shim importing `scripts.cli.main`); output rendering (table/csv/json/xml, including the curator-desk-specific CSV layout) lives at the top of this file before the `BioAnalyzerCLI` class.
- `app/services/web_scraper.py`, `image_processor.py`, `converter_service.py`, `app/utils/chunking.py`, `vector_store_service.py` — the steps the URL-analysis pipeline (above) chains together before `AgentOrchestrator` runs; `vector_store_service.py` supports both NumPy and Qdrant backends, but `study_analysis.py`'s only caller always selects NumPy.

Tests largely mock external calls (PubMed, LLM providers) — see `tests/test_api_endpoints.py` and `tests/test_integration*.py` for the mocking patterns used; there's no live network/LLM dependency in the suite.

## Notes on docs/ accuracy

`docs/ARCHITECTURE.md` describes a much larger aspirational system (Postgres, Prometheus, structured logging, Kubernetes, circuit breakers) that does not reflect the current codebase — treat it as a roadmap sketch, not ground truth. Prefer reading the actual modules listed above. `docs/README.md` indexes the rest of `docs/`.