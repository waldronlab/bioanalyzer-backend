"""Contextual summarization service for creating query-aware summaries of text chunks."""

import hashlib
import json
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.models.llm_provider import LLMProviderManager

_LLMProviderManagerClass: type["LLMProviderManager"] | None

try:
    from app.models.llm_provider import LITELLM_AVAILABLE, LLMProviderManager  # noqa: F811

    _LLMProviderManagerClass = LLMProviderManager
except ImportError:
    LITELLM_AVAILABLE = False
    _LLMProviderManagerClass = None

from paperqa.types import Text

from app.utils.config import GEMINI_TIMEOUT


@dataclass
class ChunkSummary:
    """Summary of a text chunk with relevance information."""

    chunk_id: str
    original_text: str
    summary: str
    relevance_score: float
    query: str
    key_points: List[str]
    confidence: float


@dataclass
class SummarizationConfig:
    """Configuration for contextual summarization."""

    summary_length: str = "medium"
    quality: str = "balanced"
    max_key_points: int = 5
    temperature: float = 0.3
    use_cache: bool = True


class ContextualSummarizationService:
    """Service for creating contextual summaries of text chunks."""

    def __init__(
        self,
        summary_llm_provider: Optional[str] = None,
        summary_llm_model: Optional[str] = None,
        cache_dir: Optional[str] = None,
        config: Optional[SummarizationConfig] = None,
    ):
        """Initialize contextual summarization service."""
        self.config = config or SummarizationConfig()
        self.cache_dir = Path(cache_dir) if cache_dir else Path("cache/summaries")
        self.cache_dir.mkdir(parents=True, exist_ok=True)

        self.summary_llm = None
        if LITELLM_AVAILABLE and _LLMProviderManagerClass:
            try:
                self.summary_llm = _LLMProviderManagerClass(provider=summary_llm_provider, model=summary_llm_model)
                logger.info(
                    f"ContextualSummarizationService: Using {self.summary_llm.provider.value} "
                    f"model {self.summary_llm.model} for summarization"
                )
            except Exception as e:
                logger.warning(f"Failed to initialize summary LLM: {e}")
                self.summary_llm = None

        self.summary_templates = self._create_summary_templates()

    def _create_summary_templates(self) -> Dict[str, str]:
        """Create prompt templates for different summary lengths."""
        return {
            "short": """Summarize the following text chunk in 2-3 sentences, focusing on information relevant to the query.

Query: {query}

Text chunk:
{text}

Provide a concise summary that highlights information directly related to the query.""",
            "medium": """Create a contextual summary of the following text chunk that focuses on information relevant to the query.

Query: {query}

Text chunk:
{text}

Summary should:
1. Highlight key information related to the query
2. Preserve important details and context
3. Be 3-5 sentences long
4. Focus on facts and evidence, not opinions""",
            "long": """Create a comprehensive contextual summary of the following text chunk that focuses on information relevant to the query.

Query: {query}

Text chunk:
{text}

Summary should:
1. Provide a detailed overview of information relevant to the query
2. Include key facts, numbers, and evidence
3. Preserve important context and relationships
4. Be 5-7 sentences long
5. Extract specific details that answer the query""",
        }

    def _get_cache_key(self, chunk_text: str, query: str, summary_length: str) -> str:
        """Generate cache key for summary."""
        content = f"{chunk_text[:500]}_{query}_{summary_length}"
        return hashlib.md5(content.encode()).hexdigest()

    def _load_cached_summary(self, cache_key: str) -> Optional[Dict]:
        """Load cached summary if available."""
        if not self.config.use_cache:
            return None

        cache_file = self.cache_dir / f"{cache_key}.json"
        if cache_file.exists():
            try:
                with open(cache_file, "r") as f:
                    return json.load(f)
            except Exception as e:
                logger.warning(f"Failed to load cached summary: {e}")
        return None

    def _save_cached_summary(self, cache_key: str, summary_data: Dict):
        """Save summary to cache."""
        if not self.config.use_cache:
            return

        cache_file = self.cache_dir / f"{cache_key}.json"
        try:
            with open(cache_file, "w") as f:
                json.dump(summary_data, f, indent=2)
        except Exception as e:
            logger.warning(f"Failed to save cached summary: {e}")

    async def summarize_chunk(self, chunk: Text, query: str, summary_length: Optional[str] = None) -> ChunkSummary:
        """Create contextual summary of text chunk based on query."""
        summary_length = summary_length or self.config.summary_length
        chunk_text = chunk.text if hasattr(chunk, "text") else str(chunk)
        chunk_id = getattr(chunk, "name", f"chunk_{id(chunk)}")

        cache_key = self._get_cache_key(chunk_text, query, summary_length)
        cached = self._load_cached_summary(cache_key)
        if cached:
            logger.debug(f"Using cached summary for chunk {chunk_id}")
            return ChunkSummary(
                chunk_id=chunk_id,
                original_text=chunk_text,
                summary=cached["summary"],
                relevance_score=cached["relevance_score"],
                query=query,
                key_points=cached.get("key_points", []),
                confidence=cached.get("confidence", 0.8),
            )

        template = self.summary_templates.get(summary_length, self.summary_templates["medium"])
        prompt = template.format(query=query, text=chunk_text[:3000])  # Limit text length

        summary_text = ""
        key_points = []
        confidence = 0.5

        if self.summary_llm:
            try:
                response = await self.summary_llm.chat(
                    messages=[{"role": "user", "content": prompt}],
                    temperature=self.config.temperature,
                    timeout=GEMINI_TIMEOUT,
                )
                summary_text = response.get("text", "")
                confidence = response.get("confidence", 0.5)
            except Exception as e:
                logger.error(f"Summary LLM failed: {e}")
                # Fallback to simple extraction
                summary_text = self._extract_key_sentences(chunk_text, query)
        else:
            # Fallback: extract key sentences
            summary_text = self._extract_key_sentences(chunk_text, query)

        # Extract key points
        key_points = self._extract_key_points(chunk_text, query, max_points=self.config.max_key_points)

        # Calculate relevance score
        relevance_score = self._calculate_relevance_score(chunk_text, query, summary_text)

        # Create summary object
        chunk_summary = ChunkSummary(
            chunk_id=chunk_id,
            original_text=chunk_text,
            summary=summary_text,
            relevance_score=relevance_score,
            query=query,
            key_points=key_points,
            confidence=confidence,
        )

        # Cache the summary
        self._save_cached_summary(
            cache_key,
            {
                "summary": summary_text,
                "relevance_score": relevance_score,
                "key_points": key_points,
                "confidence": confidence,
            },
        )

        return chunk_summary

    def _extract_key_sentences(self, text: str, query: str) -> str:
        """Fallback: extract key sentences containing query terms."""
        import re

        sentences = re.split(r"[.!?]+", text)
        query_terms = query.lower().split()

        # Score sentences by query term matches
        scored_sentences = []
        for sentence in sentences:
            sentence_lower = sentence.lower()
            score = sum(1 for term in query_terms if term in sentence_lower)
            if score > 0:
                scored_sentences.append((score, sentence.strip()))

        # Return top 3-5 sentences
        scored_sentences.sort(reverse=True)
        selected = [s[1] for s in scored_sentences[:5] if s[0] > 0]

        if selected:
            return " ".join(selected)
        return text[:500]  # Fallback to first 500 chars

    def _extract_key_points(self, text: str, query: str, max_points: int = 5) -> List[str]:
        """Extract key points from text relevant to query."""
        import re

        query_terms = query.lower().split()
        sentences = re.split(r"[.!?]+", text)

        key_points = []
        for sentence in sentences:
            sentence_lower = sentence.lower()
            # Check if sentence contains query terms
            if any(term in sentence_lower for term in query_terms):
                cleaned = sentence.strip()
                if len(cleaned) > 20 and len(cleaned) < 200:  # Reasonable length
                    key_points.append(cleaned)
                    if len(key_points) >= max_points:
                        break

        return key_points

    def _calculate_relevance_score(self, text: str, query: str, summary: str) -> float:
        """
        Calculate relevance score of chunk to query.

        Returns score between 0.0 and 1.0.
        """
        import re

        text_lower = text.lower()
        query_lower = query.lower()
        summary_lower = summary.lower()

        query_terms = set(re.findall(r"\b\w+\b", query_lower))

        # Count query term matches in text
        text_matches = sum(1 for term in query_terms if term in text_lower)
        summary_matches = sum(1 for term in query_terms if term in summary_lower)

        # Base score from term matches
        term_score = min(1.0, (text_matches + summary_matches * 2) / (len(query_terms) * 3))

        # Boost if summary is meaningful (not just fallback)
        if len(summary) > 50 and summary != text[:500]:
            term_score = min(1.0, term_score * 1.2)

        # Penalize if text is too short or too long
        length_penalty = 1.0
        if len(text) < 100:
            length_penalty = 0.7
        elif len(text) > 5000:
            length_penalty = 0.9

        return min(1.0, term_score * length_penalty)

    async def summarize_chunks(
        self, chunks: List[Text], query: str, summary_length: Optional[str] = None
    ) -> List[ChunkSummary]:
        """
        Summarize multiple chunks in parallel.

        Args:
            chunks: List of text chunks
            query: Query/field being extracted
            summary_length: Override config summary_length

        Returns:
            List of ChunkSummary objects
        """
        import asyncio

        # Summarize chunks in parallel (with limit to avoid overwhelming API)
        tasks = [self.summarize_chunk(chunk, query, summary_length) for chunk in chunks]

        # Process in batches to avoid rate limits
        batch_size = 5
        summaries = []
        for i in range(0, len(tasks), batch_size):
            batch = tasks[i : i + batch_size]
            batch_results = await asyncio.gather(*batch, return_exceptions=True)

            for result in batch_results:
                if isinstance(result, Exception):
                    logger.error(f"Summary generation failed: {result}")
                    # Create empty summary as fallback
                    chunk = chunks[tasks.index(batch[batch_results.index(result)])]
                    summaries.append(
                        ChunkSummary(
                            chunk_id=getattr(chunk, "name", "unknown"),
                            original_text=chunk.text if hasattr(chunk, "text") else str(chunk),
                            summary="",
                            relevance_score=0.0,
                            query=query,
                            key_points=[],
                            confidence=0.0,
                        )
                    )
                else:
                    if isinstance(result, ChunkSummary):
                        summaries.append(result)

        return summaries
