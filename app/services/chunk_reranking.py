import logging
import time
from typing import List, Optional, Dict, Any
from dataclasses import dataclass
import re

logger = logging.getLogger(__name__)

try:
    from app.models.llm_provider import LLMProviderManager, LITELLM_AVAILABLE
except ImportError:
    LITELLM_AVAILABLE = False
    LLMProviderManager = None

from app.utils.config import GEMINI_TIMEOUT
from paperqa.types import Text


@dataclass
class RankedChunk:
    chunk: Text
    relevance_score: float
    rank: int
    reasoning: Optional[str] = None
    processing_time: Optional[float] = None


class ChunkReRanker:
    """Chunk re-ranking service for relevance-based chunk prioritization."""

    def __init__(
        self,
        rerank_method: str = "hybrid",
        llm_provider: Optional[str] = None,
        llm_model: Optional[str] = None,
        evidence_k: Optional[int] = None,
        use_10_scale: bool = True,
    ):
        self.rerank_method = rerank_method.lower()
        self.llm_manager = None
        self.evidence_k = evidence_k
        self.use_10_scale = use_10_scale
        self._metrics: Dict[str, Any] = {}

        if self.rerank_method in {"llm", "hybrid"}:
            if LITELLM_AVAILABLE and LLMProviderManager:
                try:
                    self.llm_manager = LLMProviderManager(
                        provider=llm_provider, model=llm_model
                    )
                except Exception:
                    if self.rerank_method == "llm":
                        self.rerank_method = "keyword"
            else:
                if self.rerank_method == "llm":
                    self.rerank_method = "keyword"

    def _normalize_score(self, score: float) -> float:
        """Normalize score to 0-1."""
        if self.use_10_scale:
            return max(0.0, min(1.0, score / 10.0))
        return max(0.0, min(1.0, score))

    def get_metrics(self) -> Dict[str, Any]:
        """Return a copy of the internal performance metrics."""
        return dict(self._metrics)

    async def rerank_chunks(
        self,
        chunks: List[Text],
        query: str,
        top_k: Optional[int] = None,
        evidence_k: Optional[int] = None,
    ) -> List[RankedChunk]:
        start_time = time.time()
        if not chunks:
            return []

        chunks_to_rerank = chunks[
            : (
                (evidence_k or self.evidence_k)
                if (evidence_k or self.evidence_k)
                else len(chunks)
            )
        ]

        if self.rerank_method == "keyword":
            ranked = await self._keyword_rerank(chunks_to_rerank, query)
        elif self.rerank_method == "llm":
            ranked = await self._llm_rerank(chunks_to_rerank, query)
        else:
            ranked = await self._hybrid_rerank(chunks_to_rerank, query)

        # Normalize scores
        for rc in ranked:
            rc.relevance_score = self._normalize_score(rc.relevance_score)

        ranked.sort(key=lambda x: x.relevance_score, reverse=True)
        for i, rc in enumerate(ranked, start=1):
            rc.rank = i

        if top_k:
            ranked = ranked[:top_k]

        self._metrics["processing_time"] = time.time() - start_time
        return ranked

    async def _keyword_rerank(self, chunks: List[Text], query: str):
        terms = set(re.findall(r"\b\w+\b", query.lower()))
        results = []
        for chunk in chunks:
            text = chunk.text.lower()
            matches = sum(1 for t in terms if t in text)
            score = matches / len(terms) if terms else 0.0
            results.append(RankedChunk(chunk, score, 0))
        return results

    async def _llm_rerank(self, chunks: List[Text], query: str):
        if not self.llm_manager:
            return await self._keyword_rerank(chunks, query)

        results = []
        for chunk in chunks:
            try:
                prompt = self._create_rerank_prompt_10_scale(query, chunk.text)
                response = await self.llm_manager.chat(
                    messages=[{"role": "user", "content": prompt}],
                    temperature=0.1,
                    timeout=GEMINI_TIMEOUT,
                )
                score = self._parse_score_from_response_10_scale(
                    response.get("text", "")
                )
                reasoning = self._extract_reasoning(response.get("text", ""))
            except Exception:
                score = (await self._calculate_keyword_score(chunk.text, query)) * 10
                reasoning = None
            results.append(RankedChunk(chunk, score, 0, reasoning))
        return results

    async def _hybrid_rerank(self, chunks: List[Text], query: str):
        keyword_ranked = await self._keyword_rerank(chunks, query)
        if not self.llm_manager:
            return keyword_ranked

        llm_ranked = await self._llm_rerank(chunks[:10], query)
        # Use chunk text as key since Text objects can't be hashed if they have unhashable extras
        llm_map = {rc.chunk.text: rc.relevance_score for rc in llm_ranked}

        results = []
        for rc in keyword_ranked:
            chunk_text = rc.chunk.text
            if chunk_text in llm_map:
                combined = llm_map[chunk_text] * 0.7 + rc.relevance_score * 0.3
                results.append(RankedChunk(rc.chunk, combined, 0))
            else:
                results.append(rc)
        return results

    def _create_rerank_prompt_10_scale(self, query: str, text: str) -> str:
        return f"Rate relevance (0–10).\nQuery: {query}\nText: {text[:1000]}\nSCORE:"

    def _parse_score_from_response_10_scale(self, text: str) -> float:
        match = re.search(r"([0-9]+(\.[0-9]+)?)", text)
        if match:
            return max(0.0, min(10.0, float(match.group(1))))
        return 5.0

    async def _calculate_keyword_score(self, text: str, query: str) -> float:
        terms = set(re.findall(r"\b\w+\b", query.lower()))
        matches = sum(1 for t in terms if t in text.lower())
        return matches / len(terms) if terms else 0.0

    def _parse_score_from_response(self, response: str) -> float:
        """Parse score from LLM response, returning 0.5 as default for invalid input."""
        match = re.search(r"([0-9]*\.?[0-9]+)", response)
        if not match:
            return 0.5  # Default fallback score for invalid input
        return min(max(float(match.group(1)), 0.0), 1.0)

    def _extract_reasoning(self, response: str) -> Optional[str]:
        """Extract reasoning from LLM response, returning None if no reasoning marker found."""
        if not response:
            return None
        patterns = [
            r"Reasoning\s*[:\-]\s*(.+)",
            r"Explanation\s*[:\-]\s*(.+)",
            r"Because\s+(.+)",
        ]
        for pattern in patterns:
            match = re.search(pattern, response, re.IGNORECASE | re.DOTALL)
            if match:
                return match.group(1).strip()
        # Return None if no reasoning marker found
        return None
