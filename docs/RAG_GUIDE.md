# RAG Features Guide

Comprehensive guide to BioAnalyzer's Retrieval-Augmented Generation (RAG) features for enhanced paper analysis.

## Table of Contents

- [Overview](#overview)
- [What is RAG?](#what-is-rag)
- [RAG Architecture](#rag-architecture)
- [Configuration](#configuration)
- [Usage Examples](#usage-examples)
- [API Reference](#api-reference)
- [Migration Guide](#migration-guide)
- [Troubleshooting](#troubleshooting)
- [Best Practices](#best-practices)

## Overview

BioAnalyzer's RAG (Retrieval-Augmented Generation) system enhances paper analysis by:

- **Contextual Summarization**: Generate query-aware summaries of relevant text chunks
- **Chunk Re-ranking**: Prioritize the most relevant chunks for each field extraction
- **Improved Accuracy**: Better field extraction through better context understanding
- **Performance Optimization**: Caching and efficient processing

RAG features are available in the **v2 API** endpoints, while the **v1 API** provides simple analysis for backward compatibility.

## What is RAG?

RAG (Retrieval-Augmented Generation) combines information retrieval with language model generation. In BioAnalyzer:

1. **Retrieval**: Text chunks are retrieved from the paper
2. **Re-ranking**: Chunks are ranked by relevance to the specific field being extracted
3. **Summarization**: Top chunks are summarized with context about the query
4. **Generation**: The LLM uses these summaries to extract field information

### Why Use RAG?

- **Better Context**: Query-aware summaries provide focused context
- **Improved Accuracy**: Re-ranking ensures the most relevant information is used
- **Handles Long Papers**: Efficiently processes full-text papers
- **Field-Specific**: Each field gets context tailored to its extraction needs

## RAG Architecture

### System Components

```
┌─────────────────────────────────────────────────────────┐
│                    RAG Pipeline                          │
└─────────────────────────────────────────────────────────┘

1. Text Chunking
   ↓
   Paper Text → Chunks (3000 chars, 100 overlap)

2. Chunk Re-ranking
   ↓
   ChunkReRanker → Rank by relevance to query
   ├── Keyword Method (fast, no LLM)
   ├── LLM Method (accurate, uses LLM)
   └── Hybrid Method (best of both)

3. Contextual Summarization
   ↓
   ContextualSummarizationService → Query-aware summaries
   ├── Generate summaries for top K chunks
   ├── Extract key points
   └── Cache summaries for reuse

4. Field Extraction
   ↓
   UnifiedQA → LLM with contextual context
   └── Extract field value with improved accuracy
```

### Component Details

#### AdvancedRAGService

The main RAG service that orchestrates the pipeline:

```python
from app.services.advanced_rag import AdvancedRAGService

rag_service = AdvancedRAGService(
    summary_provider="gemini",  # LLM provider for summarization
    summary_model="gemini/gemini-2.0-flash",  # Model for summarization
    rerank_method="hybrid",  # Re-ranking method
    cache_dir=None  # Cache directory (optional)
)
```

**Features:**
- Combines re-ranking and summarization
- Configurable quality and speed settings
- Automatic caching of summaries

#### ChunkReRanker

Re-ranks text chunks by relevance to the query:

**Methods:**

1. **Keyword** (`keyword`):
   - Fast keyword-based scoring
   - No LLM required
   - Good for simple queries
   - Fastest method

2. **LLM** (`llm`):
   - Accurate LLM-based relevance scoring
   - Uses semantic understanding
   - Most accurate method
   - Slower than keyword

3. **Hybrid** (`hybrid`) - **Recommended**:
   - Combines keyword and LLM methods
   - Best balance of speed and accuracy
   - Default method

```python
from app.services.chunk_reranking import ChunkReRanker

reranker = ChunkReRanker(
    rerank_method="hybrid",
    llm_provider="gemini",
    llm_model="gemini/gemini-2.0-flash"
)
```

#### ContextualSummarizationService

Generates query-aware summaries of text chunks:

**Configuration:**
- `summary_length`: `short`, `medium`, `long`
- `quality`: `fast`, `balanced`, `high`
- `max_key_points`: Maximum key points per summary
- `use_cache`: Enable summary caching

```python
from app.services.contextual_summarization import (
    ContextualSummarizationService,
    SummarizationConfig
)

config = SummarizationConfig(
    summary_length="medium",
    quality="balanced",
    max_key_points=5,
    use_cache=True
)

service = ContextualSummarizationService(
    summary_llm_provider="gemini",
    summary_llm_model="gemini/gemini-2.0-flash",
    config=config
)
```

## Configuration

### Environment Variables

Configure RAG features using environment variables:

```bash
# RAG Configuration
export RAG_SUMMARY_PROVIDER="gemini"           # LLM provider for summarization
export RAG_SUMMARY_MODEL="gemini/gemini-2.0-flash"  # Model for summarization
export RAG_SUMMARY_LENGTH="medium"             # short, medium, long
export RAG_SUMMARY_QUALITY="balanced"           # fast, balanced, high
export RAG_RERANK_METHOD="hybrid"              # keyword, llm, hybrid
export RAG_USE_SUMMARY_CACHE="true"            # Enable summary caching
export RAG_MAX_SUMMARY_KEY_POINTS="5"          # Max key points per summary
export RAG_TOP_K_CHUNKS="10"                   # Number of top chunks to use
```

### Settings File

Use the settings system for comprehensive configuration:

```json
{
  "rag": {
    "enabled": true,
    "top_k_chunks": 10,
    "rerank_method": "hybrid",
    "summary_length": "medium",
    "summary_quality": "balanced",
    "summary_provider": "gemini",
    "summary_model": "gemini/gemini-2.0-flash",
    "use_cache": true,
    "max_summary_key_points": 5
  }
}
```

Load settings:
```bash
BioAnalyzer settings load --file settings.json --apply
```

### Configuration Options

#### Summary Length

- **`short`**: Brief summaries (~100 words)
  - Fastest processing
  - Less context
  - Good for simple fields

- **`medium`** (default): Balanced summaries (~200 words)
  - Good balance of speed and context
  - Recommended for most use cases

- **`long`**: Detailed summaries (~400 words)
  - Most context
  - Slower processing
  - Best for complex fields

#### Summary Quality

- **`fast`**: Quick summaries
  - Lower temperature
  - Faster generation
  - Good for batch processing

- **`balanced`** (default): Balanced quality
  - Good balance of speed and quality
  - Recommended for most use cases

- **`high`**: High-quality summaries
  - Higher temperature
  - More detailed
  - Best for accuracy-critical tasks

#### Re-ranking Method

- **`keyword`**: Fast keyword-based
  - No LLM required
  - Fastest method
  - Good for simple queries

- **`llm`**: LLM-based relevance
  - Most accurate
  - Uses semantic understanding
  - Slower than keyword

- **`hybrid`** (default): Combined approach
  - Best balance
  - Recommended for most use cases

## Usage Examples

### Python API Usage

#### Basic RAG Analysis

```python
import asyncio
from app.services.bugsigdb_analyzer import analyze_paper_with_rag

async def analyze_with_rag():
    result = await analyze_paper_with_rag(
        pmid="12345678",
        use_rag=True
    )
    print(result)

asyncio.run(analyze_with_rag())
```

#### Custom RAG Configuration

```python
import asyncio
from app.services.bugsigdb_analyzer import analyze_paper_with_rag

async def analyze_with_custom_rag():
    rag_config = {
        "enabled": True,
        "top_k_chunks": 15,
        "rerank_method": "hybrid",
        "summary_length": "long",
        "summary_quality": "high",
        "summary_provider": "gemini",
        "summary_model": "gemini/gemini-2.0-flash",
        "use_cache": True
    }
    
    result = await analyze_paper_with_rag(
        pmid="12345678",
        rag_config=rag_config,
        use_rag=True
    )
    print(result)

asyncio.run(analyze_with_custom_rag())
```

#### Using AdvancedRAGService Directly

```python
import asyncio
from app.services.advanced_rag import AdvancedRAGService
from paperqa.types import Text

async def use_rag_service():
    # Initialize RAG service
    rag_service = AdvancedRAGService(
        summary_provider="gemini",
        summary_model="gemini/gemini-2.0-flash",
        rerank_method="hybrid"
    )
    
    # Prepare chunks (example)
    chunks = [
        Text(text="Chunk 1 text...", name="chunk_1"),
        Text(text="Chunk 2 text...", name="chunk_2"),
    ]
    
    # Get contextual context for a query
    query = "What host species is being studied?"
    context = await rag_service.get_contextual_context(
        chunks=chunks,
        query=query,
        top_k=10
    )
    
    print(f"Contextual context: {context}")

asyncio.run(use_rag_service())
```

### REST API Usage

#### GET Request with RAG

```bash
# Analyze with default RAG settings
curl -X GET "http://localhost:8000/api/v2/analyze/12345678?use_rag=true"

# Custom RAG parameters
curl -X GET "http://localhost:8000/api/v2/analyze/12345678?use_rag=true&top_k_chunks=15&rerank_method=hybrid&summary_length=long&summary_quality=high"
```

#### POST Request with Custom RAG Config

```bash
curl -X POST "http://localhost:8000/api/v2/analyze" \
  -H "Content-Type: application/json" \
  -d '{
    "pmid": "12345678",
    "rag_config": {
      "enabled": true,
      "top_k_chunks": 15,
      "rerank_method": "hybrid",
      "summary_length": "long",
      "summary_quality": "high",
      "summary_provider": "gemini",
      "summary_model": "gemini/gemini-2.0-flash",
      "use_cache": true,
      "max_summary_key_points": 5
    }
  }'
```

#### Batch Analysis with RAG

```bash
curl -X POST "http://localhost:8000/api/v2/analyze/batch" \
  -H "Content-Type: application/json" \
  -d '{
    "pmids": ["12345678", "87654321", "11223344"],
    "rag_config": {
      "enabled": true,
      "top_k_chunks": 10,
      "rerank_method": "hybrid"
    }
  }'
```

### CLI Usage

Currently, RAG features are configured through settings. Use the settings system:

```bash
# View current RAG settings
BioAnalyzer settings view | grep -A 10 "RAG"

# Configure RAG settings
BioAnalyzer settings save --file rag-config.json

# Load RAG configuration
BioAnalyzer settings load --file rag-config.json --apply
```

## API Reference

### v2 API Endpoints

#### GET `/api/v2/analyze/{pmid}`

Analyze a paper with RAG features.

**Query Parameters:**
- `use_rag` (bool): Enable RAG features (default: `true`)
- `top_k_chunks` (int, optional): Number of top chunks to use
- `rerank_method` (str, optional): Re-ranking method (`keyword`, `llm`, `hybrid`)
- `summary_length` (str, optional): Summary length (`short`, `medium`, `long`)
- `summary_quality` (str, optional): Summary quality (`fast`, `balanced`, `high`)

**Example:**
```bash
GET /api/v2/analyze/12345678?use_rag=true&top_k_chunks=15&rerank_method=hybrid
```

#### POST `/api/v2/analyze`

Analyze a paper with custom RAG configuration.

**Request Body:**
```json
{
  "pmid": "12345678",
  "rag_config": {
    "enabled": true,
    "top_k_chunks": 10,
    "rerank_method": "hybrid",
    "summary_length": "medium",
    "summary_quality": "balanced",
    "summary_provider": "gemini",
    "summary_model": "gemini/gemini-2.0-flash",
    "use_cache": true,
    "max_summary_key_points": 5
  }
}
```

**Response:**
```json
{
  "pmid": "12345678",
  "title": "Paper Title",
  "fields": {
    "host_species": {
      "status": "PRESENT",
      "value": "Human",
      "confidence": 0.95
    }
  },
  "rag_metadata": {
    "enabled": true,
    "chunks_processed": 15,
    "chunks_used": 10,
    "rerank_method": "hybrid",
    "summary_length": "medium",
    "summary_quality": "balanced"
  },
  "processing_time": 8.5
}
```

#### POST `/api/v2/analyze/batch`

Batch analysis with RAG.

**Request Body:**
```json
{
  "pmids": ["12345678", "87654321"],
  "rag_config": {
    "enabled": true,
    "top_k_chunks": 10
  }
}
```

#### GET `/api/v2/rag/config`

Get current RAG configuration.

**Response:**
```json
{
  "enabled": true,
  "top_k_chunks": 10,
  "rerank_method": "hybrid",
  "summary_length": "medium",
  "summary_quality": "balanced",
  "summary_provider": "gemini",
  "summary_model": "gemini/gemini-2.0-flash",
  "use_cache": true,
  "max_summary_key_points": 5
}
```

## Migration Guide

### Migrating from v1 to v2 API

The v1 API provides simple analysis without RAG. To migrate to v2:

#### Step 1: Update API Endpoints

**Before (v1):**
```bash
GET /api/v1/analyze/12345678
```

**After (v2):**
```bash
GET /api/v2/analyze/12345678?use_rag=true
```

#### Step 2: Update Request Format

**Before (v1):**
```python
response = requests.get(f"http://localhost:8000/api/v1/analyze/{pmid}")
```

**After (v2):**
```python
# With default RAG settings
response = requests.get(f"http://localhost:8000/api/v2/analyze/{pmid}?use_rag=true")

# With custom RAG config
response = requests.post(
    "http://localhost:8000/api/v2/analyze",
    json={
        "pmid": pmid,
        "rag_config": {
            "enabled": True,
            "top_k_chunks": 10
        }
    }
)
```

#### Step 3: Handle Response Changes

v2 responses include RAG metadata:

```python
# v1 response
{
    "pmid": "12345678",
    "fields": {...}
}

# v2 response
{
    "pmid": "12345678",
    "fields": {...},
    "rag_metadata": {
        "enabled": true,
        "chunks_processed": 15,
        "chunks_used": 10
    }
}
```

#### Step 4: Configure RAG Settings

Set up RAG configuration:

```bash
# Using environment variables
export RAG_SUMMARY_QUALITY="balanced"
export RAG_RERANK_METHOD="hybrid"

# Or using settings file
BioAnalyzer settings save --file rag-config.json
```

### Backward Compatibility

- **v1 API remains available**: All v1 endpoints continue to work
- **No breaking changes**: v1 API behavior unchanged
- **Gradual migration**: Migrate endpoints one at a time

## Troubleshooting

### Common Issues

#### RAG Not Working

**Symptoms:**
- RAG features not being used
- No improvement in accuracy

**Solutions:**
1. Check RAG is enabled:
   ```bash
   curl "http://localhost:8000/api/v2/analyze/12345678?use_rag=true"
   ```

2. Verify configuration:
   ```bash
   curl "http://localhost:8000/api/v2/rag/config"
   ```

3. Check logs for errors:
   ```bash
   docker compose logs | grep -i rag
   ```

#### Slow Performance

**Symptoms:**
- Analysis takes too long
- Timeout errors

**Solutions:**
1. Use faster settings:
   ```json
   {
     "summary_quality": "fast",
     "rerank_method": "keyword",
     "top_k_chunks": 5
   }
   ```

2. Enable caching:
   ```json
   {
     "use_cache": true
   }
   ```

3. Reduce chunk count:
   ```json
   {
     "top_k_chunks": 5
   }
   ```

#### Low Accuracy

**Symptoms:**
- Field extraction not accurate
- Missing information

**Solutions:**
1. Use higher quality settings:
   ```json
   {
     "summary_quality": "high",
     "summary_length": "long",
     "rerank_method": "llm",
     "top_k_chunks": 20
   }
   ```

2. Check if full text is available:
   ```bash
   curl "http://localhost:8000/api/v1/retrieve/12345678" | jq .has_full_text
   ```

3. Verify LLM provider is working:
   ```bash
   curl "http://localhost:8000/health"
   ```

#### Cache Issues

**Symptoms:**
- Summaries not being cached
- Cache not working

**Solutions:**
1. Verify cache is enabled:
   ```bash
   export RAG_USE_SUMMARY_CACHE="true"
   ```

2. Check cache directory permissions:
   ```bash
   ls -la cache/
   ```

3. Clear cache if needed:
   ```bash
   rm -rf cache/summaries/*
   ```

### Debug Mode

Enable debug logging:

```bash
export LOG_LEVEL=DEBUG
docker compose restart
```

Check logs:
```bash
docker compose logs -f | grep -i rag
```

## Best Practices

### Performance Optimization

1. **Use appropriate quality settings**:
   - `fast` for batch processing
   - `balanced` for most use cases
   - `high` for accuracy-critical tasks

2. **Enable caching**:
   - Reduces redundant summarization
   - Improves performance for repeated queries

3. **Choose right re-ranking method**:
   - `keyword` for speed
   - `hybrid` for balance (recommended)
   - `llm` for accuracy

4. **Optimize chunk count**:
   - Start with default (10)
   - Increase for complex papers
   - Decrease for faster processing

### Accuracy Improvement

1. **Use full text when available**:
   - RAG works best with full text
   - Abstracts may not have enough context

2. **Adjust summary length**:
   - `long` for complex fields
   - `medium` for most fields
   - `short` for simple fields

3. **Use LLM re-ranking for complex queries**:
   - Better semantic understanding
   - More accurate chunk selection

### Configuration Recommendations

**For Speed:**
```json
{
  "summary_quality": "fast",
  "summary_length": "short",
  "rerank_method": "keyword",
  "top_k_chunks": 5,
  "use_cache": true
}
```

**For Accuracy:**
```json
{
  "summary_quality": "high",
  "summary_length": "long",
  "rerank_method": "llm",
  "top_k_chunks": 20,
  "use_cache": true
}
```

**For Balance (Recommended):**
```json
{
  "summary_quality": "balanced",
  "summary_length": "medium",
  "rerank_method": "hybrid",
  "top_k_chunks": 10,
  "use_cache": true
}
```

## See Also

- [Settings Documentation](SETTINGS.md) - Comprehensive settings system
- [Architecture Guide](ARCHITECTURE.md) - System architecture
- [API Documentation](http://localhost:8000/docs) - Interactive API docs
- [Quick Start Guide](QUICKSTART.md) - Getting started

