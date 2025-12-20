# API v2 - RAG Integration Documentation

## Overview

The BioAnalyzer API v2 introduces advanced RAG (Retrieval Augmented Generation) features to improve field extraction accuracy. This includes contextual summarization and chunk re-ranking capabilities.

## API Versioning

- **v1 API** (`/api/v1`): Original endpoints, maintained for backward compatibility
- **v2 API** (`/api/v2`): Enhanced endpoints with RAG support

## RAG Features

### Contextual Summarization
- Query-aware summaries of relevant text chunks
- Focuses on information directly relevant to the field being extracted
- Configurable summary length (short, medium, long)
- Configurable quality settings (fast, balanced, high)

### Chunk Re-ranking
- Relevance-based ranking of text chunks
- Three methods available:
  - **keyword**: Keyword matching-based ranking
  - **llm**: LLM-based relevance scoring
  - **hybrid**: Combination of keyword and LLM methods

## Endpoints

### Analyze Paper (GET)

```http
GET /api/v2/analyze/{pmid}?use_rag=true&top_k_chunks=10&rerank_method=hybrid
```

**Query Parameters:**
- `use_rag` (bool, default: true): Enable/disable RAG features
- `top_k_chunks` (int, optional): Number of top chunks to use after re-ranking
- `rerank_method` (string, optional): Re-ranking method ("keyword", "llm", "hybrid")
- `summary_length` (string, optional): Summary length ("short", "medium", "long")
- `summary_quality` (string, optional): Summary quality ("fast", "balanced", "high")

**Example:**
```bash
curl "http://localhost:8000/api/v2/analyze/12345678?use_rag=true&top_k_chunks=10&rerank_method=hybrid"
```

### Analyze Paper (POST)

```http
POST /api/v2/analyze
Content-Type: application/json

{
  "pmid": "12345678",
  "use_rag": true,
  "rag_config": {
    "enabled": true,
    "top_k_chunks": 10,
    "rerank_method": "hybrid",
    "summary_length": "medium",
    "summary_quality": "balanced",
    "summary_provider": "gemini",
    "summary_model": "gemini/gemini-2.0-flash",
    "use_cache": true
  }
}
```

**Request Body:**
- `pmid` (string, required): PubMed ID
- `use_rag` (bool, default: true): Enable/disable RAG
- `rag_config` (object, optional): RAG configuration
  - `enabled` (bool): Enable RAG features
  - `top_k_chunks` (int): Number of top chunks to use
  - `rerank_method` (string): "keyword", "llm", or "hybrid"
  - `summary_length` (string): "short", "medium", or "long"
  - `summary_quality` (string): "fast", "balanced", or "high"
  - `summary_provider` (string, optional): LLM provider for summarization
  - `summary_model` (string, optional): Model for summarization
  - `use_cache` (bool): Enable/disable summary caching

**Example:**
```bash
curl -X POST "http://localhost:8000/api/v2/analyze" \
  -H "Content-Type: application/json" \
  -d '{
    "pmid": "12345678",
    "use_rag": true,
    "rag_config": {
      "top_k_chunks": 10,
      "rerank_method": "hybrid"
    }
  }'
```

### Batch Analysis

```http
POST /api/v2/analyze/batch
Content-Type: application/json

{
  "pmids": ["12345678", "87654321"],
  "use_rag": true,
  "rag_config": {...},
  "max_concurrent": 5
}
```

**Request Body:**
- `pmids` (array, required): List of PubMed IDs
- `use_rag` (bool, default: true): Enable/disable RAG
- `rag_config` (object, optional): RAG configuration (same as above)
- `max_concurrent` (int, default: 5): Maximum concurrent analyses

### Get RAG Configuration

```http
GET /api/v2/rag/config
```

Returns available RAG configuration options and defaults.

**Response:**
```json
{
  "default_config": {
    "enabled": true,
    "top_k_chunks": 10,
    "rerank_method": "hybrid",
    "summary_length": "medium",
    "summary_quality": "balanced",
    "use_cache": true
  },
  "available_rerank_methods": ["keyword", "llm", "hybrid"],
  "available_summary_lengths": ["short", "medium", "long"],
  "available_summary_qualities": ["fast", "balanced", "high"],
  "available_providers": ["gemini", "openai", "anthropic"]
}
```

## Response Format

### Enhanced Analysis Result

```json
{
  "pmid": "12345678",
  "title": "Paper Title",
  "authors": ["Author 1", "Author 2"],
  "journal": "Journal Name",
  "publication_date": "2024-01-01",
  "fields": {
    "host_species": {
      "status": "PRESENT",
      "value": "Human",
      "confidence": 0.95,
      "reason_if_missing": null
    },
    ...
  },
  "analysis_timestamp": "2024-01-01T12:00:00Z",
  "model_used": "gemini",
  "processing_time": 2.5,
  "rag_enabled": true,
  "rag_stats": {
    "chunks_processed": 25,
    "chunks_ranked": 25,
    "chunks_summarized": 10,
    "avg_relevance_score": 0.85,
    "avg_confidence": 0.90,
    "rerank_method": "hybrid",
    "summary_length": "medium",
    "processing_time": 1.2
  },
  "rag_config_used": {
    "enabled": true,
    "top_k_chunks": 10,
    "rerank_method": "hybrid",
    ...
  }
}
```

## Backward Compatibility

The v1 API endpoints (`/api/v1/analyze/{pmid}`) remain fully functional and unchanged. Existing integrations will continue to work without modification.

## Feature Flags

RAG features can be enabled/disabled per request using the `use_rag` parameter. When disabled, the API behaves like v1 endpoints.

## Performance Considerations

- RAG processing adds ~1-3 seconds to analysis time
- Summary caching reduces repeated processing time
- Hybrid re-ranking is more accurate but slower than keyword-only
- Higher quality summaries take longer but provide better context

## Examples

### Basic Analysis with RAG (Default Settings)

```bash
curl "http://localhost:8000/api/v2/analyze/12345678"
```

### Analysis with Custom RAG Configuration

```bash
curl -X POST "http://localhost:8000/api/v2/analyze" \
  -H "Content-Type: application/json" \
  -d '{
    "pmid": "12345678",
    "use_rag": true,
    "rag_config": {
      "top_k_chunks": 15,
      "rerank_method": "llm",
      "summary_length": "long",
      "summary_quality": "high"
    }
  }'
```

### Analysis without RAG (v1-compatible)

```bash
curl "http://localhost:8000/api/v2/analyze/12345678?use_rag=false"
```

### Batch Analysis

```bash
curl -X POST "http://localhost:8000/api/v2/analyze/batch" \
  -H "Content-Type: application/json" \
  -d '{
    "pmids": ["12345678", "87654321", "11223344"],
    "use_rag": true,
    "max_concurrent": 3
  }'
```

## Error Handling

All endpoints return standard HTTP status codes:
- `200`: Success
- `404`: Paper not found or analysis failed
- `500`: Server error

Error responses include a `detail` field with error information.

## Migration Guide

### From v1 to v2

1. Update endpoint URLs from `/api/v1/` to `/api/v2/`
2. Optionally add RAG configuration parameters
3. Handle new response fields (`rag_enabled`, `rag_stats`, `rag_config_used`)

### Minimal Changes Required

If you want to use v2 without RAG features, simply set `use_rag=false`:

```bash
# v1 (old)
GET /api/v1/analyze/12345678

# v2 equivalent (no RAG)
GET /api/v2/analyze/12345678?use_rag=false
```

The response format is compatible, with additional optional fields when RAG is enabled.

