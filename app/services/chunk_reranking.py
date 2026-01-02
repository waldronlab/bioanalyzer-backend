"""Chunk re-ranking service for relevance-based chunk prioritization."""

import logging
import time
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.models.llm_provider import LLMProviderManager

try:
    from app.models.llm_provider import LITELLM_AVAILABLE, LLMProviderManager
except ImportError:
    LITELLM_AVAILABLE = False
    LLMProviderManager = None  # type: ignore[assignment,misc]

from paperqa.types import Text

from app.utils.config import GEMINI_TIMEOUT


@dataclass
class RankedChunk:
    """Chunk with relevance ranking information."""

    chunk: Text
    relevance_score: float
    rank: int
    reasoning: Optional[str] = None
    processing_time: Optional[float] = None


class ChunkReRanker:
    """Service for re-ranking chunks based on query relevance."""

    def __init__(
        self,
        rerank_method: str = "hybrid",
        llm_provider: Optional[str] = None,
        llm_model: Optional[str] = None,
        evidence_k: Optional[int] = None,
        use_10_scale: bool = True,
    ):
        """Initialize chunk re-ranker with specified method and configuration."""
        self.rerank_method = rerank_method.lower()
        self.llm_manager = None
        self.evidence_k = evidence_k
        self.use_10_scale = use_10_scale
        self._metrics: Dict[str, Any] = {}

        if self.rerank_method in ["llm", "hybrid"]:
            if LITELLM_AVAILABLE and LLMProviderManager:
                try:
                    self.llm_manager = LLMProviderManager(provider=llm_provider, model=llm_model)
                    logger.info(
                        f"ChunkReRanker: Using LLM for re-ranking (scale: {'0-10' if use_10_scale else '0-1.0'})"
                    )
                except Exception as e:
                    logger.warning(f"Failed to initialize LLM for re-ranking: {e}")
                    if self.rerank_method == "llm":
                        logger.warning("Falling back to keyword-based re-ranking")
                        self.rerank_method = "keyword"

    async def rerank_chunks(
        self, chunks: List[Text], query: str, top_k: Optional[int] = None, evidence_k: Optional[int] = None
    ) -> List[RankedChunk]:
        """
        Re-rank chunks based on relevance to query.

        Args:
            chunks: List of text chunks to re-rank
            query: Query string for relevance scoring
            top_k: Return only top K chunks after re-ranking (None for all)
            evidence_k: Number of evidence chunks to use for re-ranking (None = use all or instance default)

        Returns:
            List of RankedChunk objects sorted by relevance (highest first)
        """
        start_time = time.time()
        self._metrics = {
            "total_chunks": len(chunks),
            "evidence_k": evidence_k or self.evidence_k,
            "rerank_method": self.rerank_method,
            "query_length": len(query),
        }

        if not chunks:
            self._metrics["processing_time"] = time.time() - start_time
            return []

        # Apply evidence_k filter if specified (retrieve top evidence_k chunks first)
        chunks_to_rerank = chunks
        if evidence_k is not None or self.evidence_k is not None:
            evidence_limit = evidence_k or self.evidence_k
            # If we have embeddings, we could do embedding search here
            # For now, just limit the number of chunks
            chunks_to_rerank = chunks[:evidence_limit]
            self._metrics["chunks_after_evidence_k"] = len(chunks_to_rerank)

        # Score chunks
        if self.rerank_method == "keyword":
            scored_chunks = await self._keyword_rerank(chunks_to_rerank, query)
        elif self.rerank_method == "llm":
            scored_chunks = await self._llm_rerank(chunks_to_rerank, query)
        else:  # hybrid
            scored_chunks = await self._hybrid_rerank(chunks_to_rerank, query)

        # Sort by relevance score (descending)
        scored_chunks.sort(key=lambda x: x.relevance_score, reverse=True)

        # Assign ranks
        for rank, ranked_chunk in enumerate(scored_chunks, 1):
            ranked_chunk.rank = rank

        # Return top K if specified
        if top_k:
            scored_chunks = scored_chunks[:top_k]

        # Update metrics
        self._metrics.update(
            {
                "processing_time": time.time() - start_time,
                "chunks_reranked": len(scored_chunks),
                "avg_relevance_score": (
                    sum(rc.relevance_score for rc in scored_chunks) / len(scored_chunks) if scored_chunks else 0.0
                ),
                "max_relevance_score": max((rc.relevance_score for rc in scored_chunks), default=0.0),
                "min_relevance_score": min((rc.relevance_score for rc in scored_chunks), default=0.0),
            }
        )

        return scored_chunks

    def get_metrics(self) -> Dict[str, Any]:
        """Get performance metrics for the last re-ranking operation."""
        return self._metrics.copy()

    async def _keyword_rerank(self, chunks: List[Text], query: str) -> List[RankedChunk]:
        """Re-rank using keyword-based scoring."""
        import re

        query_terms = set(re.findall(r"\b\w+\b", query.lower()))
        scored_chunks = []

        for chunk in chunks:
            chunk_text = chunk.text if hasattr(chunk, "text") else str(chunk)
            chunk_lower = chunk_text.lower()

            # Count query term matches
            matches = sum(1 for term in query_terms if term in chunk_lower)

            # Calculate score
            if len(query_terms) > 0:
                score = min(1.0, matches / len(query_terms))
            else:
                score = 0.0

            # Boost for exact phrase matches
            if query.lower() in chunk_lower:
                score = min(1.0, score + 0.3)

            scored_chunks.append(RankedChunk(chunk=chunk, relevance_score=score, rank=0))  # Will be assigned later

        return scored_chunks

    async def _llm_rerank(self, chunks: List[Text], query: str) -> List[RankedChunk]:
        """Re-rank using LLM-based relevance scoring with 0-10 scale."""
        if not self.llm_manager:
            # Fallback to keyword
            return await self._keyword_rerank(chunks, query)

        scored_chunks = []
        chunk_times = []

        for chunk in chunks:
            chunk_start = time.time()
            chunk_text = chunk.text if hasattr(chunk, "text") else str(chunk)

            # Create relevance scoring prompt (0-10 scale)
            if self.use_10_scale:
                prompt = self._create_rerank_prompt_10_scale(query, chunk_text)
            else:
                prompt = self._create_rerank_prompt_01_scale(query, chunk_text)

            try:
                response = await self.llm_manager.chat(
                    messages=[{"role": "user", "content": prompt}],
                    temperature=0.1,  # Low temperature for consistent scoring
                    timeout=GEMINI_TIMEOUT,
                )

                text = response.get("text", "")

                # Parse score from response
                if self.use_10_scale:
                    score = self._parse_score_from_response_10_scale(text)
                else:
                    score = self._parse_score_from_response(text)
                reasoning = self._extract_reasoning(text)

            except Exception as e:
                logger.warning(f"LLM re-ranking failed for chunk: {e}")
                # Fallback to keyword scoring (normalize to same scale)
                keyword_score = await self._calculate_keyword_score(chunk_text, query)
                if self.use_10_scale:
                    score = keyword_score * 10.0  # Convert 0-1.0 to 0-10
                else:
                    score = keyword_score
                reasoning = "LLM scoring failed, used keyword fallback"

            chunk_time = time.time() - chunk_start
            chunk_times.append(chunk_time)

            scored_chunks.append(
                RankedChunk(chunk=chunk, relevance_score=score, rank=0, reasoning=reasoning, processing_time=chunk_time)
            )

        # Update metrics
        if chunk_times:
            self._metrics["avg_chunk_processing_time"] = sum(chunk_times) / len(chunk_times)
            self._metrics["total_chunk_processing_time"] = sum(chunk_times)
            self._metrics["max_chunk_processing_time"] = max(chunk_times)
            self._metrics["min_chunk_processing_time"] = min(chunk_times)

        return scored_chunks

    def _create_rerank_prompt_10_scale(self, query: str, chunk_text: str) -> str:
        """Create re-ranking prompt template for 0-10 scale."""
        return f"""Rate the relevance of the following text chunk to the query on a scale of 0 to 10.

Query: {query}

Text chunk:
{chunk_text[:1000]}

Provide a relevance score (0-10) where:
- 0-2: Not relevant or completely unrelated
- 3-4: Slightly relevant but not directly related
- 5-6: Moderately relevant with some connection
- 7-8: Highly relevant and directly addresses the query
- 9-10: Extremely relevant and provides definitive answer

Format your response as: SCORE: <number> REASONING: <brief explanation>"""

    def _create_rerank_prompt_01_scale(self, query: str, chunk_text: str) -> str:
        """Create re-ranking prompt template for 0-1.0 scale (backward compatibility)."""
        return f"""Rate the relevance of the following text chunk to the query on a scale of 0.0 to 1.0.

Query: {query}

Text chunk:
{chunk_text[:1000]}

Provide a relevance score (0.0 to 1.0) and a brief one-sentence explanation.
Format: SCORE: <number> REASONING: <explanation>"""

    async def _hybrid_rerank(self, chunks: List[Text], query: str) -> List[RankedChunk]:
        """Re-rank using hybrid approach (keyword + LLM)."""
        # Get keyword scores (0-1.0 scale)
        keyword_ranked = await self._keyword_rerank(chunks, query)

        # If LLM available, use it for top chunks
        if self.llm_manager and len(chunks) <= 20:  # Only use LLM for reasonable number of chunks
            # Re-rank top chunks with LLM
            top_keyword = keyword_ranked[:10]  # Top 10 from keyword
            llm_ranked = await self._llm_rerank([rc.chunk for rc in top_keyword], query)

            # Combine: use LLM scores for top chunks, keyword for rest
            result = []
            llm_scores = {rc.chunk: rc.relevance_score for rc in llm_ranked}

            for keyword_ranked_chunk in keyword_ranked:
                if keyword_ranked_chunk.chunk in llm_scores:
                    # Normalize scores to same scale for combination
                    llm_score = llm_scores[keyword_ranked_chunk.chunk]
                    keyword_score = keyword_ranked_chunk.relevance_score

                    # If LLM uses 0-10 scale, normalize keyword score to 0-10
                    if self.use_10_scale:
                        keyword_normalized = keyword_score * 10.0
                        # Combine: 70% LLM, 30% keyword
                        score = llm_score * 0.7 + keyword_normalized * 0.3
                    else:
                        # Both in 0-1.0 scale
                        score = llm_score * 0.7 + keyword_score * 0.3

                    result.append(
                        RankedChunk(
                            chunk=keyword_ranked_chunk.chunk,
                            relevance_score=score,
                            rank=0,
                            reasoning=next(
                                (rc.reasoning for rc in llm_ranked if rc.chunk == keyword_ranked_chunk.chunk), None
                            ),
                            processing_time=next(
                                (rc.processing_time for rc in llm_ranked if rc.chunk == keyword_ranked_chunk.chunk),
                                None,
                            ),
                        )
                    )
                else:
                    # Normalize keyword score if needed
                    if self.use_10_scale:
                        keyword_ranked_chunk.relevance_score = keyword_ranked_chunk.relevance_score * 10.0
                    result.append(keyword_ranked_chunk)

            return result

        # If no LLM, normalize keyword scores if using 10-scale
        if self.use_10_scale:
            for rc in keyword_ranked:
                rc.relevance_score = rc.relevance_score * 10.0

        return keyword_ranked

    def _parse_score_from_response_10_scale(self, text: str) -> float:
        """Parse relevance score from LLM response (0-10 scale)."""
        import re

        # Look for "SCORE: X" or "SCORE: X.X" pattern
        score_match = re.search(r"SCORE:\s*([0-9]+\.?[0-9]*)", text, re.IGNORECASE)
        if score_match:
            try:
                score = float(score_match.group(1))
                return max(0.0, min(10.0, score))  # Clamp to [0, 10]
            except ValueError:
                pass

        # Look for standalone integers 0-10
        numbers = re.findall(r"\b([0-9]|10)\b", text)
        if numbers:
            try:
                score = float(numbers[0])
                if 0 <= score <= 10:
                    return score
            except ValueError:
                pass

        # Look for decimal numbers that might be in 0-10 range
        decimal_match = re.search(r"\b([0-9]\.\d+)\b", text)
        if decimal_match:
            try:
                score = float(decimal_match.group(1))
                if 0 <= score <= 10:
                    return score
            except ValueError:
                pass

        # Default fallback (middle of scale)
        return 5.0

    def _parse_score_from_response(self, text: str) -> float:
        """Parse relevance score from LLM response (0-1.0 scale, backward compatibility)."""
        import re

        # Look for "SCORE: 0.XX" pattern
        score_match = re.search(r"SCORE:\s*([0-9.]+)", text, re.IGNORECASE)
        if score_match:
            try:
                score = float(score_match.group(1))
                return max(0.0, min(1.0, score))  # Clamp to [0, 1]
            except ValueError:
                pass

        # Look for standalone numbers
        numbers = re.findall(r"\b0?\.\d+\b|\b1\.0\b", text)
        if numbers:
            try:
                score = float(numbers[0])
                return max(0.0, min(1.0, score))
            except ValueError:
                pass

        # Default fallback
        return 0.5

    def _extract_reasoning(self, text: str) -> Optional[str]:
        """Extract reasoning from LLM response."""
        import re

        reasoning_match = re.search(r"REASONING:\s*(.+?)(?:\n|$)", text, re.IGNORECASE)
        if reasoning_match:
            return reasoning_match.group(1).strip()

        return None

    async def _calculate_keyword_score(self, text: str, query: str) -> float:
        """Calculate keyword-based relevance score."""
        import re

        query_terms = set(re.findall(r"\b\w+\b", query.lower()))
        text_lower = text.lower()

        matches = sum(1 for term in query_terms if term in text_lower)

        if len(query_terms) > 0:
            return min(1.0, matches / len(query_terms))
        return 0.0
