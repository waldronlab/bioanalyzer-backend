# BioAnalyzer Package Documentation

Technical documentation for developers working on or integrating with BioAnalyzer.

## Overview

BioAnalyzer extracts six BugSigDB fields from scientific papers. It's a FastAPI app with a CLI wrapper, using LLMs to analyze paper content.

## Architecture

Layered architecture:

- **API Layer** (`app/api/`): FastAPI routes, request/response models
- **Service Layer** (`app/services/`): Core business logic
- **Model Layer** (`app/models/`): LLM provider abstractions
- **Utils** (`app/utils/`): Shared helpers

### Key Services

**PubMedRetriever** (`app/services/data_retrieval.py`)
- Fetches metadata and full text from NCBI E-utilities
- Handles rate limiting (NCBI requires 0.34s between requests)
- Caches results in SQLite

**BugSigDBAnalyzer** (`app/services/bugsigdb_analyzer.py`)
- Orchestrates field extraction
- v1: Direct LLM queries
- v2: RAG pipeline with chunk re-ranking

**AdvancedRAGService** (`app/services/advanced_rag.py`)
- Re-ranks chunks by relevance
- Generates query-aware summaries
- Caches summaries to reduce API calls

**CacheManager** (`app/services/cache_manager.py`)
- SQLite-based caching
- 24-hour default validity
- Separate caches for analysis results, metadata, and full text

## API Endpoints

### v1 API (Simple)

Fast, single LLM call per field. Good for quick checks.

```bash
GET /api/v1/analyze/{pmid}
POST /api/v1/analyze/{pmid}
GET /api/v1/fields
```

### v2 API (RAG-Enhanced)

Slower but more accurate. Re-ranks chunks and generates contextual summaries.

```bash
GET /api/v2/analyze/{pmid}?use_rag=true
POST /api/v2/analyze
POST /api/v2/analyze/batch
GET /api/v2/rag/config
```

### Retrieval

```bash
GET /api/v1/retrieve/{pmid}
POST /api/v1/retrieve/batch
GET /api/v1/retrieve/search?q=query
```

## Configuration

### Environment Variables

**Required:**
- `NCBI_API_KEY` - NCBI API key
- `EMAIL` - Contact email for NCBI

**LLM (at least one):**
- `GEMINI_API_KEY` - Google Gemini
- `OPENAI_API_KEY` - OpenAI
- `ANTHROPIC_API_KEY` - Anthropic
- `OLLAMA_BASE_URL` - Local Ollama (default: http://localhost:11434)

**Optional:**
- `LLM_PROVIDER` - Override auto-detection
- `LLM_MODEL` - Specific model name
- `USE_FULLTEXT` - Enable full text retrieval (default: false)
- `API_TIMEOUT` - Request timeout (default: 30s)
- `CACHE_VALIDITY_HOURS` - Cache TTL (default: 24)

### RAG Configuration

Only applies to v2 API:

- `RAG_SUMMARY_QUALITY` - fast|balanced|high (default: balanced)
- `RAG_RERANK_METHOD` - keyword|llm|hybrid (default: hybrid)
- `RAG_TOP_K_CHUNKS` - Number of chunks after re-ranking (default: 10)
- `RAG_USE_SUMMARY_CACHE` - Cache summaries (default: true)

## Development

### Setup

```bash
git clone https://github.com/waldronlab/bioanalyzer-backend.git
cd BioAnalyzer-Backend

python3 -m venv .venv
source .venv/bin/activate

pip install -e .[dev]
```

### Running Tests

```bash
pytest
pytest --cov=app
pytest tests/test_retrieval.py
```

### Code Quality

```bash
black .
flake8 .
mypy .
```

## Project Structure

```
BioAnalyzer-Backend/
├── app/
│   ├── api/              # FastAPI routes
│   ├── services/         # Business logic
│   ├── models/           # LLM wrappers
│   └── utils/            # Helpers
├── tests/                # Test suite
├── docs/                 # Documentation
├── cli.py                # CLI interface
├── main.py               # API server entry
└── pyproject.toml        # Package config
```

## Integration

### Python

```python
from app.services.data_retrieval import PubMedRetriever
from app.services.bugsigdb_analyzer import analyze_paper_simple

retriever = PubMedRetriever(api_key="...", email="...")
result = await analyze_paper_simple("12345678")
```

### HTTP

```python
import requests

response = requests.get("http://localhost:8000/api/v1/analyze/12345678")
data = response.json()
```

## Troubleshooting

**Import errors:**
- Ensure virtual environment is activated
- Check Python version (3.8+)
- Reinstall: `pip install -e . --force-reinstall`

**API key issues:**
- Verify keys in `.env` or environment
- Check provider-specific requirements (Ollama needs local server)

**Rate limiting:**
- NCBI: 3 req/sec (handled automatically)
- LLM providers: Check your quota

**Cache issues:**
- Cache location: `cache/analysis_cache.db`
- Clear cache: Delete the database file
- Check permissions if cache writes fail

## Performance Tuning

**For speed:**
- Use v1 API
- Set `USE_FULLTEXT=false`
- Use `RAG_SUMMARY_QUALITY=fast` (v2 only)

**For accuracy:**
- Use v2 API with RAG
- Set `USE_FULLTEXT=true`
- Use `RAG_SUMMARY_QUALITY=high` (v2 only)

**For batch processing:**
- Process in parallel (watch rate limits)
- Use caching (default 24h)
- Consider `RAG_RERANK_METHOD=keyword` for speed

## License

MIT License
