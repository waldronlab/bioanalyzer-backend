"""
Accuracy benchmarks for RAG features.

Tests accuracy and quality of RAG components.
"""
import pytest
import asyncio
from unittest.mock import Mock, AsyncMock, patch
from pathlib import Path
import tempfile
import shutil

from app.services.advanced_rag import AdvancedRAGService
from app.services.contextual_summarization import ContextualSummarizationService, SummarizationConfig
from app.services.chunk_reranking import ChunkReRanker
from paperqa.types import Text


@pytest.fixture
def accuracy_test_chunks():
    """Create chunks with known relevance for accuracy testing."""
    return [
        Text(
            text="The host species in this study was clearly identified as Homo sapiens. All 100 participants were human adults.",
            name="highly_relevant"
        ),
        Text(
            text="This study examined the gut microbiome using 16S rRNA sequencing at the genus level.",
            name="moderately_relevant"
        ),
        Text(
            text="The weather was sunny during the study period. Participants enjoyed the research facilities.",
            name="low_relevance"
        ),
        Text(
            text="Samples were collected from the gastrointestinal tract, specifically the colon region of the digestive system.",
            name="highly_relevant_2"
        ),
        Text(
            text="The analysis focused on taxonomic classification and diversity metrics of microbial communities.",
            name="moderately_relevant_2"
        ),
    ]


@pytest.fixture
def mock_accurate_llm():
    """Create a mock LLM that returns accurate summaries."""
    mock = Mock()
    
    def chat_side_effect(messages, **kwargs):
        query = messages[0]["content"]
        if "host species" in query.lower():
            return {"text": "The host species is Homo sapiens (human). All participants were human adults."}
        elif "body site" in query.lower() or "gastrointestinal" in query.lower():
            return {"text": "Samples were collected from the gastrointestinal tract, specifically the colon."}
        else:
            return {"text": "This chunk contains information about the study methodology and analysis."}
    
    mock.chat = AsyncMock(side_effect=chat_side_effect)
    return mock


class TestRAGAccuracy:
    """Accuracy benchmarks for RAG components."""
    
    @pytest.mark.asyncio
    async def test_keyword_rerank_accuracy(self, accuracy_test_chunks):
        """Test that keyword re-ranking correctly identifies relevant chunks."""
        reranker = ChunkReRanker(rerank_method="keyword")
        query = "What is the host species?"
        
        ranked = await reranker.rerank_chunks(
            chunks=accuracy_test_chunks,
            query=query
        )
        
        # Chunk with "host species" should be ranked highest
        top_chunk = ranked[0]
        assert "host species" in top_chunk.chunk.text.lower() or \
               "homo sapiens" in top_chunk.chunk.text.lower()
        
        # Top chunk should have highest relevance score
        assert top_chunk.relevance_score >= ranked[-1].relevance_score
    
    @pytest.mark.asyncio
    async def test_llm_rerank_accuracy(self, accuracy_test_chunks, mock_accurate_llm):
        """Test that LLM re-ranking provides accurate relevance scores."""
        with patch('app.services.chunk_reranking.LLMProviderManager') as mock_manager:
            mock_manager.return_value = mock_accurate_llm
            
            reranker = ChunkReRanker(rerank_method="llm")
            reranker.llm_manager = mock_accurate_llm
            
            query = "What is the host species?"
            ranked = await reranker.rerank_chunks(
                chunks=accuracy_test_chunks,
                query=query
            )
            
            # Should rank chunks by relevance
            assert len(ranked) == len(accuracy_test_chunks)
            assert all(0.0 <= r.relevance_score <= 1.0 for r in ranked)
            
            # Top chunk should be most relevant
            top_score = ranked[0].relevance_score
            bottom_score = ranked[-1].relevance_score
            assert top_score >= bottom_score
    
    @pytest.mark.asyncio
    async def test_hybrid_rerank_accuracy(self, accuracy_test_chunks, mock_accurate_llm):
        """Test that hybrid re-ranking combines keyword and LLM accuracy."""
        with patch('app.services.chunk_reranking.LLMProviderManager') as mock_manager:
            mock_manager.return_value = mock_accurate_llm
            
            reranker = ChunkReRanker(rerank_method="hybrid")
            reranker.llm_manager = mock_accurate_llm
            
            query = "What is the host species?"
            ranked = await reranker.rerank_chunks(
                chunks=accuracy_test_chunks,
                query=query
            )
            
            # Should provide good ranking
            assert len(ranked) == len(accuracy_test_chunks)
            # Top chunk should be relevant
            top_text = ranked[0].chunk.text.lower()
            assert "host species" in top_text or "homo sapiens" in top_text
    
    @pytest.mark.asyncio
    async def test_summarization_accuracy(self, accuracy_test_chunks, mock_accurate_llm):
        """Test that summarization produces accurate summaries."""
        with patch('app.services.contextual_summarization.LLMProviderManager') as mock_manager:
            mock_manager.return_value = mock_accurate_llm
            
            temp_dir = tempfile.mkdtemp()
            try:
                service = ContextualSummarizationService(
                    cache_dir=temp_dir,
                    config=SummarizationConfig()
                )
                service.summary_llm = mock_accurate_llm
                
                query = "What is the host species?"
                # Test with highly relevant chunk
                relevant_chunk = accuracy_test_chunks[0]
                
                summary = await service.summarize_chunk(
                    chunk=relevant_chunk,
                    query=query
                )
                
                # Summary should contain relevant information
                assert "homo sapiens" in summary.summary.lower() or \
                       "human" in summary.summary.lower()
                assert summary.relevance_score > 0.0
            finally:
                shutil.rmtree(temp_dir, ignore_errors=True)
    
    @pytest.mark.asyncio
    async def test_rag_pipeline_accuracy(self, accuracy_test_chunks, mock_accurate_llm):
        """Test that complete RAG pipeline produces accurate context."""
        with patch('app.services.contextual_summarization.LLMProviderManager') as mock_summary, \
             patch('app.services.chunk_reranking.LLMProviderManager') as mock_rerank:
            mock_summary.return_value = mock_accurate_llm
            mock_rerank.return_value = mock_accurate_llm
            
            temp_dir = tempfile.mkdtemp()
            try:
                service = AdvancedRAGService(
                    rerank_method="hybrid",
                    cache_dir=temp_dir
                )
                service.summarization_service.summary_llm = mock_accurate_llm
                service.reranker.llm_manager = mock_accurate_llm
                
                query = "What is the host species?"
                context = await service.get_contextual_context(
                    chunks=accuracy_test_chunks,
                    query=query,
                    top_k=2
                )
                
                # Context should contain relevant information
                assert "homo sapiens" in context.lower() or "human" in context.lower()
                assert len(context) > 0
            finally:
                shutil.rmtree(temp_dir, ignore_errors=True)
    
    @pytest.mark.asyncio
    async def test_relevance_score_distribution(self, accuracy_test_chunks):
        """Test that relevance scores are properly distributed."""
        reranker = ChunkReRanker(rerank_method="keyword")
        query = "host species"
        
        ranked = await reranker.rerank_chunks(
            chunks=accuracy_test_chunks,
            query=query
        )
        
        scores = [r.relevance_score for r in ranked]
        
        # Should have variation in scores
        assert max(scores) > min(scores) or len(set(scores)) > 1
        # All scores should be in valid range
        assert all(0.0 <= s <= 1.0 for s in scores)
    
    @pytest.mark.asyncio
    async def test_summary_quality_levels(self, accuracy_test_chunks, mock_accurate_llm):
        """Test that different quality levels produce appropriate summaries."""
        with patch('app.services.contextual_summarization.LLMProviderManager') as mock_manager:
            mock_manager.return_value = mock_accurate_llm
            
            temp_dir = tempfile.mkdtemp()
            try:
                for quality in ["fast", "balanced", "high"]:
                    service = ContextualSummarizationService(
                        cache_dir=temp_dir,
                        config=SummarizationConfig(quality=quality)
                    )
                    service.summary_llm = mock_accurate_llm
                    
                    summary = await service.summarize_chunk(
                        chunk=accuracy_test_chunks[0],
                        query="What is the host species?"
                    )
                    
                    # All quality levels should produce summaries
                    assert len(summary.summary) > 0
                    assert summary.relevance_score > 0.0
            finally:
                shutil.rmtree(temp_dir, ignore_errors=True)

