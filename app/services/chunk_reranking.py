"""
Chunk Re-ranking Service

Implements re-ranking of evidence chunks based on relevance scoring.
Uses cross-encoder or LLM-based re-ranking to improve retrieval quality.
"""
import logging
from typing import List, Tuple, Optional
from dataclasses import dataclass

logger = logging.getLogger(__name__)

# Try to import LiteLLM for LLM-based re-ranking
try:
    from app.models.llm_provider import LLMProviderManager, LITELLM_AVAILABLE
except ImportError:
    LITELLM_AVAILABLE = False
    LLMProviderManager = None

from app.utils.config import GEMINI_TIMEOUT
from paperqa.types import Text


@dataclass
class RankedChunk:
    """Chunk with relevance ranking information."""
    chunk: Text
    relevance_score: float
    rank: int
    reasoning: Optional[str] = None


class ChunkReRanker:
    """
    Service for re-ranking chunks based on query relevance.
    
    Supports multiple re-ranking strategies:
    - Keyword-based scoring (fast, no LLM needed)
    - LLM-based relevance scoring (more accurate)
    - Hybrid approach (combines both)
    """
    
    def __init__(
        self,
        rerank_method: str = "hybrid",  # "keyword", "llm", "hybrid"
        llm_provider: Optional[str] = None,
        llm_model: Optional[str] = None
    ):
        """
        Initialize the chunk re-ranker.
        
        Args:
            rerank_method: Re-ranking method ("keyword", "llm", "hybrid")
            llm_provider: LLM provider for LLM-based re-ranking
            llm_model: Model for LLM-based re-ranking
        """
        self.rerank_method = rerank_method.lower()
        self.llm_manager = None
        
        if self.rerank_method in ["llm", "hybrid"]:
            if LITELLM_AVAILABLE and LLMProviderManager:
                try:
                    self.llm_manager = LLMProviderManager(
                        provider=llm_provider,
                        model=llm_model
                    )
                    logger.info(f"ChunkReRanker: Using LLM for re-ranking")
                except Exception as e:
                    logger.warning(f"Failed to initialize LLM for re-ranking: {e}")
                    if self.rerank_method == "llm":
                        logger.warning("Falling back to keyword-based re-ranking")
                        self.rerank_method = "keyword"
    
    async def rerank_chunks(
        self,
        chunks: List[Text],
        query: str,
        top_k: Optional[int] = None
    ) -> List[RankedChunk]:
        """
        Re-rank chunks based on relevance to query.
        
        Args:
            chunks: List of text chunks to re-rank
            query: Query string for relevance scoring
            top_k: Return only top K chunks (None for all)
            
        Returns:
            List of RankedChunk objects sorted by relevance (highest first)
        """
        if not chunks:
            return []
        
        # Score chunks
        if self.rerank_method == "keyword":
            scored_chunks = await self._keyword_rerank(chunks, query)
        elif self.rerank_method == "llm":
            scored_chunks = await self._llm_rerank(chunks, query)
        else:  # hybrid
            scored_chunks = await self._hybrid_rerank(chunks, query)
        
        # Sort by relevance score (descending)
        scored_chunks.sort(key=lambda x: x.relevance_score, reverse=True)
        
        # Assign ranks
        for rank, ranked_chunk in enumerate(scored_chunks, 1):
            ranked_chunk.rank = rank
        
        # Return top K if specified
        if top_k:
            return scored_chunks[:top_k]
        
        return scored_chunks
    
    async def _keyword_rerank(
        self,
        chunks: List[Text],
        query: str
    ) -> List[RankedChunk]:
        """Re-rank using keyword-based scoring."""
        import re
        
        query_terms = set(re.findall(r'\b\w+\b', query.lower()))
        scored_chunks = []
        
        for chunk in chunks:
            chunk_text = chunk.text if hasattr(chunk, 'text') else str(chunk)
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
            
            scored_chunks.append(RankedChunk(
                chunk=chunk,
                relevance_score=score,
                rank=0  # Will be assigned later
            ))
        
        return scored_chunks
    
    async def _llm_rerank(
        self,
        chunks: List[Text],
        query: str
    ) -> List[RankedChunk]:
        """Re-rank using LLM-based relevance scoring."""
        if not self.llm_manager:
            # Fallback to keyword
            return await self._keyword_rerank(chunks, query)
        
        scored_chunks = []
        
        for chunk in chunks:
            chunk_text = chunk.text if hasattr(chunk, 'text') else str(chunk)
            
            # Create relevance scoring prompt
            prompt = f"""Rate the relevance of the following text chunk to the query on a scale of 0.0 to 1.0.

Query: {query}

Text chunk:
{chunk_text[:1000]}

Provide a relevance score (0.0 to 1.0) and a brief one-sentence explanation.
Format: SCORE: <number> REASONING: <explanation>"""
            
            try:
                response = await self.llm_manager.chat(
                    messages=[{"role": "user", "content": prompt}],
                    temperature=0.1,  # Low temperature for consistent scoring
                    timeout=GEMINI_TIMEOUT,
                )
                
                text = response.get("text", "")
                
                # Parse score from response
                score = self._parse_score_from_response(text)
                reasoning = self._extract_reasoning(text)
                
            except Exception as e:
                logger.warning(f"LLM re-ranking failed for chunk: {e}")
                # Fallback to keyword scoring
                score = await self._calculate_keyword_score(chunk_text, query)
                reasoning = "LLM scoring failed, used keyword fallback"
            
            scored_chunks.append(RankedChunk(
                chunk=chunk,
                relevance_score=score,
                rank=0,
                reasoning=reasoning
            ))
        
        return scored_chunks
    
    async def _hybrid_rerank(
        self,
        chunks: List[Text],
        query: str
    ) -> List[RankedChunk]:
        """Re-rank using hybrid approach (keyword + LLM)."""
        # Get keyword scores
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
                    # Use LLM score with keyword as tiebreaker
                    score = (llm_scores[keyword_ranked_chunk.chunk] * 0.7 + 
                            keyword_ranked_chunk.relevance_score * 0.3)
                    result.append(RankedChunk(
                        chunk=keyword_ranked_chunk.chunk,
                        relevance_score=score,
                        rank=0,
                        reasoning=next((rc.reasoning for rc in llm_ranked 
                                     if rc.chunk == keyword_ranked_chunk.chunk), None)
                    ))
                else:
                    result.append(keyword_ranked_chunk)
            
            return result
        
        return keyword_ranked
    
    def _parse_score_from_response(self, text: str) -> float:
        """Parse relevance score from LLM response."""
        import re
        
        # Look for "SCORE: 0.XX" pattern
        score_match = re.search(r'SCORE:\s*([0-9.]+)', text, re.IGNORECASE)
        if score_match:
            try:
                score = float(score_match.group(1))
                return max(0.0, min(1.0, score))  # Clamp to [0, 1]
            except ValueError:
                pass
        
        # Look for standalone numbers
        numbers = re.findall(r'\b0?\.\d+\b|\b1\.0\b', text)
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
        
        reasoning_match = re.search(r'REASONING:\s*(.+?)(?:\n|$)', text, re.IGNORECASE)
        if reasoning_match:
            return reasoning_match.group(1).strip()
        
        return None
    
    async def _calculate_keyword_score(self, text: str, query: str) -> float:
        """Calculate keyword-based relevance score."""
        import re
        
        query_terms = set(re.findall(r'\b\w+\b', query.lower()))
        text_lower = text.lower()
        
        matches = sum(1 for term in query_terms if term in text_lower)
        
        if len(query_terms) > 0:
            return min(1.0, matches / len(query_terms))
        return 0.0

