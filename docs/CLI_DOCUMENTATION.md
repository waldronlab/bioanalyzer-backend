# BioAnalyzer CLI Reference

The CLI (`scripts/cli.py`, wrapped by the `BioAnalyzer` global command and the
backward-compatible `cli.py` shim at the repo root) is a thin client: the
lifecycle commands (`build`/`start`/`stop`/`restart`/`status`/`run table`)
drive Docker directly, while every analysis command (`analyze`, `analyze-url`,
`qa`) talks to the FastAPI service over HTTP at `BIOANALYZER_API_URL`
(default `http://localhost:8000/api/v1`) — so the API must be running
(`BioAnalyzer start`) before those will work. `search`, `curate`, and
`retrieve` call PubMed/PMC directly and don't need the API up.

Three equivalent ways to invoke it, all identical:

```bash
BioAnalyzer <command> [args]              # global wrapper (after ./install.sh)
python scripts/cli.py <command> [args]    # direct
python cli.py <command> [args]            # backward-compat shim, same repo root
```

This reference is generated from the actual `argparse` definitions in
`scripts/cli.py` — if a flag here disagrees with `BioAnalyzer help` or
`BioAnalyzer <command> --help`, trust the running binary.

## Quick Start

```bash
BioAnalyzer build && BioAnalyzer start   # build the image, start the API
BioAnalyzer status                       # confirm it's healthy
BioAnalyzer analyze 25444008             # analyze one paper
BioAnalyzer stop                         # tear down when done
```

## Command Index

| Command | Purpose |
|---|---|
| [`build`](#bioanalyzer-build) | Build the Docker image |
| [`start`](#bioanalyzer-start) | Start the API (and build first if needed) |
| [`stop`](#bioanalyzer-stop) | Stop and remove containers |
| [`restart`](#bioanalyzer-restart) | `stop` then `start` |
| [`status`](#bioanalyzer-status) | Docker/image/container/API health snapshot |
| [`run table`](#bioanalyzer-run-table) | Launch the Streamlit curator table |
| [`fields`](#bioanalyzer-fields) | Print the 5 BugSigDB fields this tool extracts |
| [`search`](#bioanalyzer-search) | PubMed discovery search (query presets) |
| [`curate`](#bioanalyzer-curate-topic) | PubMed search for a named bulk-retrieval topic |
| [`analyze`](#bioanalyzer-analyze) | Extract the 5 fields for one or more PMIDs |
| [`analyze-url`](#bioanalyzer-analyze-url) | Full study-analysis pipeline for an arbitrary URL |
| [`retrieve`](#bioanalyzer-retrieve) | Fetch raw PubMed/PMC metadata + full text, no LLM |
| [`qa`](#bioanalyzer-qa) | Ask the RAG-backed Q&A endpoint a free-text question |
| [`settings`](#bioanalyzer-settings) | View/save/load/preset/migrate app settings |
| [`help`](#bioanalyzer-help) | Print the built-in command summary |

---

## Lifecycle Commands

### `BioAnalyzer build`

Builds the `bioanalyzer-package` Docker image from the repo's `Dockerfile`.

```bash
$ BioAnalyzer build
🔨 Building BioAnalyzer containers...
✅ All containers built successfully!
```

### `BioAnalyzer start`

Builds the image first if it's missing, warns about missing required env
vars (`GEMINI_API_KEY`, `NCBI_API_KEY`, `EMAIL`), brings the stack up via
`docker compose` (recreating containers if they exist but aren't healthy),
and polls `/health` for up to 60s.

```bash
$ BioAnalyzer start
🚀 Starting BioAnalyzer application...
⏳ Waiting for API health (timeout: 60s)...
✅ API running at http://localhost:8000

🎉 BioAnalyzer backend is running!
🔧 API: http://localhost:8000  |  📖 Docs: http://localhost:8000/docs
```

`--interactive` drops straight into the `qa` interactive prompt once the API
is up:

```bash
BioAnalyzer start --interactive
```

### `BioAnalyzer stop`

```bash
$ BioAnalyzer stop
🛑 Stopping BioAnalyzer application...
✅ BioAnalyzer application stopped
```

### `BioAnalyzer restart`

Equivalent to `stop` followed by `start` (with a 2s pause between).

### `BioAnalyzer status`

```bash
$ BioAnalyzer status
📊 BioAnalyzer System Status
========================================
Docker:          ✅ Available
Package Image:   ✅ Built
Container:       ✅ Running
API Health:      ✅ Healthy
🔧 http://localhost:8000  |  📖 http://localhost:8000/docs
```

### `BioAnalyzer run table`

Launches the Streamlit curator-review table (`curator_table/app.py`) inside
the Docker image, bind-mounting the repo and forwarding your env vars
(via `.env` and/or `os.environ`). Requires the image to already be built.

```bash
BioAnalyzer run table                 # http://localhost:8501
BioAnalyzer run table --port 8888     # custom port
```

### `BioAnalyzer fields`

Prints the 5 BugSigDB fields this tool extracts and the 3 status values.

```bash
$ BioAnalyzer fields

🧬 BioAnalyzer - BugSigDB Essential Fields
==========================================
  🔹 Host Species: Host organism (e.g. Human, Mouse, Rat)
  🔹 Body Site: Sample location (e.g. Gut, Oral, Skin)
  🔹 Condition: Disease, treatment, or exposure studied
  🔹 Sequencing Type: Molecular method (e.g. 16S, WMS)
  🔹 Sample Size: Number of samples / participants

✅ PRESENT  ⚠️ PARTIALLY_PRESENT  ❌ ABSENT
```

---

## Discovery Commands

These hit PubMed's `esearch` directly (`app/services/data_retrieval.py`),
not the API — they work even with the API stopped, as long as
`NCBI_API_KEY` is set.

### `BioAnalyzer search`

```text
BioAnalyzer search [--query/-q TEXT] [--preset discovery|broad|precision]
                    [--max-results/-n N] [--format txt|json|csv] [--output/-o FILE]
```

`--preset` selects one of the built-in queries in
`app/services/pubmed_queries.py` (ignored if `--query` is given):

- `discovery` (default) — recall-optimized microbiome + sequencing query, excludes reviews/meta-analyses
- `broad` — looser version of the same query, more hits, less precision
- `precision` — narrower, requires explicit "differential abundance" language

```bash
# 50 PMIDs from the default discovery query, saved to a file
$ BioAnalyzer search --preset discovery -n 50 -o pmids.txt
🔍 PubMed search (preset=discovery, max=50)...
✅ Found 50 PMID(s)
💾 PMIDs saved to: pmids.txt

# Broader net, JSON output to stdout
BioAnalyzer search --preset broad -n 200 --format json

# Your own PubMed query string (bypasses --preset entirely)
BioAnalyzer search --query '"Akkermansia muciniphila"[tiab] AND obesity[tiab]' -n 30 --format csv -o akk_obesity.csv
```

### `BioAnalyzer curate <topic>`

Runs one of three fixed, named MeSH bulk-retrieval queries curated for
specific BugSigDB topics (`app/services/pubmed_queries.py::BULK_RETRIEVAL_QUERIES`).
`topic` is one of `women`, `masld`, `colorectal`.

```text
BioAnalyzer curate <women|masld|colorectal> [--max-results/-n N]
                    [--format txt|json|csv] [--output/-o FILE]
```

```bash
# Women's health microbiome papers, up to 300, saved as CSV
BioAnalyzer curate women -n 300 --format csv -o womens_health_pmids.csv

# MASLD/NAFLD microbiome papers, default 100
BioAnalyzer curate masld -o masld_pmids.txt

# Colorectal cancer microbiome papers
BioAnalyzer curate colorectal -n 500 --format json -o crc_pmids.json
```

---

## Analysis Commands

### `BioAnalyzer analyze`

The core command: extracts the 5 BugSigDB fields (Host Species, Body Site,
Condition, Sequencing Type, Sample Size) for one or more PMIDs via
`GET /api/v1/analyze/{pmid}`. **Requires the API to be running.**

```text
BioAnalyzer analyze [PMID ...] [--file/-f FILE]
                     [--format table|json|csv|curator_desk_csv|detailed_csv|xml]
                     [--output/-o FILE] [--refresh] [--verbose/-v]
```

PMIDs can be given inline (space- or comma-separated), loaded from a file
with `--file` (`.txt` one-per-line or comma-separated, `.csv` first column,
`.xlsx`/`.xls` first column with a PMID-looking header — read via a
throwaway container, so Docker must be available for Excel input), or both
at once (deduplicated).

```bash
# Single paper, human-readable table
$ BioAnalyzer analyze 25444008
🔬 Analysing 1 paper(s)...
[1/1] PMID: 25444008
✅ Done

================================================================================
🧬 BIOANALYZER - CURATABLE SIGNATURE ANALYSIS RESULTS
================================================================================
📄 PMID: 25444008
...
✅ Host Species          | PRESENT              | Human                          | 0.94
✅ Body Site              | PRESENT              | Gut                            | 0.91
...

# A handful of PMIDs, inline
BioAnalyzer analyze 22339879 25444008 25599982

# Same thing, comma-separated (also accepted)
BioAnalyzer analyze 22339879,25444008,25599982

# From a file, curator-desk CSV output (the format curator_table/curator_table_r expect)
BioAnalyzer analyze --file pmids.txt --format csv -o predictions.csv

# Force recompute, bypassing the 24h SQLite cache
BioAnalyzer analyze 25444008 --refresh

# All fields + per-field PRESENT/PARTIALLY_PRESENT/ABSENT status, for validation scripts
BioAnalyzer analyze --file pmids.txt --format detailed_csv -o detailed.csv

# XML output to stdout
BioAnalyzer analyze 25444008 --format xml
```

**Output formats:**

| `--format` | Shape | Use for |
|---|---|---|
| `table` (default) | Human-readable, one block per PMID | Reading in a terminal |
| `json` | Full result payload per PMID | Piping into other tools |
| `csv` / `curator_desk_csv` | Fixed curator-desk schema — value + Ontology ID + Ontology Candidates for Host Species/Body Site/Condition, plus Sample Size, Sequencing Type, Differential Abundance, In bsgdb, and a Mapping Tier per ontology field | Handing predictions to `curator_table`/`curator_table_r` — these two names produce byte-identical output |
| `detailed_csv` | Older, separate schema: value **and** status per field, no ontology columns | Internal validation only, e.g. `scripts/eval/confusion_matrix_analysis.py` — not what the curator table reads |
| `xml` | `<BioAnalyzerResults>` with status/value/confidence (+ ontology ID/tier for the 3 ontology fields) per field | Interop with XML-based tooling |

**Re-running against an existing `--format csv`/`curator_desk_csv` file is
additive:** PMIDs already present in the `-o` output file are skipped
(printed as "⏭️ Skipping N PMID(s) already in ...") and new rows are
appended, using the file itself as the de-duplication manifest — no separate
state file to go stale. `--refresh` disables this and overwrites from
scratch:

```bash
# First run — creates predictions.csv with 3 rows
BioAnalyzer analyze --file pmids.txt --format csv -o predictions.csv

# Add more PMIDs to pmids.txt, re-run — only the new ones get analyzed and appended
BioAnalyzer analyze --file pmids.txt --format csv -o predictions.csv

# Redo everything, including PMIDs already in the file
BioAnalyzer analyze --file pmids.txt --format csv -o predictions.csv --refresh
```

### `BioAnalyzer analyze-url`

Runs the separate URL-based study-analysis pipeline
(`POST /api/v1/analyze-url` → scrape → describe images → chunk/vectorize →
Paper-QA extraction) for an arbitrary paper URL instead of a PMID. This is a
background job on the server side — the CLI submits it, then polls
`/api/v1/analysis-status/{job_id}` until it completes or times out.

```text
BioAnalyzer analyze-url [URL ...] [--file/-f FILE]
                         [--embedding-model MODEL] [--llm-model MODEL]
                         [--format table|json] [--output/-o FILE]
                         [--poll-interval N] [--timeout N] [--verbose/-v]
```

```bash
# One URL, default models (gemini/text-embedding-004 + gemini/gemini-2.0-flash)
$ BioAnalyzer analyze-url https://www.ncbi.nlm.nih.gov/pmc/articles/PMC4315977/
[1/1] https://www.ncbi.nlm.nih.gov/pmc/articles/PMC4315977/
🆔 Job ID: 3f1c2b8a-...
   ⏳ processing (scraping)
   ⏳ processing (extracting)
================================================================================
🌐 BIOANALYZER - URL STUDY ANALYSIS RESULTS
================================================================================

🔗 https://www.ncbi.nlm.nih.gov/pmc/articles/PMC4315977/
🆔 Job: 3f1c2b8a-...
🧪 Experiments: 2
✅ Curation Ready: Yes
...

# Several URLs from a file, one per line, with a longer timeout for slow scrapes
BioAnalyzer analyze-url --file urls.txt --timeout 600 --poll-interval 10 -o url_results.json --format json

# Non-default LLM/embedding models
BioAnalyzer analyze-url https://example.org/study --llm-model gpt-4o-mini --embedding-model ollama/nomic-embed-text
```

### `BioAnalyzer retrieve`

Fetches raw PubMed/PMC metadata and full text — no LLM call, no field
extraction. Useful for inspecting what BioAnalyzer actually sees before it
reasons about it, or for building your own corpus. Does **not** require the
API to be running (it calls the retriever service directly, or falls back to
raw NCBI E-utilities).

```text
BioAnalyzer retrieve [PMID ...] [--file/-f FILE]
                      [--format table|json|csv] [--output/-o FILE]
                      [--save/-s] [--verbose/-v]
```

```bash
# Basic retrieval, table output
BioAnalyzer retrieve 22339879

# Multiple PMIDs, comma-separated, and persist each as its own JSON file under results/
BioAnalyzer retrieve 22339879,25444008 --save

# From a file, CSV summary (title/journal/authors/full-text availability/lengths)
BioAnalyzer retrieve --file pmids.txt --format csv -o retrieved_summary.csv
```

### `BioAnalyzer qa`

Free-text question against the RAG-backed `/api/v1/qa` endpoint.
**Requires the API to be running.**

```text
BioAnalyzer qa [QUESTION] [--interactive/-i]
```

```bash
# One-shot question
$ BioAnalyzer qa "What is 16S rRNA sequencing?"
🤔 Thinking...

💡 Answer (confidence: 0.87):
------------------------------------------------------------
16S rRNA sequencing is a method for identifying and comparing
bacteria present within a sample by sequencing the 16S rRNA gene...
------------------------------------------------------------

# Interactive REPL (also entered automatically if you run `qa` with no question)
$ BioAnalyzer qa --interactive
💬 Interactive Q&A  (type 'quit' to exit)

Q> what body sites does BugSigDB track?
...
Q> quit
👋 Goodbye!
```

---

## Settings

### `BioAnalyzer settings`

Manages the Pydantic-based structured settings in `app/core/settings.py`
(distinct from the flatter `os.getenv` reads in `app/utils/config.py`). See
[SETTINGS.md](SETTINGS.md) for the full field reference.

```text
BioAnalyzer settings view   [--format json|yaml|table] [--output/-o FILE]
BioAnalyzer settings save   [--file/-f FILE] [--format json|yaml]
                             [--preset fast|balanced|high_quality|development|production]
BioAnalyzer settings load   --file/-f FILE [--apply]
BioAnalyzer settings preset <fast|balanced|high_quality|development|production> [--save/-s]
BioAnalyzer settings migrate --file/-f FILE [--output/-o FILE]
```

```bash
# Show the currently active settings as a human-readable table
$ BioAnalyzer settings view
============================================================
BioAnalyzer Settings
============================================================
Version: 1.0  |  Env: development
🔌 API  timeout=180s  analysis=300s  gemini=60s  max_req=10
🤖 LLM  provider=gemini  model=gemini-2.0-flash
📚 RAG  enabled=True  top_k=10  rerank=hybrid  cache=True
💾 Cache  enabled=True  ttl=24h  max=1000  dir=cache
📝 Log  level=INFO  dir=logs
============================================================

# Dump as JSON to a file
BioAnalyzer settings view --format json -o current_settings.json

# Inspect a preset without applying it
BioAnalyzer settings preset high_quality

# Apply the "fast" preset and persist it as the default settings file
BioAnalyzer settings preset fast --save

# Save the current in-memory settings explicitly, as YAML
BioAnalyzer settings save --format yaml -f my_settings.yaml

# Load a settings file and apply it to the current environment
BioAnalyzer settings load --file my_settings.yaml --apply

# Migrate an old-format settings file to the current schema
BioAnalyzer settings migrate --file legacy_settings.json -o settings.migrated.json
```

---

## `BioAnalyzer help`

Prints the CLI's own built-in command summary (also shown when no command is
given):

```bash
BioAnalyzer help
BioAnalyzer            # same as `help` with no arguments
```

---

## Environment Variables

| Variable | Purpose |
|---|---|
| `NCBI_API_KEY`, `EMAIL` | Required for PubMed/PMC access (search, curate, retrieve, analyze) |
| `GEMINI_API_KEY` / `OPENAI_API_KEY` / `ANTHROPIC_API_KEY` / `OLLAMA_BASE_URL` | One LLM credential; provider auto-detects, override with `LLM_PROVIDER` |
| `BIOANALYZER_API_URL` | API base the CLI talks to for `analyze`/`analyze-url`/`qa` (default `http://localhost:8000/api/v1`) — point this at a remote/staging API instead of localhost |
| `BIOANALYZER_ANALYZE_TIMEOUT` | Per-PMID HTTP timeout (seconds) for `analyze`, default `180` |
| `BIOANALYZER_PATH` | Where the `BioAnalyzer` global wrapper looks for this repo, if not run from inside it |

A `.env` file at the repo root is picked up automatically by both the CLI
(for API calls) and `start`/`run table` (forwarded into the container).

## Troubleshooting

**"Docker is not installed or not available"** — install Docker and make
sure the daemon is running (`sudo systemctl start docker`); your user needs
to be in the `docker` group.

**`analyze`/`analyze-url`/`qa` return connection errors** — the API isn't
up. Run `BioAnalyzer status`; if unhealthy, `BioAnalyzer start` (or
`restart`). These three commands need the API; `search`, `curate`, and
`retrieve` don't.

**`analyze --file foo.xlsx` fails** — reading Excel requires the Docker
image (`BioAnalyzer build`) since it's parsed with pandas inside a throwaway
container, not the host Python environment.

**Rate-limited during a large `analyze --file` batch** — expected and
handled automatically: the API's own 60 req/min limiter returns HTTP 429,
and the CLI waits and retries rather than failing the batch.
