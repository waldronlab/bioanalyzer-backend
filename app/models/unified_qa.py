# app/models/unified_qa.py
import logging
import os
from typing import Dict, List, Optional, Union

from .gemini_qa import GeminiQA

logger = logging.getLogger(__name__)


class UnifiedQA:
    """Unified QA system that wraps an external model interface for conversational interactions."""

    def __init__(self, use_gemini: bool = True, gemini_api_key: Optional[str] = None):
        """
        Initialize the unified QA system.

        Behavior:
        - If gemini_api_key provided (non-empty), use it.
        - Else fall back to environment variable GEMINI_API_KEY.
        - If neither present and use_gemini=True, log a warning but keep the wrapper available.
        """
        self.use_gemini = bool(use_gemini)

        # Prefer explicit param, otherwise environment variable
        api_key_candidate = None
        if gemini_api_key and isinstance(gemini_api_key, str) and gemini_api_key.strip():
            api_key_candidate = gemini_api_key.strip()
        else:
            env_key = os.getenv("GEMINI_API_KEY", "")
            if env_key and env_key.strip():
                api_key_candidate = env_key.strip()

        if self.use_gemini and api_key_candidate:
            try:
                self.qa_system = GeminiQA(api_key=api_key_candidate)
                logger.info("UnifiedQA: GeminiQA initialized successfully.")
            except Exception as e:
                self.qa_system = None
                logger.error(f"UnifiedQA: failed to initialize GeminiQA: {e}")
        else:
            self.qa_system = None
            logger.warning(
                "UnifiedQA: GeminiQA not initialized. "
                f"use_gemini={self.use_gemini}, api_key_provided={bool(api_key_candidate)}. "
                "Chat functionality will be limited."
            )

    async def chat(self, prompt: str) -> dict:
        """
        Chat with the QA system (generic conversational).
        Returns a dict with 'text' and 'confidence' keys to match downstream expectations.
        """
        if not self.qa_system:
            return {"text": "Model not available. Check GEMINI_API_KEY.", "confidence": 0.0}
        try:
            return await self.qa_system.chat(prompt)
        except Exception as e:
            logger.error(f"UnifiedQA.chat error: {e}")
            return {"text": f"Error: {e}", "confidence": 0.0}

    async def ask_question(self, question: str, context: Optional[str] = None, pmid: Optional[str] = None) -> Dict:
        """
        Adapter used by paper_analysis.py and other routers.
        Ensures a common response shape: {'answer': str, 'confidence': float}
        """
        prompt = question
        if context:
            prompt = f"Context: {context[:2000]}\n\nQuestion: {question}"

        # Use chat() under the hood; normalized output
        try:
            resp = await self.chat(prompt)
            text = resp.get("text") or resp.get("answer") or ""
            confidence = float(resp.get("confidence", 0.0) or 0.0)
            return {"answer": text, "confidence": confidence, "pmid": pmid}
        except Exception as e:
            logger.error(f"UnifiedQA.ask_question error: {e}")
            return {"answer": "", "confidence": 0.0, "error": str(e), "pmid": pmid}

    async def analyze_paper(self, paper_content: Dict[str, str]) -> dict:
        """Analyze a paper using the QA system."""
        if not self.qa_system:
            return {"error": "QA system not available", "confidence": 0.0, "status": "error"}
        try:
            return await self.qa_system.analyze_paper(paper_content)
        except Exception as e:
            logger.error(f"UnifiedQA.analyze_paper error: {e}")
            return {"error": str(e), "confidence": 0.0, "status": "error"}

    async def analyze_paper_enhanced(self, prompt: str) -> Dict[str, Union[str, float, List[str]]]:
        """Enhanced analysis method for BugSigDB curation requirements."""
        if self.use_gemini and self.qa_system:
            return await self.qa_system.analyze_paper_enhanced(prompt)
        else:
            return {
                "error": "No enhanced analysis available",
                "key_findings": "{}",
                "confidence": 0.0
            }
