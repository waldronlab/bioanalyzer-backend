"""
Advanced RAG Service with Contextual Summarization

Integrates contextual summarization and re-ranking for improved field extraction.
"""
import logging
from typing import List, Dict, Optional, Tuple
from pathlib import Path

from app.services.contextual_summarization import (
    ContextualSummarizationService,
    SummarizationConfig,
    ChunkSummary
)
from app.services.chunk_reranking import ChunkReRanker, RankedChunk
from app.utils.config import (
    RAG_SUMMARY_PROVIDER,
    RAG_SUMMARY_MODEL,
    RAG_SUMMARY_LENGTH,
    RAG_SUMMARY_QUALITY,
    RAG_RERANK_METHOD,
    RAG_USE_SUMMARY_CACHE,
    RAG_MAX_SUMMARY_KEY_POINTS,
    RAG_TOP_K_CHUNKS
)
from paperqa.types import Text

logger = logging.getLogger(__name__)


class AdvancedRAGService:
    """
    Advanced RAG service that combines:
    - Contextual summarization (RCS)
    - Chunk re-ranking
    - Relevance scoring
    
    Provides improved field extraction accuracy through better context understanding.
    """
    
    def __init__(
        self,
        summary_provider: Optional[str] = None,
        summary_model: Optional[str] = None,
        rerank_method: Optional[str] = None,
        cache_dir: Optional[str] = None
    ):
        """
        Initialize the advanced RAG service.
        
        Args:
            summary_provider: LLM provider for summarization
            summary_model: Model for summarization
            rerank_method: Re-ranking method ("keyword", "llm", "hybrid")
            cache_dir: Directory for caching summaries
        """
        # Initialize summarization service
        summary_config = SummarizationConfig(
            summary_length=RAG_SUMMARY_LENGTH,
            quality=RAG_SUMMARY_QUALITY,
            max_key_points=RAG_MAX_SUMMARY_KEY_POINTS,
            use_cache=RAG_USE_SUMMARY_CACHE
        )
        
        self.summarization_service = ContextualSummarizationService(
            summary_llm_provider=summary_provider or RAG_SUMMARY_PROVIDER,
            summary_llm_model=summary_model or RAG_SUMMARY_MODEL,
            cache_dir=cache_dir,
            config=summary_config
        )
        
        # Initialize re-ranker
        self.reranker = ChunkReRanker(
            rerank_method=rerank_method or RAG_RERANK_METHOD,
            llm_provider=summary_provider or RAG_SUMMARY_PROVIDER,
            llm_model=summary_model or RAG_SUMMARY_MODEL
        )
        
        logger.info(
            f"AdvancedRAGService initialized: "
            f"summary_length={RAG_SUMMARY_LENGTH}, "
            f"rerank_method={rerank_method or RAG_RERANK_METHOD}"
        )
    
    async def retrieve_and_summarize(
        self,
        chunks: List[Text],
        query: str,
        top_k: Optional[int] = None
    ) -> Tuple[List[ChunkSummary], List[RankedChunk]]:
        """
        Retrieve, re-rank, and summarize chunks for a query.
        
        Args:
            chunks: List of text chunks to process
            query: Query/field being extracted
            top_k: Number of top chunks to return (uses RAG_TOP_K_CHUNKS if None)
            
        Returns:
            Tuple of (summaries, ranked_chunks)
        """
        top_k = top_k or RAG_TOP_K_CHUNKS
        
        logger.info(f"Processing {len(chunks)} chunks for query: {query[:50]}...")
        
        # Step 1: Re-rank chunks by relevance
        ranked_chunks = await self.reranker.rerank_chunks(
            chunks=chunks,
            query=query,
            top_k=top_k * 2  # Get more chunks for summarization, then filter
        )
        
        logger.info(f"Re-ranked chunks: top {len(ranked_chunks)} selected")
        
        # Step 2: Create contextual summaries for top chunks
        top_chunks = [rc.chunk for rc in ranked_chunks[:top_k]]
        summaries = await self.summarization_service.summarize_chunks(
            chunks=top_chunks,
            query=query
        )
        
        logger.info(f"Created {len(summaries)} contextual summaries")
        
        # Step 3: Filter ranked chunks to match summaries
        summary_chunk_ids = {s.chunk_id for s in summaries}
        filtered_ranked = [
            rc for rc in ranked_chunks
            if getattr(rc.chunk, 'name', f"chunk_{id(rc.chunk)}") in summary_chunk_ids
        ]
        
        return summaries, filtered_ranked
    
    async def get_contextual_context(
        self,
        chunks: List[Text],
        query: str,
        top_k: Optional[int] = None
    ) -> str:
        """
        Get contextual context string for field extraction.
        
        Combines re-ranked and summarized chunks into a single context string.
        
        Args:
            chunks: List of text chunks
            query: Query/field being extracted
            top_k: Number of top chunks to use
            
        Returns:
            Contextual context string for LLM
        """
        summaries, ranked_chunks = await self.retrieve_and_summarize(
            chunks=chunks,
            query=query,
            top_k=top_k
        )
        
        # Combine summaries into context
        context_parts = []
        for summary in summaries:
            if summary.summary:
                context_parts.append(f"[Relevance: {summary.relevance_score:.2f}] {summary.summary}")
                if summary.key_points:
                    context_parts.append(f"Key points: {'; '.join(summary.key_points[:3])}")
        
        if not context_parts:
            # Fallback to original chunks if no summaries
            context_parts = [
                f"{chunk.text[:500]}" for chunk in chunks[:top_k or RAG_TOP_K_CHUNKS]
            ]
        
        return "\n\n".join(context_parts)
    
    def get_summary_stats(self, summaries: List[ChunkSummary]) -> Dict:
        """Get statistics about summaries."""
        if not summaries:
            return {
                "num_summaries": 0,
                "avg_relevance": 0.0,
                "avg_confidence": 0.0,
                "total_key_points": 0
            }
        
        return {
            "num_summaries": len(summaries),
            "avg_relevance": sum(s.relevance_score for s in summaries) / len(summaries),
            "avg_confidence": sum(s.confidence for s in summaries) / len(summaries),
            "total_key_points": sum(len(s.key_points) for s in summaries),
            "min_relevance": min(s.relevance_score for s in summaries),
            "max_relevance": max(s.relevance_score for s in summaries)
        }

