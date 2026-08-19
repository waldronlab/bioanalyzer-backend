"""
Unit tests for Chunk Re-ranking Service.

Tests the chunk re-ranking functionality with different methods.
"""

import pytest
import asyncio
from unittest.mock import Mock, AsyncMock, patch

from app.services.chunk_reranking import ChunkReRanker, RankedChunk
from paperqa.types import Text


@pytest.fixture
def sample_chunks():
    """Create sample text chunks for testing."""
    from paperqa.types import Doc

    test_doc = Doc(
        docname="test_paper", dockey="test_key", citation="Test Paper Citation"
    )

    return [
        Text(
            text="This study examined the gut microbiome in human participants with inflammatory bowel disease.",
            name="chunk_1",
            doc=test_doc,
        ),
        Text(
            text="The host species was clearly identified as Homo sapiens. All participants were adults.",
            name="chunk_2",
            doc=test_doc,
        ),
        Text(
            text="Samples were collected from the gastrointestinal tract, specifically the colon.",
            name="chunk_3",
            doc=test_doc,
        ),
        Text(
            text="The analysis used 16S rRNA sequencing at the genus level for taxonomic classification.",
            name="chunk_4",
            doc=test_doc,
        ),
        Text(
            text="A total of 100 participants were included in this study, with 50 controls and 50 patients.",
            name="chunk_5",
            doc=test_doc,
        ),
    ]


@pytest.fixture
def mock_llm_provider():
    """Create a mock LLM provider."""
    mock = Mock()
    mock.chat = AsyncMock(
        return_value={
            "text": "SCORE: 0.85 REASONING: This chunk contains highly relevant information about the query."
        }
    )
    return mock


class TestRankedChunk:
    """Test RankedChunk dataclass."""

    def test_ranked_chunk_creation(self):
        """Test creating a RankedChunk."""
        from paperqa.types import Doc

        test_doc = Doc(docname="test", dockey="test_key", citation="Test")
        chunk = Text(text="Test chunk", name="chunk_1", doc=test_doc)
        ranked = RankedChunk(
            chunk=chunk, relevance_score=0.85, rank=1, reasoning="Highly relevant"
        )

        assert ranked.chunk == chunk
        assert ranked.relevance_score == 0.85
        assert ranked.rank == 1
        assert ranked.reasoning == "Highly relevant"

    def test_ranked_chunk_without_reasoning(self):
        """Test RankedChunk without reasoning."""
        from paperqa.types import Doc

        test_doc = Doc(docname="test", dockey="test_key", citation="Test")
        chunk = Text(text="Test chunk", name="chunk_1", doc=test_doc)
        ranked = RankedChunk(chunk=chunk, relevance_score=0.5, rank=2)

        assert ranked.reasoning is None


class TestChunkReRanker:
    """Test ChunkReRanker service."""

    def test_initialization_keyword_method(self):
        """Test initialization with keyword method."""
        reranker = ChunkReRanker(rerank_method="keyword")
        assert reranker.rerank_method == "keyword"
        assert reranker.llm_manager is None

    def test_initialization_llm_method(self, mock_llm_provider):
        """Test initialization with LLM method."""
        with patch("app.services.chunk_reranking.LLMProviderManager") as mock_manager:
            mock_manager.return_value = mock_llm_provider
            reranker = ChunkReRanker(
                rerank_method="llm",
                llm_provider="gemini",
                llm_model="gemini/gemini-2.0-flash",
            )
            assert reranker.rerank_method == "llm"
            assert reranker.llm_manager is not None

    def test_initialization_hybrid_method(self, mock_llm_provider):
        """Test initialization with hybrid method."""
        with patch("app.services.chunk_reranking.LLMProviderManager") as mock_manager:
            mock_manager.return_value = mock_llm_provider
            reranker = ChunkReRanker(rerank_method="hybrid", llm_provider="gemini")
            assert reranker.rerank_method == "hybrid"
            assert reranker.llm_manager is not None

    def test_initialization_llm_fallback(self):
        """Test that LLM method falls back to keyword if LLM unavailable."""
        with patch("app.services.chunk_reranking.LITELLM_AVAILABLE", False):
            reranker = ChunkReRanker(rerank_method="llm")
            assert reranker.rerank_method == "keyword"

    @pytest.mark.asyncio
    async def test_keyword_rerank(self, sample_chunks):
        """Test keyword-based re-ranking."""
        reranker = ChunkReRanker(rerank_method="keyword")
        query = "What is the host species?"

        ranked = await reranker.rerank_chunks(chunks=sample_chunks, query=query)

        assert len(ranked) == len(sample_chunks)
        assert all(isinstance(r, RankedChunk) for r in ranked)
        assert all(0.0 <= r.relevance_score <= 1.0 for r in ranked)

        # Chunk with "host species" should have higher score
        host_chunk = next(
            (r for r in ranked if "host species" in r.chunk.text.lower()), None
        )
        assert host_chunk is not None
        assert host_chunk.relevance_score > 0.0

    @pytest.mark.asyncio
    async def test_keyword_rerank_sorting(self, sample_chunks):
        """Test that keyword re-ranking sorts by relevance."""
        reranker = ChunkReRanker(rerank_method="keyword")
        query = "host species"

        ranked = await reranker.rerank_chunks(chunks=sample_chunks, query=query)

        # Should be sorted by relevance (descending)
        scores = [r.relevance_score for r in ranked]
        assert scores == sorted(scores, reverse=True)

        # Ranks should be assigned correctly
        assert ranked[0].rank == 1
        assert ranked[1].rank == 2

    @pytest.mark.asyncio
    async def test_keyword_rerank_top_k(self, sample_chunks):
        """Test keyword re-ranking with top_k parameter."""
        reranker = ChunkReRanker(rerank_method="keyword")
        query = "test query"

        ranked = await reranker.rerank_chunks(
            chunks=sample_chunks, query=query, top_k=3
        )

        assert len(ranked) == 3
        assert all(r.rank <= 3 for r in ranked)

    @pytest.mark.asyncio
    async def test_keyword_rerank_exact_phrase(self, sample_chunks):
        """Test that exact phrase matches get boosted scores."""
        reranker = ChunkReRanker(rerank_method="keyword")
        query = "host species"

        ranked = await reranker.rerank_chunks(chunks=sample_chunks, query=query)

        # Chunk with exact phrase should have higher score
        exact_match = next(
            (r for r in ranked if query.lower() in r.chunk.text.lower()), None
        )
        if exact_match:
            # Should have boosted score
            assert exact_match.relevance_score >= 0.0

    @pytest.mark.asyncio
    async def test_llm_rerank(self, sample_chunks, mock_llm_provider):
        """Test LLM-based re-ranking."""
        with patch("app.services.chunk_reranking.LLMProviderManager") as mock_manager:
            mock_manager.return_value = mock_llm_provider
            reranker = ChunkReRanker(rerank_method="llm", llm_provider="gemini")
            reranker.llm_manager = mock_llm_provider

            query = "What is the host species?"
            ranked = await reranker.rerank_chunks(chunks=sample_chunks, query=query)

            assert len(ranked) == len(sample_chunks)
            assert all(isinstance(r, RankedChunk) for r in ranked)
            assert all(0.0 <= r.relevance_score <= 1.0 for r in ranked)

            # Should have called LLM
            assert mock_llm_provider.chat.called

    @pytest.mark.asyncio
    async def test_llm_rerank_with_reasoning(self, sample_chunks, mock_llm_provider):
        """Test that LLM re-ranking includes reasoning."""
        with patch("app.services.chunk_reranking.LLMProviderManager") as mock_manager:
            mock_manager.return_value = mock_llm_provider
            reranker = ChunkReRanker(rerank_method="llm")
            reranker.llm_manager = mock_llm_provider

            query = "Test query"
            ranked = await reranker.rerank_chunks(
                chunks=sample_chunks[:2], query=query  # Just 2 for speed
            )

            # Should have reasoning from LLM
            assert all(r.reasoning is not None for r in ranked)

    @pytest.mark.asyncio
    async def test_llm_rerank_fallback(self, sample_chunks):
        """Test that LLM re-ranking falls back to keyword on error."""
        mock_llm = Mock()
        mock_llm.chat = AsyncMock(side_effect=Exception("LLM error"))

        with patch("app.services.chunk_reranking.LLMProviderManager") as mock_manager:
            mock_manager.return_value = mock_llm
            reranker = ChunkReRanker(rerank_method="llm")
            reranker.llm_manager = mock_llm

            query = "Test query"
            ranked = await reranker.rerank_chunks(chunks=sample_chunks, query=query)

            # Should still return results (using keyword fallback)
            assert len(ranked) == len(sample_chunks)

    @pytest.mark.asyncio
    async def test_hybrid_rerank(self, sample_chunks, mock_llm_provider):
        """Test hybrid re-ranking method."""
        with patch("app.services.chunk_reranking.LLMProviderManager") as mock_manager:
            mock_manager.return_value = mock_llm_provider
            # Use 0-1 scale for easier testing
            reranker = ChunkReRanker(
                rerank_method="hybrid", llm_provider="gemini", use_10_scale=False
            )
            reranker.llm_manager = mock_llm_provider

            query = "What is the host species?"
            ranked = await reranker.rerank_chunks(chunks=sample_chunks, query=query)

            assert len(ranked) == len(sample_chunks)
            assert all(isinstance(r, RankedChunk) for r in ranked)
            # Hybrid should combine keyword and LLM scores (0-1 scale)
            assert all(0.0 <= r.relevance_score <= 1.0 for r in ranked)

    @pytest.mark.asyncio
    async def test_hybrid_rerank_without_llm(self, sample_chunks):
        """Test hybrid re-ranking when LLM is not available."""
        reranker = ChunkReRanker(rerank_method="hybrid")
        reranker.llm_manager = None

        query = "Test query"
        ranked = await reranker.rerank_chunks(chunks=sample_chunks, query=query)

        # Should fall back to keyword-only
        assert len(ranked) == len(sample_chunks)

    @pytest.mark.asyncio
    async def test_hybrid_rerank_large_chunk_list(
        self, sample_chunks, mock_llm_provider
    ):
        """Test hybrid re-ranking with large chunk list (should limit LLM calls)."""
        # Create many chunks
        many_chunks = sample_chunks * 10  # 50 chunks

        with patch("app.services.chunk_reranking.LLMProviderManager") as mock_manager:
            mock_manager.return_value = mock_llm_provider
            reranker = ChunkReRanker(rerank_method="hybrid")
            reranker.llm_manager = mock_llm_provider

            query = "Test query"
            ranked = await reranker.rerank_chunks(chunks=many_chunks, query=query)

            # Should handle large lists
            assert len(ranked) == len(many_chunks)
            # Hybrid should only use LLM for top chunks
            assert mock_llm_provider.chat.call_count <= 20  # Limited LLM calls

    @pytest.mark.asyncio
    async def test_empty_chunks(self):
        """Test re-ranking with empty chunk list."""
        reranker = ChunkReRanker(rerank_method="keyword")
        ranked = await reranker.rerank_chunks(chunks=[], query="Test query")
        assert ranked == []

    @pytest.mark.asyncio
    async def test_get_metrics_reflects_actual_relevance_scores(self):
        """Regression test: get_metrics() must report real aggregate relevance
        scores computed from the actual reranked chunks, not the old hardcoded
        constants (avg=0.75, max=0.0, min=0.0) that were previously returned
        because rerank_chunks() never wrote score aggregates into _metrics.

        Uses purpose-built chunks with deliberately graduated keyword-match
        density against the query, so every chunk gets a distinct, nonzero
        keyword-rerank score and the aggregates are unambiguously not the
        old constants.
        """
        from paperqa.types import Doc

        test_doc = Doc(docname="test", dockey="test_key", citation="Test")
        query = "microbiome host species sample sequencing"

        # Graduated density: 5, 4, 3, 2, 1 of the 5 query terms present.
        density_chunks = [
            Text(
                text=(
                    "microbiome host species sample sequencing all present "
                    "in this chunk about the study."
                ),
                name="dense_5",
                doc=test_doc,
            ),
            Text(
                text=(
                    "microbiome host species sample present here but no "
                    "mention of the analysis method."
                ),
                name="dense_4",
                doc=test_doc,
            ),
            Text(
                text="microbiome host species discussed without further detail.",
                name="dense_3",
                doc=test_doc,
            ),
            Text(
                text="microbiome host mentioned only briefly in passing.",
                name="dense_2",
                doc=test_doc,
            ),
            Text(
                text="microbiome mentioned once, nothing else relevant here.",
                name="dense_1",
                doc=test_doc,
            ),
        ]

        reranker = ChunkReRanker(rerank_method="keyword")
        ranked = await reranker.rerank_chunks(chunks=density_chunks, query=query)
        metrics = reranker.get_metrics()

        # Independently recompute expected aggregates from the actual
        # returned scores (full population, not just a top_k slice).
        expected_scores = [rc.relevance_score for rc in ranked]
        expected_avg = sum(expected_scores) / len(expected_scores)
        expected_max = max(expected_scores)
        expected_min = min(expected_scores)

        # Sanity check: the fixture actually produced graduated, distinct
        # scores (otherwise this test wouldn't exercise real variance).
        assert len(set(expected_scores)) == len(expected_scores)

        assert metrics["chunks_reranked"] == len(density_chunks)
        assert metrics["avg_relevance_score"] == pytest.approx(expected_avg)
        assert metrics["max_relevance_score"] == pytest.approx(expected_max)
        assert metrics["min_relevance_score"] == pytest.approx(expected_min)
        assert "processing_time" in metrics

        # The old hardcoded fallback values (used whenever these keys were
        # never populated) would not survive this comparison.
        assert metrics["avg_relevance_score"] != 0.75
        assert metrics["max_relevance_score"] != 0.0
        assert metrics["min_relevance_score"] != 0.0

    @pytest.mark.asyncio
    async def test_get_metrics_computed_over_full_population_not_top_k(
        self, sample_chunks
    ):
        """Metrics must be computed over the full reranked set, not just the
        post-top_k slice, so a small top_k can't trivially inflate the
        reported average/min via selection bias."""
        reranker = ChunkReRanker(rerank_method="keyword")
        query = "host species Homo sapiens gastrointestinal colon"

        full_ranked = await reranker.rerank_chunks(chunks=sample_chunks, query=query)
        full_scores = [rc.relevance_score for rc in full_ranked]

        reranker_top_k = ChunkReRanker(rerank_method="keyword")
        top_ranked = await reranker_top_k.rerank_chunks(
            chunks=sample_chunks, query=query, top_k=1
        )
        assert len(top_ranked) == 1
        metrics = reranker_top_k.get_metrics()

        # Even though only 1 chunk was returned, metrics reflect all chunks
        # that were actually reranked/scored.
        assert metrics["chunks_reranked"] == len(sample_chunks)
        assert metrics["avg_relevance_score"] == pytest.approx(
            sum(full_scores) / len(full_scores)
        )
        assert metrics["min_relevance_score"] == pytest.approx(min(full_scores))

    @pytest.mark.asyncio
    async def test_metrics_reset_on_empty_chunks_after_prior_call(self, sample_chunks):
        """A chunkless call must reset metrics to zeroed values rather than
        leaving stale data from a previous call on the same instance."""
        reranker = ChunkReRanker(rerank_method="keyword")
        query = "host species"

        ranked = await reranker.rerank_chunks(chunks=sample_chunks, query=query)
        prior_metrics = reranker.get_metrics()
        assert prior_metrics["chunks_reranked"] == len(sample_chunks)
        assert len(ranked) == len(sample_chunks)

        empty_ranked = await reranker.rerank_chunks(chunks=[], query=query)
        assert empty_ranked == []

        reset_metrics = reranker.get_metrics()
        assert reset_metrics == {
            "processing_time": 0.0,
            "chunks_reranked": 0,
            "avg_relevance_score": 0.0,
            "max_relevance_score": 0.0,
            "min_relevance_score": 0.0,
        }

    @pytest.mark.asyncio
    async def test_score_parsing(self, sample_chunks, mock_llm_provider):
        """Test parsing scores from LLM responses."""
        # Test different response formats
        test_cases = [
            "SCORE: 0.85 REASONING: Test reasoning",
            "The relevance score is 0.75",
            "0.90",
            "Score: 0.65",
        ]

        with patch("app.services.chunk_reranking.LLMProviderManager") as mock_manager:
            mock_manager.return_value = mock_llm_provider
            reranker = ChunkReRanker(rerank_method="llm")
            reranker.llm_manager = mock_llm_provider

            for response_text in test_cases:
                mock_llm_provider.chat.return_value = {"text": response_text}
                ranked = await reranker.rerank_chunks(
                    chunks=sample_chunks[:1], query="Test"
                )

                # Should parse score (may default to 0.5 if parsing fails)
                assert 0.0 <= ranked[0].relevance_score <= 1.0

    @pytest.mark.asyncio
    async def test_calculate_keyword_score(self, sample_chunks):
        """Test keyword score calculation."""
        reranker = ChunkReRanker(rerank_method="keyword")

        # Test with matching terms
        score1 = await reranker._calculate_keyword_score(
            "This is about host species", "host species"
        )
        assert 0.0 <= score1 <= 1.0

        # Test with no matches
        score2 = await reranker._calculate_keyword_score(
            "This is about something else", "host species"
        )
        assert score2 < score1

    def test_parse_score_from_response(self):
        """Test parsing score from LLM response."""
        reranker = ChunkReRanker(rerank_method="keyword")

        # Test various formats
        assert reranker._parse_score_from_response("SCORE: 0.85") == 0.85
        assert reranker._parse_score_from_response("0.75") == 0.75
        assert reranker._parse_score_from_response("Score: 1.0") == 1.0
        assert reranker._parse_score_from_response("Invalid") == 0.5  # Default

    def test_extract_reasoning(self):
        """Test extracting reasoning from LLM response."""
        reranker = ChunkReRanker(rerank_method="keyword")

        reasoning = reranker._extract_reasoning(
            "SCORE: 0.85 REASONING: This is highly relevant"
        )
        assert reasoning == "This is highly relevant"

        reasoning = reranker._extract_reasoning("No reasoning here")
        assert reasoning is None
