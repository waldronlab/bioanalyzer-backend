# Advanced RAG with Contextual Summarization

## Overview

BioAnalyzer now implements **Advanced RAG (Retrieval-Augmented Generation) with Contextual Summarization (RCS)** to improve field extraction accuracy. This feature creates query-aware summaries of evidence chunks, re-ranks them by relevance, and uses them for more accurate field extraction.

## Features

1. **Contextual Summarization (RCS)**: Creates query-aware summaries of text chunks
2. **Chunk Re-ranking**: Re-ranks chunks by relevance to the extraction query
3. **Relevance Scoring**: Scores chunks based on their relevance to specific fields
4. **Summary Caching**: Caches summaries for reuse to improve performance
5. **Separate Summary LLM**: Uses a separate (potentially cheaper/faster) LLM for summarization
6. **Configurable Quality**: Adjust summary length and quality based on needs

## Architecture

```
Field Extraction Query
    ↓
Text Chunks (from paper)
    ↓
Chunk Re-ranker (keyword/LLM/hybrid)
    ↓
Top-K Relevant Chunks
    ↓
Contextual Summarization Service
    ↓
Query-Aware Summaries
    ↓
Combined Context for Field Extraction
    ↓
Improved Field Extraction Accuracy
```

## Configuration

### Environment Variables

```bash
# Summary LLM Configuration (optional - uses main LLM if not set)
export RAG_SUMMARY_PROVIDER=gemini  # Provider for summarization
export RAG_SUMMARY_MODEL=gemini/gemini-1.5-flash  # Model for summarization (can be cheaper)

# Summary Quality Settings
export RAG_SUMMARY_LENGTH=medium  # "short", "medium", "long"
export RAG_SUMMARY_QUALITY=balanced  # "fast", "balanced", "high"
export RAG_MAX_SUMMARY_KEY_POINTS=5  # Max key points per summary

# Re-ranking Configuration
export RAG_RERANK_METHOD=hybrid  # "keyword", "llm", "hybrid"

# Performance Settings
export RAG_USE_SUMMARY_CACHE=true  # Enable summary caching
export RAG_TOP_K_CHUNKS=10  # Number of top chunks to use after re-ranking
```

### Summary Length Options

- **short**: 2-3 sentences, fast, good for simple queries
- **medium**: 3-5 sentences, balanced, recommended for most use cases
- **long**: 5-7 sentences, comprehensive, best for complex queries

### Re-ranking Methods

- **keyword**: Fast keyword-based scoring, no LLM needed
- **llm**: LLM-based relevance scoring, more accurate but slower
- **hybrid**: Combines keyword and LLM (recommended)

## Usage

### Automatic Integration

The advanced RAG is automatically integrated into the field extraction pipeline. When analyzing papers:

1. If full text is available (>1000 chars), chunks are automatically created
2. For each field extraction query, chunks are re-ranked and summarized
3. Contextual summaries are used instead of raw text chunks

### Manual Usage

```python
from app.services.advanced_rag import AdvancedRAGService
from app.utils.chunking import ChunkingService

# Create chunks
chunker = ChunkingService(chunk_chars=3000, overlap=100)
chunks = await chunker.chunk_markdown(markdown=full_text, doc_name="paper")

# Initialize RAG service
rag_service = AdvancedRAGService()

# Get contextual context for a query
query = "What is the host species?"
context = await rag_service.get_contextual_context(
    chunks=chunks,
    query=query,
    top_k=10
)

# Use context for field extraction
# ... (pass to LLM for extraction)
```

### Contextual Summarization Service

```python
from app.services.contextual_summarization import (
    ContextualSummarizationService,
    SummarizationConfig
)

# Configure summarization
config = SummarizationConfig(
    summary_length="medium",
    quality="balanced",
    max_key_points=5,
    use_cache=True
)

# Initialize service
summarizer = ContextualSummarizationService(
    summary_llm_provider="gemini",
    summary_llm_model="gemini/gemini-1.5-flash",
    config=config
)

# Summarize chunks
summaries = await summarizer.summarize_chunks(
    chunks=chunks,
    query="What is the host species?"
)

for summary in summaries:
    print(f"Relevance: {summary.relevance_score:.2f}")
    print(f"Summary: {summary.summary}")
    print(f"Key points: {summary.key_points}")
```

### Chunk Re-ranking Service

```python
from app.services.chunk_reranking import ChunkReRanker

# Initialize re-ranker
reranker = ChunkReRanker(
    rerank_method="hybrid",  # or "keyword", "llm"
    llm_provider="gemini",
    llm_model="gemini/gemini-1.5-flash"
)

# Re-rank chunks
ranked_chunks = await reranker.rerank_chunks(
    chunks=chunks,
    query="What is the host species?",
    top_k=10
)

for ranked in ranked_chunks:
    print(f"Rank {ranked.rank}: Relevance {ranked.relevance_score:.2f}")
    if ranked.reasoning:
        print(f"Reasoning: {ranked.reasoning}")
```

## Benefits

1. **Improved Accuracy**: Query-aware summaries provide better context for field extraction
2. **Better Relevance**: Re-ranking ensures most relevant chunks are used
3. **Performance**: Summary caching reduces redundant LLM calls
4. **Flexibility**: Can use cheaper/faster models for summarization
5. **Scalability**: Handles large documents efficiently

## Performance Considerations

### Summary Caching

Summaries are cached by default to avoid redundant generation:
- Cache key: MD5 hash of (chunk_text + query + summary_length)
- Cache location: `cache/summaries/` directory
- Cache format: JSON files

### Batch Processing

Summaries are generated in batches (default: 5 at a time) to avoid overwhelming the LLM API.

### Fallback Behavior

- If summarization fails, falls back to keyword-based extraction
- If re-ranking fails, uses original chunk order
- If chunks unavailable, uses simple text extraction

## Integration with Field Extraction

The advanced RAG is integrated into `analyze_single_field()` in `bugsigdb_analyzer.py`:

```python
async def analyze_single_field(
    text: str,
    field_name: str,
    question: str,
    pmid: str,
    chunks: Optional[List] = None  # Chunks for advanced RAG
) -> Dict:
    # If chunks provided, use advanced RAG
    if chunks:
        rag_service = AdvancedRAGService()
        contextual_context = await rag_service.get_contextual_context(
            chunks=chunks,
            query=question
        )
        # Use contextual_context instead of raw text
    # ... rest of extraction logic
```

## Monitoring and Statistics

Get statistics about summaries:

```python
from app.services.advanced_rag import AdvancedRAGService

rag_service = AdvancedRAGService()
summaries, ranked_chunks = await rag_service.retrieve_and_summarize(
    chunks=chunks,
    query="What is the host species?"
)

stats = rag_service.get_summary_stats(summaries)
print(f"Average relevance: {stats['avg_relevance']:.2f}")
print(f"Average confidence: {stats['avg_confidence']:.2f}")
print(f"Total key points: {stats['total_key_points']}")
```

## Troubleshooting

### Summaries Not Being Generated

1. Check that chunks are being created (full text > 1000 chars)
2. Verify summary LLM is configured correctly
3. Check logs for summarization errors

### Low Relevance Scores

1. Try different re-ranking methods (hybrid recommended)
2. Adjust `RAG_TOP_K_CHUNKS` to use more chunks
3. Check that queries are specific enough

### Performance Issues

1. Reduce `RAG_TOP_K_CHUNKS` to process fewer chunks
2. Use "keyword" re-ranking method for faster processing
3. Use "short" summary length for faster generation
4. Ensure summary caching is enabled

## See Also

- [LiteLLM Integration Guide](./LITELLM_INTEGRATION.md)
- [Field Extraction Documentation](../app/services/bugsigdb_analyzer.py)
- [Chunking Service](../app/utils/chunking.py)

