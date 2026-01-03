"""
Integration tests for Advanced RAG Service.

Tests the complete RAG pipeline including re-ranking and summarization.
"""
import pytest
import asyncio
from unittest.mock import Mock, AsyncMock, patch
from pathlib import Path
import tempfile
import shutil

from app.services.advanced_rag import AdvancedRAGService
from app.services.contextual_summarization import SummarizationConfig
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
    return [
        Text(
            text="This study examined the gut microbiome in 100 human participants with inflammatory bowel disease. The analysis used 16S rRNA sequencing at the genus level.",
            name="chunk_1"
        ),
        Text(
            text="The host species was clearly identified as Homo sapiens. All participants were adults between 18-65 years old.",
            name="chunk_2"
        ),
        Text(
            text="Samples were collected from the gastrointestinal tract, specifically the colon. The study included both healthy controls and patients with Crohn's disease.",
            name="chunk_3"
        ),
        Text(
            text="The sequencing analysis focused on taxonomic classification at the genus level. Over 200 different genera were identified.",
            name="chunk_4"
        ),
        Text(
            text="A total of 100 participants were included in this study, with 50 controls and 50 patients with IBD.",
            name="chunk_5"
        ),
    ]


@pytest.fixture
def mock_llm_provider():
    """Create a mock LLM provider."""
    mock = Mock()
    mock.chat = AsyncMock(return_value={
        "text": "This study analyzed the gut microbiome in human participants with IBD using 16S sequencing. Key findings include genus-level analysis of 100 participants."
    })
    return mock


@pytest.fixture
def rag_service(temp_cache_dir, mock_llm_provider):
    """Create an AdvancedRAGService with mocked dependencies."""
    with patch('app.services.contextual_summarization.LLMProviderManager') as mock_summary, \
         patch('app.services.chunk_reranking.LLMProviderManager') as mock_rerank:
        mock_summary.return_value = mock_llm_provider
        mock_rerank.return_value = mock_llm_provider
        
        service = AdvancedRAGService(
            summary_provider="gemini",
            summary_model="gemini/gemini-2.0-flash",
            rerank_method="hybrid",
            cache_dir=str(temp_cache_dir)
        )
        service.summarization_service.summary_llm = mock_llm_provider
        service.reranker.llm_manager = mock_llm_provider
        return service


class TestAdvancedRAGService:
    """Test AdvancedRAGService integration."""
    
    def test_initialization(self, temp_cache_dir):
        """Test service initialization."""
        service = AdvancedRAGService(
            summary_provider="gemini",
            rerank_method="keyword",
            cache_dir=str(temp_cache_dir)
        )
        assert service.summarization_service is not None
        assert service.reranker is not None
    
    @pytest.mark.asyncio
    async def test_retrieve_and_summarize(self, rag_service, sample_chunks):
        """Test the complete retrieve and summarize pipeline."""
        query = "What is the host species and body site?"
        
        summaries, ranked_chunks = await rag_service.retrieve_and_summarize(
            chunks=sample_chunks,
            query=query,
            top_k=3
        )
        
        assert len(summaries) > 0
        assert len(ranked_chunks) > 0
        assert len(summaries) <= 3  # top_k limit
        assert all(hasattr(s, 'summary') for s in summaries)
        assert all(hasattr(rc, 'relevance_score') for rc in ranked_chunks)
    
    @pytest.mark.asyncio
    async def test_get_contextual_context(self, rag_service, sample_chunks):
        """Test getting contextual context string."""
        query = "What host species is being studied?"
        
        context = await rag_service.get_contextual_context(
            chunks=sample_chunks,
            query=query,
            top_k=3
        )
        
        assert isinstance(context, str)
        assert len(context) > 0
        # Should contain summaries
        assert "Relevance:" in context or len(context) > 100
    
    @pytest.mark.asyncio
    async def test_get_contextual_context_fallback(self, rag_service, sample_chunks):
        """Test fallback when summarization fails."""
        # Mock summarization to return empty
        rag_service.summarization_service.summarize_chunks = AsyncMock(return_value=[])
        
        query = "Test query"
        context = await rag_service.get_contextual_context(
            chunks=sample_chunks,
            query=query
        )
        
        # Should fallback to original chunks
        assert isinstance(context, str)
        assert len(context) > 0
    
    @pytest.mark.asyncio
    async def test_different_rerank_methods(self, temp_cache_dir, sample_chunks, mock_llm_provider):
        """Test RAG service with different re-ranking methods."""
        for method in ["keyword", "llm", "hybrid"]:
            with patch('app.services.contextual_summarization.LLMProviderManager') as mock_summary, \
                 patch('app.services.chunk_reranking.LLMProviderManager') as mock_rerank:
                mock_summary.return_value = mock_llm_provider
                mock_rerank.return_value = mock_llm_provider
                
                service = AdvancedRAGService(
                    rerank_method=method,
                    cache_dir=str(temp_cache_dir)
                )
                service.summarization_service.summary_llm = mock_llm_provider
                if method != "keyword":
                    service.reranker.llm_manager = mock_llm_provider
                
                context = await service.get_contextual_context(
                    chunks=sample_chunks,
                    query="Test query",
                    top_k=2
                )
                
                assert isinstance(context, str)
                assert len(context) > 0
    
    @pytest.mark.asyncio
    async def test_get_summary_stats(self, rag_service, sample_chunks):
        """Test summary statistics calculation."""
        query = "Test query"
        summaries, _ = await rag_service.retrieve_and_summarize(
            chunks=sample_chunks,
            query=query,
            top_k=3
        )
        
        stats = rag_service.get_summary_stats(summaries)
        
        assert stats["num_summaries"] == len(summaries)
        assert stats["avg_relevance"] >= 0.0
        assert stats["avg_confidence"] >= 0.0
        assert stats["total_key_points"] >= 0
        assert "min_relevance" in stats
        assert "max_relevance" in stats
    
    @pytest.mark.asyncio
    async def test_get_summary_stats_empty(self, rag_service):
        """Test summary stats with empty summaries."""
        stats = rag_service.get_summary_stats([])
        
        assert stats["num_summaries"] == 0
        assert stats["avg_relevance"] == 0.0
        assert stats["avg_confidence"] == 0.0
        assert stats["total_key_points"] == 0
    
    @pytest.mark.asyncio
    async def test_top_k_filtering(self, rag_service, sample_chunks):
        """Test that top_k properly filters results."""
        query = "Test query"
        
        for top_k in [1, 2, 3, 5]:
            summaries, ranked = await rag_service.retrieve_and_summarize(
                chunks=sample_chunks,
                query=query,
                top_k=top_k
            )
            
            assert len(summaries) <= top_k
            assert len(ranked) <= top_k * 2  # May get more for summarization
    
    @pytest.mark.asyncio
    async def test_empty_chunks(self, rag_service):
        """Test handling of empty chunk list."""
        summaries, ranked = await rag_service.retrieve_and_summarize(
            chunks=[],
            query="Test query"
        )
        
        assert summaries == []
        assert ranked == []
    
    @pytest.mark.asyncio
    async def test_chunk_id_matching(self, rag_service, sample_chunks):
        """Test that ranked chunks match summary chunk IDs."""
        query = "Test query"
        summaries, ranked_chunks = await rag_service.retrieve_and_summarize(
            chunks=sample_chunks,
            query=query,
            top_k=3
        )
        
        summary_ids = {s.chunk_id for s in summaries}
        ranked_ids = {
            getattr(rc.chunk, 'name', f"chunk_{id(rc.chunk)}")
            for rc in ranked_chunks
        }
        
        # Ranked chunks should match summaries
        assert summary_ids.issubset(ranked_ids) or len(summaries) == 0

