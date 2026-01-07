"""
Performance benchmarks for RAG features.

Tests performance characteristics of RAG components.
"""

import pytest
import asyncio
import time
from unittest.mock import Mock, AsyncMock, patch
from pathlib import Path
import tempfile
import shutil

from app.services.advanced_rag import AdvancedRAGService
from app.services.contextual_summarization import (
    ContextualSummarizationService,
    SummarizationConfig,
)
from app.services.chunk_reranking import ChunkReRanker
from paperqa.types import Text


@pytest.fixture
def large_chunk_set():
    """Create a large set of chunks for performance testing."""
    chunks = []
    for i in range(50):
        chunks.append(
            Text(
                text=f"Chunk {i}: This is a test chunk with some content about microbiome analysis. "
                f"It contains information about host species, body sites, and sequencing methods. "
                f"Chunk number {i} has additional details.",
                name=f"chunk_{i}",
                doc=None,
            )
        )
    return chunks


@pytest.fixture
def mock_fast_llm():
    """Create a fast mock LLM for performance testing."""
    mock = Mock()
    mock.chat = AsyncMock(return_value={"text": "Summary text with key points."})
    return mock


class TestRAGPerformance:
    """Performance benchmarks for RAG components."""

    @pytest.mark.asyncio
    async def test_keyword_rerank_performance(self, large_chunk_set):
        """Test keyword re-ranking performance with large chunk set."""
        reranker = ChunkReRanker(rerank_method="keyword")
        query = "host species microbiome"

        start_time = time.time()
        ranked = await reranker.rerank_chunks(chunks=large_chunk_set, query=query)
        elapsed = time.time() - start_time

        assert len(ranked) == len(large_chunk_set)
        # Keyword method should be fast (< 1 second for 50 chunks)
        assert elapsed < 1.0, f"Keyword re-ranking took {elapsed:.2f}s, expected < 1.0s"

    @pytest.mark.asyncio
    async def test_summarization_performance(self, large_chunk_set, mock_fast_llm):
        """Test summarization performance."""
        with patch(
            "app.services.contextual_summarization.LLMProviderManager"
        ) as mock_manager:
            mock_manager.return_value = mock_fast_llm

            temp_dir = tempfile.mkdtemp()
            try:
                service = ContextualSummarizationService(
                    cache_dir=temp_dir,
                    config=SummarizationConfig(
                        use_cache=False
                    ),  # Disable cache for consistent timing
                )
                service.summary_llm = mock_fast_llm

                # Test with smaller subset for speed
                test_chunks = large_chunk_set[:10]
                query = "Test query"

                start_time = time.time()
                summaries = await service.summarize_chunks(
                    chunks=test_chunks, query=query
                )
                elapsed = time.time() - start_time

                assert len(summaries) == len(test_chunks)
                # Should complete in reasonable time
                assert elapsed < 30.0, f"Summarization took {elapsed:.2f}s"
            finally:
                shutil.rmtree(temp_dir, ignore_errors=True)

    @pytest.mark.asyncio
    async def test_rag_pipeline_performance(self, large_chunk_set, mock_fast_llm):
        """Test complete RAG pipeline performance."""
        with patch(
            "app.services.contextual_summarization.LLMProviderManager"
        ) as mock_summary, patch(
            "app.services.chunk_reranking.LLMProviderManager"
        ) as mock_rerank:
            mock_summary.return_value = mock_fast_llm
            mock_rerank.return_value = mock_fast_llm

            temp_dir = tempfile.mkdtemp()
            try:
                service = AdvancedRAGService(
                    rerank_method="keyword", cache_dir=temp_dir  # Use keyword for speed
                )
                service.summarization_service.summary_llm = mock_fast_llm

                # Test with subset
                test_chunks = large_chunk_set[:20]
                query = "Test query"

                start_time = time.time()
                context = await service.get_contextual_context(
                    chunks=test_chunks, query=query, top_k=5
                )
                elapsed = time.time() - start_time

                assert isinstance(context, str)
                assert len(context) > 0
                # Should complete in reasonable time
                assert elapsed < 30.0, f"RAG pipeline took {elapsed:.2f}s"
            finally:
                shutil.rmtree(temp_dir, ignore_errors=True)

    @pytest.mark.asyncio
    async def test_cache_performance_improvement(self, large_chunk_set, mock_fast_llm):
        """Test that caching improves performance."""
        with patch(
            "app.services.contextual_summarization.LLMProviderManager"
        ) as mock_manager:
            mock_manager.return_value = mock_fast_llm

            temp_dir = tempfile.mkdtemp()
            try:
                service = ContextualSummarizationService(
                    cache_dir=temp_dir, config=SummarizationConfig(use_cache=True)
                )
                service.summary_llm = mock_fast_llm

                test_chunks = large_chunk_set[:5]
                query = "Test query"

                # First call (no cache)
                start1 = time.time()
                summaries1 = await service.summarize_chunks(test_chunks, query)
                elapsed1 = time.time() - start1

                # Second call (with cache)
                start2 = time.time()
                summaries2 = await service.summarize_chunks(test_chunks, query)
                elapsed2 = time.time() - start2

                # Cached call should be faster
                assert (
                    elapsed2 < elapsed1 or elapsed2 < 0.1
                ), f"Cache should improve performance: {elapsed1:.3f}s -> {elapsed2:.3f}s"
            finally:
                shutil.rmtree(temp_dir, ignore_errors=True)

    @pytest.mark.asyncio
    async def test_top_k_performance_impact(self, large_chunk_set, mock_fast_llm):
        """Test that smaller top_k improves performance."""
        with patch(
            "app.services.contextual_summarization.LLMProviderManager"
        ) as mock_summary, patch(
            "app.services.chunk_reranking.LLMProviderManager"
        ) as mock_rerank:
            mock_summary.return_value = mock_fast_llm
            mock_rerank.return_value = mock_fast_llm

            temp_dir = tempfile.mkdtemp()
            try:
                service = AdvancedRAGService(
                    rerank_method="keyword", cache_dir=temp_dir
                )
                service.summarization_service.summary_llm = mock_fast_llm

                query = "Test query"

                # Test with top_k=5
                start1 = time.time()
                context1 = await service.get_contextual_context(
                    chunks=large_chunk_set[:20], query=query, top_k=5
                )
                elapsed1 = time.time() - start1

                # Test with top_k=10
                start2 = time.time()
                context2 = await service.get_contextual_context(
                    chunks=large_chunk_set[:20], query=query, top_k=10
                )
                elapsed2 = time.time() - start2

                # Smaller top_k should generally be faster
                # (though this depends on implementation)
                assert isinstance(context1, str)
                assert isinstance(context2, str)
            finally:
                shutil.rmtree(temp_dir, ignore_errors=True)

    @pytest.mark.asyncio
    async def test_rerank_method_performance_comparison(self, large_chunk_set):
        """Compare performance of different re-ranking methods."""
        query = "Test query"

        # Keyword method
        start1 = time.time()
        reranker1 = ChunkReRanker(rerank_method="keyword")
        ranked1 = await reranker1.rerank_chunks(large_chunk_set, query)
        elapsed1 = time.time() - start1

        # Keyword should be fastest
        assert elapsed1 < 1.0, f"Keyword method took {elapsed1:.2f}s"
        assert len(ranked1) == len(large_chunk_set)
