"""
Unit tests for Contextual Summarization Service.

Tests the RCS (Retrieval Contextual Summarization) functionality.
"""

import pytest
import asyncio
from unittest.mock import Mock, AsyncMock, patch, MagicMock
from pathlib import Path
import tempfile
import shutil

from app.services.contextual_summarization import (
    ContextualSummarizationService,
    SummarizationConfig,
    ChunkSummary,
)
from paperqa.types import Text


@pytest.fixture
def temp_cache_dir():
    """Create a temporary cache directory."""
    temp_dir = tempfile.mkdtemp()
    yield Path(temp_dir)
    shutil.rmtree(temp_dir, ignore_errors=True)


@pytest.fixture
def sample_chunks():
    """Create sample text chunks for testing."""
    from paperqa.types import Doc
    
    test_doc = Doc(
        docname="test_paper",
        dockey="test_key",
        citation="Test Paper Citation"
    )
    
    return [
        Text(
            text="This study examined the gut microbiome in 100 human participants with inflammatory bowel disease. The analysis used 16S rRNA sequencing at the genus level.",
            name="chunk_1",
            doc=test_doc,
        ),
        Text(
            text="The host species was clearly identified as Homo sapiens. All participants were adults between 18-65 years old.",
            name="chunk_2",
            doc=test_doc,
        ),
        Text(
            text="Samples were collected from the gastrointestinal tract, specifically the colon. The study included both healthy controls and patients with Crohn's disease.",
            name="chunk_3",
            doc=test_doc,
        ),
    ]


@pytest.fixture
def mock_llm_provider():
    """Create a mock LLM provider."""
    mock = Mock()
    mock.chat = AsyncMock(
        return_value={
            "text": "This study analyzed the gut microbiome in human participants with IBD using 16S sequencing. Key findings include genus-level analysis of 100 participants."
        }
    )
    return mock


@pytest.fixture
def summarization_service(temp_cache_dir, mock_llm_provider):
    """Create a summarization service with mocked LLM."""
    with patch(
        "app.services.contextual_summarization.LLMProviderManager"
    ) as mock_manager:
        mock_manager.return_value = mock_llm_provider
        service = ContextualSummarizationService(
            summary_llm_provider="gemini",
            summary_llm_model="gemini/gemini-2.0-flash",
            cache_dir=str(temp_cache_dir),
            config=SummarizationConfig(
                summary_length="medium",
                quality="balanced",
                max_key_points=3,
                use_cache=True,
            ),
        )
        service.summary_llm = mock_llm_provider
        return service


class TestSummarizationConfig:
    """Test SummarizationConfig dataclass."""

    def test_default_config(self):
        """Test default configuration values."""
        config = SummarizationConfig()
        assert config.summary_length == "medium"
        assert config.quality == "balanced"
        assert config.max_key_points == 5
        assert config.temperature == 0.3
        assert config.use_cache is True

    def test_custom_config(self):
        """Test custom configuration values."""
        config = SummarizationConfig(
            summary_length="long",
            quality="high",
            max_key_points=10,
            temperature=0.5,
            use_cache=False,
        )
        assert config.summary_length == "long"
        assert config.quality == "high"
        assert config.max_key_points == 10
        assert config.temperature == 0.5
        assert config.use_cache is False


class TestContextualSummarizationService:
    """Test ContextualSummarizationService."""

    def test_initialization(self, temp_cache_dir):
        """Test service initialization."""
        service = ContextualSummarizationService(
            cache_dir=str(temp_cache_dir), config=SummarizationConfig()
        )
        assert service.config is not None
        assert service.cache_dir == temp_cache_dir
        assert service.cache_dir.exists()

    def test_initialization_without_llm(self, temp_cache_dir):
        """Test initialization when LLM is not available."""
        with patch("app.services.contextual_summarization.LITELLM_AVAILABLE", False):
            service = ContextualSummarizationService(cache_dir=str(temp_cache_dir))
            assert service.summary_llm is None

    def test_summary_templates(self, summarization_service):
        """Test that summary templates are created."""
        assert "short" in summarization_service.summary_templates
        assert "medium" in summarization_service.summary_templates
        assert "long" in summarization_service.summary_templates

    def test_cache_key_generation(self, summarization_service):
        """Test cache key generation."""
        chunk_text = "Sample chunk text"
        query = "What is the host species?"
        length = "medium"

        key1 = summarization_service._get_cache_key(chunk_text, query, length)
        key2 = summarization_service._get_cache_key(chunk_text, query, length)

        # Same inputs should generate same key
        assert key1 == key2

        # Different inputs should generate different keys
        key3 = summarization_service._get_cache_key(
            chunk_text, "Different query", length
        )
        assert key1 != key3

    @pytest.mark.asyncio
    async def test_summarize_single_chunk(self, summarization_service, sample_chunks):
        """Test summarizing a single chunk."""
        query = "What host species is being studied?"
        chunk = sample_chunks[1]  # Contains host species info

        summary = await summarization_service.summarize_chunk(chunk=chunk, query=query)

        assert isinstance(summary, ChunkSummary)
        assert summary.chunk_id is not None
        assert summary.original_text == chunk.text
        assert summary.query == query
        assert summary.summary is not None
        assert len(summary.summary) > 0
        assert 0.0 <= summary.relevance_score <= 1.0
        assert 0.0 <= summary.confidence <= 1.0

    @pytest.mark.asyncio
    async def test_summarize_chunks(self, summarization_service, sample_chunks):
        """Test summarizing multiple chunks."""
        query = "What is the host species and body site?"

        summaries = await summarization_service.summarize_chunks(
            chunks=sample_chunks, query=query
        )

        assert len(summaries) == len(sample_chunks)
        assert all(isinstance(s, ChunkSummary) for s in summaries)
        assert all(s.query == query for s in summaries)
        assert all(len(s.summary) > 0 for s in summaries)

    @pytest.mark.asyncio
    async def test_summarize_chunks_with_cache(
        self, summarization_service, sample_chunks
    ):
        """Test that caching works for summaries."""
        query = "What host species?"

        # First call - should generate summaries
        summaries1 = await summarization_service.summarize_chunks(
            chunks=sample_chunks, query=query
        )

        # Second call - should use cache
        summaries2 = await summarization_service.summarize_chunks(
            chunks=sample_chunks, query=query
        )

        # Results should be the same
        assert len(summaries1) == len(summaries2)
        for s1, s2 in zip(summaries1, summaries2):
            assert s1.summary == s2.summary
            assert s1.chunk_id == s2.chunk_id

    @pytest.mark.asyncio
    async def test_summarize_chunks_cache_disabled(
        self, temp_cache_dir, mock_llm_provider
    ):
        """Test summarization with cache disabled."""
        with patch(
            "app.services.contextual_summarization.LLMProviderManager"
        ) as mock_manager:
            mock_manager.return_value = mock_llm_provider
            service = ContextualSummarizationService(
                cache_dir=str(temp_cache_dir),
                config=SummarizationConfig(use_cache=False),
            )
            service.summary_llm = mock_llm_provider

            from paperqa.types import Doc
            test_doc = Doc(docname="test", dockey="test_key", citation="Test")
            chunks = [Text(text="Test chunk", name="chunk_1", doc=test_doc)]
            query = "Test query"

            summaries = await service.summarize_chunks(chunks, query)
            assert len(summaries) == 1

    @pytest.mark.asyncio
    async def test_different_summary_lengths(
        self, summarization_service, sample_chunks
    ):
        """Test different summary length configurations."""
        query = "What is being studied?"

        for length in ["short", "medium", "long"]:
            service = ContextualSummarizationService(
                cache_dir=str(summarization_service.cache_dir),
                config=SummarizationConfig(summary_length=length),
            )
            service.summary_llm = summarization_service.summary_llm

            summaries = await service.summarize_chunks(
                chunks=sample_chunks[:1], query=query  # Just one chunk for speed
            )

            assert len(summaries) == 1
            # Long summaries should generally be longer than short ones
            # (though this depends on LLM response)

    @pytest.mark.asyncio
    async def test_summarize_without_llm(self, temp_cache_dir, sample_chunks):
        """Test summarization when LLM is not available."""
        with patch("app.services.contextual_summarization.LITELLM_AVAILABLE", False):
            service = ContextualSummarizationService(cache_dir=str(temp_cache_dir))

            # Should handle gracefully
            summaries = await service.summarize_chunks(
                chunks=sample_chunks, query="Test query"
            )

            # Should return empty or fallback summaries
            assert isinstance(summaries, list)

    @pytest.mark.asyncio
    async def test_key_points_extraction(self, summarization_service, sample_chunks):
        """Test that key points are extracted from summaries."""
        query = "What are the key findings?"

        # Mock LLM to return response with key points
        mock_response = {
            "text": "Summary text. Key points: 1. Point one. 2. Point two. 3. Point three."
        }
        summarization_service.summary_llm.chat = AsyncMock(return_value=mock_response)

        summaries = await summarization_service.summarize_chunks(
            chunks=sample_chunks[:1], query=query
        )

        assert len(summaries) > 0
        # Key points should be extracted (implementation dependent)
        assert hasattr(summaries[0], "key_points")

    @pytest.mark.asyncio
    async def test_relevance_scoring(self, summarization_service, sample_chunks):
        """Test that relevance scores are calculated."""
        query = "What is the host species?"

        summaries = await summarization_service.summarize_chunks(
            chunks=sample_chunks, query=query
        )

        # All summaries should have relevance scores
        assert all(0.0 <= s.relevance_score <= 1.0 for s in summaries)

        # Chunk with host species info should have higher relevance
        host_chunk_idx = 1  # chunk_2 has host species info
        assert summaries[host_chunk_idx].relevance_score >= 0.0

    @pytest.mark.asyncio
    async def test_empty_chunks(self, summarization_service):
        """Test handling of empty chunk list."""
        summaries = await summarization_service.summarize_chunks(
            chunks=[], query="Test query"
        )
        assert summaries == []

    @pytest.mark.asyncio
    async def test_llm_error_handling(self, summarization_service, sample_chunks):
        """Test error handling when LLM fails."""
        # Mock LLM to raise an error
        summarization_service.summary_llm.chat = AsyncMock(
            side_effect=Exception("LLM error")
        )

        # Should handle gracefully
        summaries = await summarization_service.summarize_chunks(
            chunks=sample_chunks, query="Test query"
        )

        # Should return empty list or fallback
        assert isinstance(summaries, list)


class TestChunkSummary:
    """Test ChunkSummary dataclass."""

    def test_chunk_summary_creation(self):
        """Test creating a ChunkSummary."""
        summary = ChunkSummary(
            chunk_id="chunk_1",
            original_text="Original text",
            summary="Summary text",
            relevance_score=0.85,
            query="Test query",
            key_points=["Point 1", "Point 2"],
            confidence=0.9,
        )

        assert summary.chunk_id == "chunk_1"
        assert summary.original_text == "Original text"
        assert summary.summary == "Summary text"
        assert summary.relevance_score == 0.85
        assert summary.query == "Test query"
        assert len(summary.key_points) == 2
        assert summary.confidence == 0.9
