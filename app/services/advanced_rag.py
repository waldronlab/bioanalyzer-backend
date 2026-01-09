"""RAG pipeline for better field extraction accuracy.

Re-ranks text chunks by relevance to each field query, then generates
query-aware summaries. More accurate than simple analysis but slower and
more expensive (multiple LLM calls per field).
"""

import logging
from typing import List, Dict, Optional, Tuple, Any
from pathlib import Path

from app.services.contextual_summarization import (
    ContextualSummarizationService,
    SummarizationConfig,
    ChunkSummary,
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
    RAG_TOP_K_CHUNKS,
)
from paperqa.types import Text

logger = logging.getLogger(__name__)


class AdvancedRAGService:
    """RAG pipeline: re-rank chunks, then summarize before querying LLM.

    This is what makes v2 API more accurate than v1. The tradeoff is speed
    and cost - expect 2-3x more LLM API calls per field.
    """

    def __init__(
        self,
        summary_provider: Optional[str] = None,
        summary_model: Optional[str] = None,
        rerank_method: Optional[str] = None,
        cache_dir: Optional[str] = None,
        evidence_k: Optional[int] = None,
        max_sources: Optional[int] = None,
        use_10_scale: bool = True,
    ):
        """Set up RAG service with configuration.

        Args:
            summary_provider: LLM provider for summarization (default: auto-detect).
            summary_model: Model for summarization (default: provider default).
            rerank_method: keyword|llm|hybrid (default: hybrid).
            cache_dir: Where to cache summaries (default: cache/).
            evidence_k: Initial chunks to retrieve before re-ranking.
            max_sources: Max chunks to use after re-ranking.
            use_10_scale: Use 0-10 relevance scale instead of 0-1.
        """
        summary_config = SummarizationConfig(
            summary_length=RAG_SUMMARY_LENGTH,
            quality=RAG_SUMMARY_QUALITY,
            max_key_points=RAG_MAX_SUMMARY_KEY_POINTS,
            use_cache=RAG_USE_SUMMARY_CACHE,
        )

        self.summarization_service = ContextualSummarizationService(
            summary_llm_provider=summary_provider or RAG_SUMMARY_PROVIDER,
            summary_llm_model=summary_model or RAG_SUMMARY_MODEL,
            cache_dir=cache_dir,
            config=summary_config,
        )

        self.reranker = ChunkReRanker(
            rerank_method=rerank_method or RAG_RERANK_METHOD,
            llm_provider=summary_provider or RAG_SUMMARY_PROVIDER,
            llm_model=summary_model or RAG_SUMMARY_MODEL,
            evidence_k=evidence_k,
            use_10_scale=use_10_scale,
        )

        self.max_sources = max_sources or RAG_TOP_K_CHUNKS
        self.evidence_k = evidence_k

        logger.info(
            f"AdvancedRAGService initialized: "
            f"summary_length={RAG_SUMMARY_LENGTH}, "
            f"rerank_method={rerank_method or RAG_RERANK_METHOD}, "
            f"evidence_k={evidence_k}, "
            f"max_sources={self.max_sources}, "
            f"use_10_scale={use_10_scale}"
        )

    async def retrieve_and_summarize(
        self,
        chunks: List[Text],
        query: str,
        top_k: Optional[int] = None,
        evidence_k: Optional[int] = None,
        max_sources: Optional[int] = None,
    ) -> Tuple[List[ChunkSummary], List[RankedChunk]]:
        """
        Retrieve, re-rank, and summarize chunks for a query.

        Args:
            chunks: List of text chunks to process
            query: Query/field being extracted
            top_k: Number of top chunks to return (uses RAG_TOP_K_CHUNKS if None)
            evidence_k: Number of evidence chunks to retrieve before re-ranking
            max_sources: Maximum number of sources to use for final answer

        Returns:
            Tuple of (summaries, ranked_chunks)
        """
        top_k = top_k or RAG_TOP_K_CHUNKS
        evidence_k = evidence_k or self.evidence_k
        max_sources = max_sources or self.max_sources

        logger.info(f"Processing {len(chunks)} chunks for query: {query[:50]}...")

        # Step 1: Re-rank chunks by relevance (with evidence_k)
        ranked_chunks = await self.reranker.rerank_chunks(
            chunks=chunks, query=query, top_k=top_k * 2, evidence_k=evidence_k
        )

        logger.info(f"Re-ranked chunks: top {len(ranked_chunks)} selected")

        # Step 2: Apply max_sources limit
        if max_sources and len(ranked_chunks) > max_sources:
            ranked_chunks = ranked_chunks[:max_sources]
            logger.info(f"Limited to {max_sources} sources (max_sources)")

        # Step 3: Create contextual summaries for top chunks
        top_chunks = [rc.chunk for rc in ranked_chunks[:top_k]]
        summaries = await self.summarization_service.summarize_chunks(
            chunks=top_chunks, query=query
        )

        logger.info(f"Created {len(summaries)} contextual summaries")

        # Step 4: Filter ranked chunks to match summaries
        summary_chunk_ids = {s.chunk_id for s in summaries}
        filtered_ranked = [
            rc
            for rc in ranked_chunks
            if getattr(rc.chunk, "name", f"chunk_{id(rc.chunk)}") in summary_chunk_ids
        ]

        return summaries, filtered_ranked

    async def get_contextual_context(
        self,
        chunks: List[Text],
        query: str,
        top_k: Optional[int] = None,
        evidence_k: Optional[int] = None,
        max_sources: Optional[int] = None,
    ) -> str:
        """
        Get contextual context string for field extraction.

        Combines re-ranked and summarized chunks into a single context string.

        Args:
            chunks: List of text chunks
            query: Query/field being extracted
            top_k: Number of top chunks to use
            evidence_k: Number of evidence chunks to retrieve before re-ranking
            max_sources: Maximum number of sources to use for final answer

        Returns:
            Contextual context string for LLM
        """
        summaries, ranked_chunks = await self.retrieve_and_summarize(
            chunks=chunks,
            query=query,
            top_k=top_k,
            evidence_k=evidence_k,
            max_sources=max_sources,
        )

        # Apply max_sources limit to summaries
        if max_sources and len(summaries) > max_sources:
            summaries = summaries[:max_sources]

        # Combine summaries into context
        context_parts = []
        for summary in summaries:
            if summary.summary:
                # Format relevance score based on scale
                if self.reranker.use_10_scale:
                    score_str = f"{summary.relevance_score:.1f}/10"
                else:
                    score_str = f"{summary.relevance_score:.2f}"
                context_parts.append(f"[Relevance: {score_str}] {summary.summary}")
                if summary.key_points:
                    context_parts.append(
                        f"Key points: {'; '.join(summary.key_points[:3])}"
                    )

        if not context_parts:
            # Fallback to original chunks if no summaries
            context_parts = [
                f"{chunk.text[:500]}" for chunk in chunks[: top_k or RAG_TOP_K_CHUNKS]
            ]

        return "\n\n".join(context_parts)

    def get_rerank_metrics(self) -> Dict[str, Any]:
        """Get performance metrics from the re-ranker."""
        return self.reranker.get_metrics()

    def get_summary_stats(self, summaries: List[ChunkSummary]) -> Dict[str, Any]:
        """Get statistics about summaries."""
        if not summaries:
            return {
                "num_summaries": 0,
                "avg_relevance": 0.0,
                "avg_confidence": 0.0,
                "total_key_points": 0,
            }

        return {
            "num_summaries": len(summaries),
            "avg_relevance": sum(s.relevance_score for s in summaries) / len(summaries),
            "avg_confidence": sum(s.confidence for s in summaries) / len(summaries),
            "total_key_points": sum(len(s.key_points) for s in summaries),
            "min_relevance": min(s.relevance_score for s in summaries),
            "max_relevance": max(s.relevance_score for s in summaries),
        }
