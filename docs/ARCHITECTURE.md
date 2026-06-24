# BioAnalyzer Architecture

BioAnalyzer extracts BugSigDB curation fields from scientific papers: it
retrieves metadata/full text from PubMed/PMC, then uses an LLM (via
LiteLLM, or a Gemini/Paper-QA fallback chain) to determine field presence
and confidence. It's a layered system - CLI/API -> Services ->
Models/Normalization -> Utils - not a microservices or distributed system.

This document is split into two parts: **Current Architecture** describes
what's actually implemented today, verified directly against the code.
**Roadmap / Not Yet Implemented** lists architectural ideas that have been
discussed or partially sketched out but don't exist in the codebase yet -
don't write code or docs assuming any of that section is real.

## Current Architecture

### Layered structure

```
┌─────────────────────────────────────────┐
│   CLI (scripts/cli.py)  /  API (app/api) │
├─────────────────────────────────────────┤
│         Services (app/services/)         │
├─────────────────────────────────────────┤
│  Models (app/models/) / Normalization    │
│         (app/normalization/)             │
├─────────────────────────────────────────┤
│           Utils (app/utils/)             │
└─────────────────────────────────────────┘
```

- **`app/api/`** - FastAPI app (`app.py`), routers (`routers/`), API-specific
  utilities (`utils/`). Mounts four routers, each with its own URL prefix
  (see API Endpoints below).
- **`app/services/`** - business logic: PubMed/PMC retrieval
  (`data_retrieval.py`, `pubmed_retrieval_service.py`,
  `standalone_pubmed_retriever.py`), field analysis orchestration
  (`bugsigdb_analyzer.py`), the v2 RAG pipeline (`advanced_rag.py`,
  `chunk_reranking.py`, `contextual_summarization.py`), and the SQLite
  cache (`cache_manager.py`).
- **`app/models/`** - LLM integration: `llm_provider.py` (LiteLLM-based
  provider abstraction for Gemini/OpenAI/Anthropic/Ollama), `unified_qa.py`
  (the common QA interface with the fallback chain described below),
  `gemini_qa.py` and `paperqa_agent.py` (provider-specific
  implementations), `extraction_schemas.py`.
- **`app/normalization/`** - maps extracted free-text fields to controlled
  ontology vocabularies (NCBITaxon, UBERON, EFO via OLS, plus BugSigDB's
  own controlled vocab for sequencing type/taxa level, and numeric parsing
  for sample size).
- **`app/utils/`** - `config.py` (env-based settings, bridges to
  `app/core/settings.py`'s Pydantic model), `credential_masking.py`
  (scrubs secrets from logs/errors - the global exception handler in
  `app/api/app.py` always routes through it), `text_processing.py`,
  `chunking.py`, `field_validator.py`, `performance_logger.py`.

### API Endpoints

Four routers, each independently prefixed (verified against
`app/api/routers/*.py` and `app/api/app.py`):

```http
# app/api/routers/bugsigdb_analysis.py (v1 - direct LLM query per field)
GET  /api/v1/analyze/{pmid}
POST /api/v1/analyze/{pmid}
GET  /api/v1/fields
GET  /api/v1/fields/{field_name}

# app/api/routers/bugsigdb_analysis_v2.py (v2 - adds the RAG pipeline)
GET  /api/v2/analyze/{pmid}
POST /api/v2/analyze
POST /api/v2/analyze/batch
GET  /api/v2/rag/config
GET  /api/v2/fields
GET  /api/v2/fields/{field_name}

# app/api/routers/study_analysis.py (arbitrary-URL analysis, background jobs)
POST /api/v1/analyze-url
GET  /api/v1/analysis-status/{job_id}
GET  /api/v1/analysis-result/{job_id}

# app/api/routers/system.py
GET  /api/v1/             GET /api/v1/status   GET /api/v1/version
GET  /api/v1/health        GET /api/v1/config   GET /api/v1/ping
GET  /api/v1/health/gemini GET /api/v1/health/ncbi
GET  /api/v1/metrics       POST /api/v1/qa

# app/api/app.py (top-level, outside any router prefix)
GET  /health
```

There is no `/retrieve` API endpoint - PubMed/PMC retrieval is exposed via
the CLI (`BioAnalyzer retrieve`) and used internally by the analysis
endpoints, not as its own REST resource. There's no `/health/live` or
`/health/ready` (liveness/readiness probes) either - just the single
`/health` check plus the provider-specific `/health/gemini` and
`/health/ncbi`.

### CLI structure

`scripts/cli.py`'s `BioAnalyzerCLI`, invoked via the `BioAnalyzer` wrapper
or `python scripts/cli.py`:

```
BioAnalyzer
├── build / start / stop / restart / status   # Docker lifecycle
├── run table [--port N]                      # launches the Streamlit curator table
├── search [--preset discovery|broad|precision] [-n N] [-o FILE] [--query Q]
├── analyze <pmid|pmids> [--file F] [--format table|json|csv|curator_desk_csv|xml] [-o FILE]
├── analyze-url <url> [--file F] [--format table|json] [-o FILE]
├── retrieve <pmid|pmids> [--file F] [--format table|json|csv] [-o FILE] [--save]
├── qa [question] [--interactive]
├── fields
└── settings view|save|load|preset|migrate
```

Output rendering (table/csv/curator_desk_csv/xml) lives in
`scripts/cli_rendering.py`, separate from argument parsing/dispatch.

### LLM provider fallback chain

`UnifiedQA` (`app/models/unified_qa.py`) tries providers in this order,
falling back on failure (per its own docstring, verified): **LiteLLM**
(`LLMProviderManager`, supports Gemini/OpenAI/Anthropic/Ollama) first, then
**Paper-QA** (`PaperQAAgent`), then **GeminiQA** directly as the last
resort. Provider auto-detects from whichever API key is set; override with
`LLM_PROVIDER`.

### Error handling

No circuit breaker, no generic retry-with-backoff framework. The actual
pattern is: services catch specific exceptions close to where they occur
(e.g. `app/normalization/host_species.py` narrows to
`requests.exceptions.RequestException`/`ValueError`/`KeyError` around its
NCBI lookup) and fall back to a lower-confidence result rather than
raising; API-level errors are caught by FastAPI exception handlers in
`app/api/app.py`, which always mask credentials via
`app/utils/credential_masking.py` before logging or returning error detail.

### Caching

SQLite-backed (`cache/analysis_cache.db`, `app/services/cache_manager.py`),
TTL-based (`CACHE_VALIDITY_HOURS`, default 24h). There is no Redis-backed
or in-memory caching layer today - see the Docker topology note below.

### Configuration

`app/core/settings.py` (Pydantic-based, supports JSON/YAML config files and
named presets, exposed via `BioAnalyzer settings`) is the structured
source of truth. `app/utils/config.py` bridges to it - it sets its own
`os.getenv`-based defaults first, then overwrites them with
`get_settings()`'s values - and is what the 13 other modules that need
flat config constants actually import. See `.env.example` for the full set
of supported environment variables.

### Deployment topology

Two Docker services - the FastAPI app and Redis (see
[DOCKER_DEPLOYMENT.md](DOCKER_DEPLOYMENT.md) for the full picture). Redis
is provisioned but **not** currently used by the app's caching logic
(that's SQLite, as above) - don't assume cache reads/writes touch it.
No Nginx, no PostgreSQL, no Prometheus in this repo's Docker setup.

## Roadmap / Not Yet Implemented

None of the following exists in the codebase today. Treat this section as
a list of ideas, not architecture to build against:

- **Kubernetes orchestration** - auto-scaling, service discovery, rolling
  deployments. Today's deployment is `docker compose` only.
- **Circuit breaker pattern** for external API calls (NCBI, LLM providers).
  Today's resilience is narrowed exception handling + fallback values, not
  a stateful breaker with open/closed/half-open states.
- **Multi-level caching** (in-memory + Redis + file). Today's cache is
  SQLite only.
- **Prometheus-style metrics and alerting** (counters/histograms/gauges,
  alert rules, Slack/PagerDuty/email notification channels). The real
  `/metrics` endpoint returns a JSON payload of app-level stats
  (`psutil`-based resource usage, request counts, cache hit rate) - it's
  not a Prometheus scrape target, and there's no alerting system.
- **Structured logging** via `structlog` or similar. Today's logging is
  the standard library `logging` module with a fixed format string.
- **API key-based authentication/authorization and per-key rate limits.**
  Today's rate limiting (`ENABLE_RATE_LIMITING`, `RATE_LIMIT_PER_MINUTE` in
  `.env.example`) is a simple global limiter, not per-API-key.
- **Microservices split, event-driven architecture, GraphQL API,
  WebSocket-based real-time updates** - all previously listed as "planned
  improvements"; none started.
- **Horizontal scaling, database sharding, CDN/edge deployment** - none
  applicable yet; there's no database to shard (SQLite cache is local to
  one instance) and no multi-instance deployment story today.

If you want to design toward any of these, treat it as new architecture
work with its own design doc - this file shouldn't be the place that
quietly grows speculative content again.
