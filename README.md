# BioAnalyzer Backend

[![CI/CD Pipeline](https://github.com/waldronlab/bioanalyzer-backend/actions/workflows/ci.yml/badge.svg)](https://github.com/waldronlab/bioanalyzer-backend/actions/workflows/ci.yml)
[![Python](https://img.shields.io/badge/Python-3.8+-blue.svg)](https://python.org)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.104+-green.svg)](https://fastapi.tiangolo.com)
[![Docker](https://img.shields.io/badge/Docker-20.0+-blue.svg)](https://docker.com)
[![License](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

Extracts six BugSigDB fields from scientific papers using LLMs. Pulls metadata and full text from PubMed/PMC, then analyzes papers to determine if they're ready for curation.

Works on Ubuntu with Docker. Python 3.8+ for local installs.

## What It Does

Takes a PMID, fetches the paper from PubMed, and extracts:
1. Host Species (Human, Mouse, etc.)
2. Body Site (Gut, Oral, Skin, etc.)
3. Condition (disease/treatment being studied)
4. Sequencing Type (16S, metagenomics, etc.)
5. Taxa Level (phylum, genus, species, etc.)
6. Sample Size (number of samples/participants)

Each field gets a status: `PRESENT`, `PARTIALLY_PRESENT`, or `ABSENT`, plus a confidence score.

## Quick Start

### Prerequisites

- Docker 20.0+ (recommended) or Python 3.8+
- NCBI API key (required)
- At least one LLM API key: Gemini (easiest), OpenAI, Anthropic, or Ollama (local)

### Docker (Recommended)

```bash
git clone https://github.com/waldronlab/bioanalyzer-backend.git
cd bioanalyzer-backend

chmod +x install.sh
./install.sh

docker compose build
docker compose up -d

curl http://localhost:8000/health
```

API docs at http://localhost:8000/docs

### Local Install

```bash
git clone https://github.com/waldronlab/bioanalyzer-backend.git
cd bioanalyzer-backend

python3 -m venv .venv
source .venv/bin/activate

pip install -e .

# Set API keys
export NCBI_API_KEY=your_key
export GEMINI_API_KEY=your_key
```

## Usage

### CLI

```bash
# Analyze a paper
BioAnalyzer analyze 12345678

# Batch analysis
BioAnalyzer analyze 12345678,87654321
BioAnalyzer analyze --file pmids.txt

# Retrieve paper data
BioAnalyzer retrieve 12345678

# System management
BioAnalyzer start
BioAnalyzer stop
BioAnalyzer status
```

### API

**v1 (simple, fast):**
```bash
curl http://localhost:8000/api/v1/analyze/12345678
```

**v2 (RAG-enhanced, more accurate):**
```bash
curl "http://localhost:8000/api/v2/analyze/12345678?use_rag=true"
```

v2 uses RAG to improve accuracy but costs more API calls. Use v1 for quick checks, v2 when you need better results.

## Configuration

### Required

- `NCBI_API_KEY` - Get from [NCBI account settings](https://www.ncbi.nlm.nih.gov/account/settings/)
- `EMAIL` - Contact email for NCBI requests

### LLM Provider

Set one of:
- `GEMINI_API_KEY` - Google Gemini (recommended, cheapest)
- `OPENAI_API_KEY` - OpenAI
- `ANTHROPIC_API_KEY` - Anthropic
- `OLLAMA_BASE_URL` - Local Ollama (default: http://localhost:11434)

Auto-detects provider from available keys. Override with `LLM_PROVIDER=gemini|openai|anthropic|ollama`.

### RAG Settings (v2 API)

```bash
# Fast (good for batch jobs)
export RAG_SUMMARY_QUALITY=fast
export RAG_RERANK_METHOD=keyword
export RAG_TOP_K_CHUNKS=5

# Balanced (default, good tradeoff)
export RAG_SUMMARY_QUALITY=balanced
export RAG_RERANK_METHOD=hybrid
export RAG_TOP_K_CHUNKS=10

# High accuracy (slower, more expensive)
export RAG_SUMMARY_QUALITY=high
export RAG_RERANK_METHOD=llm
export RAG_TOP_K_CHUNKS=20
```

### Performance

- `USE_FULLTEXT=true` - Enable full text retrieval (slower but more accurate)
- `API_TIMEOUT=30` - Request timeout in seconds
- `CACHE_VALIDITY_HOURS=24` - How long to cache results

## Architecture

Standard layered setup:

```
app/
├── api/          # FastAPI routes (v1 and v2)
├── services/     # Business logic
│   ├── data_retrieval.py      # PubMed fetching
│   ├── bugsigdb_analyzer.py   # Field extraction
│   ├── advanced_rag.py         # RAG pipeline
│   └── cache_manager.py       # SQLite cache
├── models/       # LLM wrappers
│   ├── llm_provider.py        # LiteLLM manager
│   └── unified_qa.py          # QA interface
└── utils/        # Helpers
```

**Flow:**
1. Fetch paper from PubMed (cached in SQLite)
2. Chunk text if full text available
3. For each field: query LLM (v1) or use RAG pipeline (v2)
4. Validate and score results
5. Cache and return

v2 adds chunk re-ranking and contextual summarization before querying the LLM. Worth the extra cost for better accuracy.

## LLM Providers

Uses LiteLLM for provider abstraction. Supports:
- **Gemini** - Good balance of cost and quality
- **OpenAI** - Expensive but reliable
- **Anthropic** - Good for complex reasoning
- **Ollama** - Free but requires local setup
- **Llamafile** - Self-contained local models

Gemini is the default because it's cheap and works well for this use case.

## Performance

- **v1**: ~2-5 seconds per paper, 10-20 papers/min
- **v2**: ~5-10 seconds per paper, 5-10 papers/min
- **Memory**: ~100-200MB base, +50MB per concurrent request
- **Cache hit rate**: 60-80% for frequently analyzed papers

Cache is SQLite-based, stored in `cache/analysis_cache.db`. Results valid for 24 hours by default.

## Development

```bash
# Install dev dependencies
pip install -e .[dev]

# Run tests
pytest

# Format code
black .

# Lint
flake8 .
```

### Adding Features

- Services go in `app/services/`
- API routes in `app/api/routers/`
- CLI commands in `cli.py`
- Models in `app/api/models/`

## Troubleshooting

**Import errors:**
- Use Docker, or ensure virtual environment is activated
- Check Python version (3.8+)

**API not responding:**
```bash
docker compose ps
docker compose logs
```

**Missing API keys:**
- Check `.env` file or environment variables
- System will warn but continue (with limited functionality)

**Rate limiting:**
- NCBI enforces 3 requests/second. We throttle automatically.
- LLM providers have their own limits. Check your quota.

## Documentation

- [SETUP_GUIDE.md](SETUP_GUIDE.md) - Detailed setup
- [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) - System design
- [docs/RAG_GUIDE.md](docs/RAG_GUIDE.md) - RAG configuration
- API docs: http://localhost:8000/docs (when running)

## License

MIT License - see [LICENSE](LICENSE) file.
