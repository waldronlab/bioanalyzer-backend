# BioAnalyzer Backend

[![CI/CD Pipeline](https://github.com/waldronlab/bioanalyzer-backend/actions/workflows/ci.yml/badge.svg)](https://github.com/waldronlab/bioanalyzer-backend/actions/workflows/ci.yml)
[![Python](https://img.shields.io/badge/Python-3.8+-blue.svg)](https://python.org)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.104+-green.svg)](https://fastapi.tiangolo.com)
[![Docker](https://img.shields.io/badge/Docker-20.0+-blue.svg)](https://docker.com)
[![License](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Code Quality](https://img.shields.io/badge/code%20style-black-000000.svg)](https://github.com/psf/black)

Backend system for analyzing scientific papers to identify curatable microbiome signatures. Extracts essential BugSigDB fields and retrieves full text from PubMed/PMC.

Tested on Ubuntu Linux with Docker. See [SETUP_GUIDE.md](SETUP_GUIDE.md) for setup steps.

## Overview

BioAnalyzer extracts 6 essential fields from papers for BugSigDB curation. Uses AI analysis with PubMed data retrieval to evaluate papers.

### Features

- Paper analysis: Extract 6 BugSigDB fields using AI
- Multi-provider LLM support: Works with OpenAI, Anthropic, Gemini, Ollama, and Llamafile via LiteLLM
- RAG support: Contextual summarization and chunk re-ranking for better accuracy
- Full text retrieval: Gets metadata and full text from PubMed/PMC
- REST API: Versioned endpoints (v1 and v2) with RAG support
- CLI tool: Command-line interface for analysis
- Multiple output formats: JSON, CSV, XML, and table formats
- Batch processing: Analyze multiple papers at once
- Docker support: Containerized deployment
- Monitoring: Health checks and performance metrics

## Architecture

### System Components

```
┌─────────────────────────────────────────────────────────────┐
│                    BioAnalyzer Backend                      │
├─────────────────────────────────────────────────────────────┤
│  CLI Interface (cli.py)                                    │
│  ├── Analysis Commands                                      │
│  ├── Retrieval Commands                                     │
│  └── System Management                                      │
├─────────────────────────────────────────────────────────────┤
│  API Layer (app/api/)                                       │
│  ├── FastAPI Application                                    │
│  ├── v1 Routers (Backward Compatible)                      │
│  ├── v2 Routers (RAG-Enhanced)                             │
│  ├── Study Analysis Router                                  │
│  └── Request/Response Models                                │
├─────────────────────────────────────────────────────────────┤
│  Service Layer (app/services/)                             │
│  ├── PubMedRetriever                                        │
│  ├── BugSigDBAnalyzer                                       │
│  ├── AdvancedRAGService (Contextual Summarization)          │
│  ├── ChunkReRanker                                          │
│  ├── ContextualSummarizationService                         │
│  ├── CacheManager (SQLite)                                  │
│  └── VectorStoreService                                     │
├─────────────────────────────────────────────────────────────┤
│  Model Layer (app/models/)                                 │
│  ├── LLMProviderManager (LiteLLM)                          │
│  ├── UnifiedQA                                              │
│  ├── GeminiQA (Fallback)                                    │
│  └── Configuration                                          │
├─────────────────────────────────────────────────────────────┤
│  Utility Layer (app/utils/)                                │
│  ├── Configuration Management                              │
│  ├── Text Processing & Chunking                              │
│  └── Performance Logging                                    │
└─────────────────────────────────────────────────────────────┘
```

### Complete Data Flow

```
┌─────────────────────────────────────────────────────────────┐
│                    Analysis Flow                            │
└─────────────────────────────────────────────────────────────┘

1. INPUT
   ↓
   PMID(s) via CLI or API (v1/v2)

2. RETRIEVAL
   ↓
   PubMedRetriever → NCBI E-utilities
   ├── Fetch metadata (title, abstract, authors, journal)
   ├── Fetch full text from PMC (if available)
   └── Cache results in SQLite

3. TEXT PREPARATION
   ↓
   ├── Combine title + abstract + full text
   ├── If full text > 1000 chars:
   │   └── ChunkingService → Create text chunks (3000 chars, 100 overlap)
   └── Prepare analysis text

4. ANALYSIS (For each of 6 fields)
   ↓
   ├── [v1 API] Simple Analysis:
   │   └── UnifiedQA → LLM (Gemini/OpenAI/Anthropic/Ollama)
   │
   └── [v2 API] RAG-Enhanced Analysis:
       ├── AdvancedRAGService
       │   ├── ChunkReRanker → Rank chunks by relevance
       │   │   └── Methods: keyword, LLM, or hybrid
       │   └── ContextualSummarizationService
       │       ├── Generate query-aware summaries
       │       ├── Extract key points
       │       └── Cache summaries for reuse
       └── UnifiedQA → LLM with contextual context

5. VALIDATION & SCORING
   ↓
   ├── Field validation
   ├── Confidence scoring
   └── Status determination (PRESENT/PARTIALLY_PRESENT/ABSENT)

6. OUTPUT
   ↓
   ├── JSON/CSV/Table/XML formats
   ├── Cache results (24h validity)
   └── Return structured response
```

### LLM Provider Support (via LiteLLM)

The system supports multiple LLM providers through LiteLLM:

- **OpenAI**: GPT-4, GPT-4o, GPT-3.5-turbo
- **Anthropic**: Claude 3.5 Sonnet, Claude 3 Opus
- **Google Gemini**: Gemini 2.0 Flash, Gemini Pro
- **Ollama**: Local models (llama3, mistral, etc.)
- **Llamafile**: Local llamafile models

Auto-detection: If `LLM_PROVIDER` is not set, the system auto-detects from available API keys.

## Quick Start

### Prerequisites

- **Docker** (recommended) - Version 20.0+ with Docker Compose support
- **Python 3.8+** (for local installation)
- **NCBI API key** (required for PubMed access)
- **LLM API key** (at least one required):
  - Google Gemini API key (recommended)
  - OpenAI API key (optional)
  - Anthropic API key (optional)
  - Ollama (local, no API key needed)

### Installation & Setup

#### Docker Installation (Recommended)

Docker avoids Python environment conflicts and provides a clean setup.

```bash
cd /path/to/bioanalyzer-backend

chmod +x install.sh
./install.sh

docker compose build
docker compose up -d

docker compose ps
curl http://localhost:8000/health
```

#### Local Python Installation

Note: This may encounter issues with externally managed Python environments on modern Linux distributions.

```bash
# Clone and setup
git clone https://github.com/waldronlab/bioanalyzer-backend.git
cd bioanalyzer-backend

# Create virtual environment (if python3-venv is available)
python3 -m venv .venv
source .venv/bin/activate

# Install dependencies and package
# The package uses pyproject.toml (PEP 518/621) for modern Python packaging
pip install -e .
# Or install with optional dependencies:
# pip install -e .[dev]  # for development dependencies
# pip install -e .[cli]   # for CLI enhancements

# Set up environment (optional)
cp .env.example .env
# Edit .env with your API keys
```

### Verification

After installation, verify everything works:

```bash
docker compose ps
curl http://localhost:8000/health

export PATH="$PATH:/home/ronald/.local/bin"
BioAnalyzer fields
BioAnalyzer status
```

Open http://localhost:8000/docs for API documentation.

## Usage

### CLI Commands

#### System Management
```bash
BioAnalyzer build                    # Build Docker containers
BioAnalyzer start                    # Start the application
BioAnalyzer stop                     # Stop the application
BioAnalyzer restart                  # Restart the application
BioAnalyzer status                   # Check system status
```

#### Paper Analysis
```bash
BioAnalyzer analyze 12345678         # Analyze single paper
BioAnalyzer analyze 12345678,87654321 # Analyze multiple papers
BioAnalyzer analyze --file pmids.txt # Analyze from file
BioAnalyzer fields                   # Show field information
```

#### Paper Retrieval
```bash
BioAnalyzer retrieve 12345678        # Retrieve single paper
BioAnalyzer retrieve 12345678,87654321 # Retrieve multiple papers
BioAnalyzer retrieve --file pmids.txt # Retrieve from file
BioAnalyzer retrieve 12345678 --save  # Save individual files
BioAnalyzer retrieve 12345678 --format json # JSON output
BioAnalyzer retrieve 12345678 --output results.csv # Save to file
```

#### Settings & Configuration (RAG Configuration)
```bash
# View current settings (including RAG configuration)
BioAnalyzer settings view

# View RAG settings specifically
BioAnalyzer settings view | grep -A 10 "RAG"

# Save RAG configuration
BioAnalyzer settings save --file rag-config.json

# Load and apply RAG configuration
BioAnalyzer settings load --file rag-config.json --apply

# Apply RAG preset (fast, balanced, high_quality)
BioAnalyzer settings preset balanced --save
```

**Note:** RAG features are configured through the settings system. The CLI uses the v2 API which supports RAG by default. See [RAG Guide](docs/RAG_GUIDE.md) for detailed RAG configuration and usage.

### API Endpoints

#### Analysis Endpoints (v1 - Backward Compatible)
```http
GET /api/v1/analyze/{pmid}           # Analyze paper for BugSigDB fields (simple)
POST /api/v1/analyze/{pmid}           # Analyze paper (POST method)
GET /api/v1/fields                    # Get field information
```

#### Analysis Endpoints (v2 - RAG-Enhanced)
```http
GET /api/v2/analyze/{pmid}            # Analyze with RAG features
POST /api/v2/analyze                   # Analyze with custom RAG config
POST /api/v2/analyze/batch            # Batch analysis with RAG
GET /api/v2/rag/config                # Get RAG configuration
```

#### Retrieval Endpoints
```http
GET /api/v1/retrieve/{pmid}           # Retrieve full paper data
POST /api/v1/retrieve/batch           # Batch retrieval
GET /api/v1/retrieve/search?q=query   # Search papers
```

#### System Endpoints
```http
GET /health                           # System health check
GET /api/v1/status                    # Detailed system status
GET /api/v1/metrics                   # Performance metrics
GET /api/v1/config                   # Configuration info
```

### Web Interface

Once started:
- Main Interface: http://localhost:3000
- API Documentation: http://localhost:8000/docs
- Health Check: http://localhost:8000/health

## Configuration

### Environment Variables

#### Required API Keys
| Variable | Description | Required | Default |
|----------|-------------|----------|---------|
| `NCBI_API_KEY` | NCBI API key for PubMed access | Yes | - |
| `EMAIL` | Contact email for API requests | Yes | bioanalyzer@example.com |

#### LLM Provider Configuration
| Variable | Description | Required | Default |
|----------|-------------|----------|---------|
| `GEMINI_API_KEY` | Google Gemini API key | No* | - |
| `OPENAI_API_KEY` | OpenAI API key | No* | - |
| `ANTHROPIC_API_KEY` | Anthropic API key | No* | - |
| `LLM_PROVIDER` | LLM provider (openai/anthropic/gemini/ollama/llamafile) | No | Auto-detect |
| `LLM_MODEL` | Specific model to use | No | Provider default |
| `OLLAMA_BASE_URL` | Ollama server URL (for local models) | No | http://localhost:11434 |

*At least one LLM API key is required for analysis functionality.

#### RAG Configuration (v2 API)

The RAG (Retrieval-Augmented Generation) system enhances analysis accuracy through contextual summarization and chunk re-ranking. See [RAG Guide](docs/RAG_GUIDE.md) for comprehensive documentation.

| Variable | Description | Required | Default |
|----------|-------------|----------|---------|
| `RAG_SUMMARY_PROVIDER` | LLM provider for summarization | No | Auto-detect |
| `RAG_SUMMARY_MODEL` | Model for summarization | No | Provider default |
| `RAG_SUMMARY_LENGTH` | Summary length (short/medium/long) | No | medium |
| `RAG_SUMMARY_QUALITY` | Summary quality (fast/balanced/high) | No | balanced |
| `RAG_RERANK_METHOD` | Re-ranking method (keyword/llm/hybrid) | No | hybrid |
| `RAG_USE_SUMMARY_CACHE` | Enable summary caching | No | true |
| `RAG_MAX_SUMMARY_KEY_POINTS` | Max key points per summary | No | 5 |
| `RAG_TOP_K_CHUNKS` | Top K chunks after re-ranking | No | 10 |

**Quick RAG Setup:**
```bash
# Fast processing
export RAG_SUMMARY_QUALITY="fast"
export RAG_RERANK_METHOD="keyword"
export RAG_TOP_K_CHUNKS="5"

# High accuracy
export RAG_SUMMARY_QUALITY="high"
export RAG_RERANK_METHOD="llm"
export RAG_TOP_K_CHUNKS="20"

# Balanced (recommended)
export RAG_SUMMARY_QUALITY="balanced"
export RAG_RERANK_METHOD="hybrid"
export RAG_TOP_K_CHUNKS="10"
```

#### Performance Configuration
| Variable | Description | Required | Default |
|----------|-------------|----------|---------|
| `USE_FULLTEXT` | Enable full text retrieval | No | true |
| `API_TIMEOUT` | API request timeout (seconds) | No | 30 |
| `ANALYSIS_TIMEOUT` | Analysis timeout (seconds) | No | 45 |
| `GEMINI_TIMEOUT` | Gemini API timeout (seconds) | No | 30 |
| `NCBI_RATE_LIMIT_DELAY` | Rate limiting delay (seconds) | No | 0.34 |
| `CACHE_VALIDITY_HOURS` | Cache validity period | No | 24 |

### Configuration Files

- `config/requirements.txt`: Python dependencies
- `app/utils/config.py`: Application configuration
- `docker-compose.yml`: Docker services configuration

## The 6 Essential BugSigDB Fields

The system analyzes papers for these fields:

1. Host Species: The organism being studied (Human, Mouse, Rat, etc.)
2. Body Site: Sample collection location (Gut, Oral, Skin, etc.)
3. Condition: Disease/treatment/exposure being studied
4. Sequencing Type: Molecular method used (16S, metagenomics, etc.)
5. Taxa Level: Taxonomic level analyzed (phylum, genus, species, etc.)
6. Sample Size: Number of samples or participants

### Field Status Values

- PRESENT: Information about the microbiome signature is complete and clear
- PARTIALLY_PRESENT: Some information available but incomplete
- ABSENT: Information is missing

## Architecture Details

### Service Layer Architecture

#### PubMedRetriever
- **Purpose**: Core PubMed data retrieval
- **Features**: Metadata extraction, PMC full text retrieval
- **Dependencies**: requests, xml.etree.ElementTree
- **Rate Limiting**: NCBI-compliant request throttling
- **Caching**: SQLite-based cache for metadata and full text

#### BugSigDBAnalyzer
- **Purpose**: AI-powered field extraction for 6 essential BugSigDB fields
- **Features**: 
  - Simple analysis (v1 API)
  - RAG-enhanced analysis (v2 API)
  - Automatic chunking when full text available
  - Field validation and confidence scoring
- **Dependencies**: UnifiedQA, AdvancedRAGService, ChunkingService
- **Output**: Structured field data with confidence scores

#### AdvancedRAGService
- **Purpose**: Advanced RAG with contextual summarization and chunk re-ranking
- **Features**:
  - Contextual summarization (query-aware summaries)
  - Chunk re-ranking (keyword, LLM, or hybrid methods)
  - Relevance scoring
  - Summary caching for performance
- **Dependencies**: ContextualSummarizationService, ChunkReRanker
- **Use Case**: v2 API endpoints for improved extraction accuracy
- **Documentation**: See [RAG Guide](docs/RAG_GUIDE.md) for detailed usage and examples

#### ContextualSummarizationService
- **Purpose**: Generate query-aware summaries of text chunks
- **Features**:
  - Query-specific summarization
  - Key point extraction
  - Configurable summary length and quality
  - Caching for reuse
- **Dependencies**: LLMProviderManager (LiteLLM)

#### ChunkReRanker
- **Purpose**: Re-rank text chunks by relevance to query
- **Methods**:
  - **Keyword**: Fast keyword-based scoring (no LLM needed)
  - **LLM**: Accurate LLM-based relevance scoring
  - **Hybrid**: Combines both methods for best results
- **Dependencies**: LLMProviderManager (for LLM/hybrid methods)

#### LLMProviderManager
- **Purpose**: Unified interface for multiple LLM providers via LiteLLM
- **Supported Providers**: OpenAI, Anthropic, Gemini, Ollama, Llamafile
- **Features**: Auto-detection, provider switching, unified API
- **Dependencies**: litellm

#### UnifiedQA
- **Purpose**: Unified interface for QA operations
- **Backends**: 
  - LLMProviderManager (preferred, via LiteLLM)
  - PaperQAAgent (fallback)
  - GeminiQA (fallback)
- **Features**: Chat, question answering, image analysis

#### CacheManager
- **Purpose**: SQLite-based caching for analysis results and metadata
- **Features**: 
  - Analysis result caching (24h validity)
  - Metadata caching
  - Full text caching
  - Cache statistics and management

### Complete Data Flow Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                    v1 API Flow (Simple)                      │
└─────────────────────────────────────────────────────────────┘

PMID → PubMedRetriever → Cache Check → NCBI API (if miss)
  ↓
Text Preparation (title + abstract + full text)
  ↓
For each field (6 fields):
  ↓
UnifiedQA → LLMProviderManager → LLM (Gemini/OpenAI/etc.)
  ↓
Field Validation & Scoring
  ↓
Aggregate Results → Cache → JSON/CSV/Table Output

┌─────────────────────────────────────────────────────────────┐
│                    v2 API Flow (RAG-Enhanced)               │
└─────────────────────────────────────────────────────────────┘

PMID → PubMedRetriever → Cache Check → NCBI API (if miss)
  ↓
Text Preparation + Chunking (if full text > 1000 chars)
  ↓
For each field (6 fields):
  ↓
AdvancedRAGService:
  ├── ChunkReRanker → Rank chunks by relevance
  │   └── Method: keyword/llm/hybrid
  └── ContextualSummarizationService → Generate query-aware summaries
      ├── Query: "What host species is being studied?"
      ├── Summarize top K chunks
      └── Extract key points
  ↓
UnifiedQA → LLM with contextual context
  ↓
Field Validation & Scoring
  ↓
Aggregate Results + RAG Stats → Cache → JSON/CSV/Table Output
```

### Error Handling Strategy

1. **Network Errors**: Retry with exponential backoff
2. **API Errors**: Graceful degradation with fallback methods
3. **Parsing Errors**: Error reporting with context
4. **Missing Data**: Clear indication of unavailable information

## API Examples

### v1 API - Simple Analysis
```bash
# Analyze a paper (simple method)
curl -X GET "http://localhost:8000/api/v1/analyze/12345678"
```

### v2 API - RAG-Enhanced Analysis

RAG (Retrieval-Augmented Generation) enhances analysis accuracy through contextual summarization and chunk re-ranking. **See [RAG Guide](docs/RAG_GUIDE.md) for comprehensive documentation, examples, and troubleshooting.**

```bash
# Analyze with default RAG settings
curl -X GET "http://localhost:8000/api/v2/analyze/12345678?use_rag=true"

# Analyze with custom RAG configuration
curl -X POST "http://localhost:8000/api/v2/analyze" \
  -H "Content-Type: application/json" \
  -d '{
    "pmid": "12345678",
    "rag_config": {
      "enabled": true,
      "summary_length": "medium",
      "summary_quality": "balanced",
      "rerank_method": "hybrid",
      "top_k_chunks": 10
    }
  }'

# Batch analysis with RAG
curl -X POST "http://localhost:8000/api/v2/analyze/batch" \
  -H "Content-Type: application/json" \
  -d '{
    "pmids": ["12345678", "87654321"],
    "rag_config": {
      "enabled": true,
      "top_k_chunks": 10
    }
  }'

# Get RAG configuration
curl -X GET "http://localhost:8000/api/v2/rag/config"
```

**Quick RAG Configuration Examples:**

```bash
# Fast processing (for batch jobs)
curl -X GET "http://localhost:8000/api/v2/analyze/12345678?use_rag=true&summary_quality=fast&rerank_method=keyword&top_k_chunks=5"

# High accuracy (for critical analysis)
curl -X GET "http://localhost:8000/api/v2/analyze/12345678?use_rag=true&summary_quality=high&rerank_method=llm&top_k_chunks=20"
```

### Retrieval Request
```bash
curl -X GET "http://localhost:8000/api/v1/retrieve/12345678"
```

### Batch Retrieval
```bash
curl -X POST "http://localhost:8000/api/v1/retrieve/batch" \
  -H "Content-Type: application/json" \
  -d '{"pmids": ["12345678", "87654321"]}'
```

### Response Format
```json
{
  "pmid": "12345678",
  "title": "Gut microbiome analysis in patients with IBD",
  "abstract": "This study examines...",
  "journal": "Nature Medicine",
  "authors": ["Smith J", "Doe A"],
  "publication_date": "2023",
  "full_text": "Complete paper text...",
  "has_full_text": true,
  "fields": {
    "host_species": {
      "status": "PRESENT",
      "value": "Human",
      "confidence": 0.95
    },
    "body_site": {
      "status": "PRESENT",
      "value": "Gut",
      "confidence": 0.92
    }
  },
  "retrieval_timestamp": "2023-12-01T10:30:00Z"
}
```

## Testing

### Run Tests
```bash
# All tests
pytest

# With coverage
pytest --cov=app

# Specific module
pytest tests/test_retrieval.py

# In Docker
docker exec -it bioanalyzer-api pytest
```

### Test Coverage
- Unit tests for all service classes
- Integration tests for API endpoints
- CLI command testing
- Error handling validation

## Project Structure

```
bioanalyzer-backend/
├── app/                           # Main application code
│   ├── api/                      # API layer
│   │   ├── app.py               # FastAPI application
│   │   ├── models/              # Pydantic models
│   │   ├── routers/             # API routes
│   │   └── utils/               # API utilities
│   ├── models/                   # AI models and configuration
│   │   ├── llm_provider.py       # LiteLLM provider manager
│   │   ├── gemini_qa.py         # Gemini AI integration (fallback)
│   │   ├── unified_qa.py         # Unified QA system
│   │   └── config.py            # Model configuration
│   ├── services/                 # Business logic services
│   │   ├── data_retrieval.py    # Core PubMed retrieval
│   │   ├── bugsigdb_analyzer.py  # Field analysis
│   │   ├── advanced_rag.py     # Advanced RAG service
│   │   ├── contextual_summarization.py # Contextual summarization
│   │   ├── chunk_reranking.py   # Chunk re-ranking
│   │   ├── cache_manager.py     # SQLite caching
│   │   └── vector_store_service.py # Vector storage
│   └── utils/                    # Utilities and helpers
│       ├── config.py             # Configuration management
│       ├── text_processing.py    # Text processing utilities
│       ├── chunking.py           # Text chunking service
│       └── performance_logger.py # Performance monitoring
├── config/                       # Configuration files
│   ├── requirements.txt         # Python dependencies (legacy)
│   └── pytest.ini              # Test configuration
├── pyproject.toml                # Modern Python packaging (PEP 518/621)
├── setup.py                      # Legacy setup.py (kept for backward compatibility)
├── docs/                         # Documentation
│   ├── README.md                # Main documentation
│   ├── DOCKER_DEPLOYMENT.md     # Docker deployment guide
│   └── QUICKSTART.md            # Quick start guide
├── scripts/                      # Utility scripts
│   ├── log_cleanup.py           # Log management
│   ├── performance_monitor.py   # Performance monitoring
│   └── log_dashboard.py         # Log visualization
├── tests/                        # Test suite
│   ├── test_api.py              # API tests
│   ├── test_retrieval.py        # Retrieval tests
│   └── test_cli.py              # CLI tests
├── cli.py                        # CLI interface
├── main.py                       # API server entry point
├── docker-compose.yml            # Docker services
├── Dockerfile                    # Docker image
└── README.md                     # This file
```

## Deployment

### Docker Deployment

#### Development
```bash
# Build and start development environment
docker-compose up -d

# View logs
docker-compose logs -f

# Access container
docker exec -it bioanalyzer-api bash
```

#### Production
```bash
# Build production image
docker build -t bioanalyzer-backend:latest .

# Run production container
docker run -d -p 8000:8000 \
  -e GEMINI_API_KEY=your_key \
  -e NCBI_API_KEY=your_key \
  bioanalyzer-backend:latest
```

### Local Deployment

#### API Server
```bash
# Start API server
python main.py

# Or with uvicorn
uvicorn app.api.app:app --host 0.0.0.0 --port 8000 --reload
```

#### CLI Usage
```bash
# Direct CLI usage
python cli.py analyze 12345678
python cli.py retrieve 12345678 --save
```

## Performance

### Optimization Features

- **Caching**: Built-in caching for frequently accessed papers
- **Rate Limiting**: NCBI-compliant request throttling
- **Batch Processing**: Efficient multi-paper processing
- **Async Support**: Non-blocking API operations
- **Memory Management**: Optimized for large-scale analysis

### Performance Metrics

- **v1 Analysis Speed**: ~2-5 seconds per paper (simple method)
- **v2 Analysis Speed**: ~5-10 seconds per paper (RAG-enhanced)
- **Retrieval Speed**: ~1-3 seconds per paper
- **Throughput**: 
  - v1: 10-20 papers per minute
  - v2: 5-10 papers per minute (with RAG)
- **Memory Usage**: ~100-200MB base + 50MB per concurrent request
- **Cache Hit Rate**: ~60-80% (for frequently analyzed papers)

## Development

### Setting Up Development Environment

```bash
# Clone repository
git clone https://github.com/waldronlab/bioanalyzer-backend.git
cd bioanalyzer-backend

# Create virtual environment
python -m venv .venv
source .venv/bin/activate  # On Windows: .venv\Scripts\activate

# Install dependencies and package
# The package uses pyproject.toml (PEP 518/621) for modern Python packaging
pip install -e .[dev]  # Installs package with development dependencies

# Set up pre-commit hooks (see CONTRIBUTING.md for details)
# Using Docker (recommended):
./scripts/pre-commit-docker.sh

# Or manually with Docker:
docker run --rm \
  -v "$(pwd):/workspace" -w /workspace \
  -v ~/.cache/pre-commit:/root/.cache/pre-commit \
  python:3.11-slim \
  bash -c "pip install --quiet pre-commit && pre-commit run --all-files"
```

### Code Quality

```bash
# Format code
black .

# Lint code
flake8 .

# Type checking
mypy .

# Run tests
pytest
```

### Adding New Features

1. **Service Layer**: Add new services in `app/services/`
2. **API Endpoints**: Add routes in `app/api/routers/`
3. **CLI Commands**: Extend `cli.py` with new commands
4. **Models**: Add Pydantic models in `app/api/models/`

## Troubleshooting

### Common Issues

#### Python Environment Issues
```bash
# Error: externally-managed-environment
# Solution: Use Docker (recommended) or install python3-venv
sudo apt install python3.12-venv python3-full
python3 -m venv .venv
source .venv/bin/activate
```

#### Docker Compose Issues
```bash
# Error: docker-compose command not found
# Solution: Use newer Docker Compose syntax
docker compose build    # Instead of docker-compose build
docker compose up -d    # Instead of docker-compose up -d
```

#### CLI Command Not Found
```bash
# Error: BioAnalyzer command not found
# Solution: Add to PATH
export PATH="$PATH:/home/<copmuter_name>/.local/bin"
# Or restart terminal after running ./install.sh
```

#### API Not Responding
```bash
# Check container status
docker compose ps

# Check logs
docker compose logs

# Restart if needed
docker compose restart
```

#### Missing API Keys
```bash
# Warning: GeminiQA not initialized
# This is normal - system works without API keys
# For full functionality, set environment variables:
export GEMINI_API_KEY="your_gemini_key"
export NCBI_API_KEY="your_ncbi_key"
```

### Debug Mode

Enable debug logging:
```bash
export LOG_LEVEL=DEBUG
python main.py
```

## Documentation

- [QUICKSTART.md](docs/QUICKSTART.md) - Get running in 5 minutes
- [SETUP_GUIDE.md](SETUP_GUIDE.md) - Detailed setup steps
- [ARCHITECTURE.md](docs/ARCHITECTURE.md) - System architecture
- [RAG_GUIDE.md](docs/RAG_GUIDE.md) - RAG features documentation
- [SETTINGS.md](docs/SETTINGS.md) - Configuration system
- [DOCKER_DEPLOYMENT.md](docs/DOCKER_DEPLOYMENT.md) - Docker deployment
- API Documentation: http://localhost:8000/docs (when running)

## Contributing

Please see [CONTRIBUTING.md](CONTRIBUTING.md) for guidelines on contributing to this project, including:
- Development setup
- Pre-commit hooks installation and usage
- Code style guidelines
- Testing requirements
- Pull request process

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/amazing-feature`)
3. Commit your changes (`git commit -m 'Add amazing feature'`)
4. Push to the branch (`git push origin feature/amazing-feature`)
5. Open a Pull Request

### Development Guidelines

- Follow PEP 8 style guidelines
- Add tests for new functionality
- Update documentation for API changes
- Use type hints for all functions
- Write comprehensive docstrings

## License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

## Acknowledgments

- **BugSigDB Team**: For the microbial signatures database
- **NCBI**: For PubMed data access and E-utilities API
- **Google**: For Gemini AI capabilities
- **LiteLLM**: For multi-provider LLM support
- **FastAPI**: For the excellent web framework
- **Docker**: For containerization technology

## Support

- **Issues**: [GitHub Issues](https://github.com/waldronlab/bioanalyzer-backend/issues)
- **Discussions**: [GitHub Discussions](https://github.com/waldronlab/bioanalyzer-backend/discussions)
- **Documentation**: [Project Wiki](https://github.com/waldronlab/bioanalyzer-backend/wiki)

---

Happy analyzing!
