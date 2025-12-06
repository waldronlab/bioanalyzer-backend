# app/models/unified_qa.py
import logging
import os
import asyncio
from typing import Dict, List, Optional, Union

# Try to import Paper-QA first, fallback to GeminiQA if not available
try:
    from .paperqa_agent import PaperQAAgent
    PAPERQA_AVAILABLE = True
except ImportError:
    PAPERQA_AVAILABLE = False
    logger = logging.getLogger(__name__)
    logger.warning("Paper-QA not available, falling back to GeminiQA")
    from .gemini_qa import GeminiQA

from app.utils.config import GEMINI_TIMEOUT, GEMINI_API_KEY

logger = logging.getLogger(__name__)


class UnifiedQA:
    """
    Unified QA system that wraps Paper-QA agent (preferred) or GeminiQA (fallback).
    
    Paper-QA is preferred because it:
    - Supports multiple LLMs including Gemini
    - Provides agent-based reasoning
    - Offers better paper analysis capabilities
    """

    def __init__(
        self, 
        use_gemini: bool = True, 
        gemini_api_key: Optional[str] = None,
        use_paperqa: bool = True
    ):
        """
        Initialize the unified QA system.

        Args:
            use_gemini: Whether to use Gemini (via Paper-QA or direct API)
            gemini_api_key: API key for Gemini
            use_paperqa: Whether to use Paper-QA agent (default: True)
                          If False or Paper-QA unavailable, falls back to GeminiQA

        Behavior:
        - If use_paperqa=True and Paper-QA is available, use PaperQAAgent
        - Otherwise, fall back to GeminiQA (direct API calls)
        - If gemini_api_key provided (non-empty), use it.
        - Else fall back to environment variable GEMINI_API_KEY.
        """
        self.use_gemini = bool(use_gemini)
        self.use_paperqa = bool(use_paperqa) and PAPERQA_AVAILABLE

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
                if self.use_paperqa:
                    # Try Paper-QA agent first (preferred)
                    try:
                        self.qa_system = PaperQAAgent(api_key=api_key_candidate)
                        # Test if Paper-QA actually works (some versions have compatibility issues)
                        logger.info("UnifiedQA: PaperQAAgent initialized successfully.")
                    except Exception as paperqa_error:
                        logger.warning(f"UnifiedQA: Paper-QA initialization failed: {paperqa_error}")
                        logger.info("UnifiedQA: Falling back to GeminiQA due to Paper-QA issues")
                        # Fallback to direct Gemini API
                        from .gemini_qa import GeminiQA
                        self.qa_system = GeminiQA(api_key=api_key_candidate)
                        self.use_paperqa = False  # Disable Paper-QA for this instance
                        logger.info("UnifiedQA: GeminiQA initialized successfully (Paper-QA unavailable).")
                else:
                    # Fallback to direct Gemini API
                    from .gemini_qa import GeminiQA
                    self.qa_system = GeminiQA(api_key=api_key_candidate)
                    logger.info("UnifiedQA: GeminiQA initialized successfully (Paper-QA not used).")
            except Exception as e:
                self.qa_system = None
                logger.error(f"UnifiedQA: failed to initialize QA system: {e}")
                # Try fallback if Paper-QA failed
                if self.use_paperqa:
                    try:
                        from .gemini_qa import GeminiQA
                        self.qa_system = GeminiQA(api_key=api_key_candidate)
                        self.use_paperqa = False  # Disable Paper-QA for this instance
                        logger.info("UnifiedQA: Fallback to GeminiQA after Paper-QA failure.")
                    except Exception as e2:
                        logger.error(f"UnifiedQA: Fallback to GeminiQA also failed: {e2}")
        else:
            self.qa_system = None
            logger.warning(
                "UnifiedQA: QA system not initialized. "
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
            response = await self.qa_system.chat(prompt)
            # Check if response indicates an error (Paper-QA failure)
            if response.get('text', '').startswith('Error:') or 'router' in str(response.get('text', '')).lower():
                logger.warning(f"Paper-QA returned error, falling back to GeminiQA: {response.get('text')}")
                # Fallback to direct Gemini API
                return await self._fallback_to_gemini(prompt)
            return response
        except Exception as e:
            logger.error(f"UnifiedQA.chat error: {e}")
            # Try fallback to GeminiQA
            logger.info("Attempting fallback to GeminiQA after error")
            return await self._fallback_to_gemini(prompt)
    
    async def _fallback_to_gemini(self, prompt: str) -> dict:
        """Fallback to direct Gemini API when Paper-QA fails."""
        try:
            from .gemini_qa import GeminiQA
            # Get API key from environment or use the one from initialization
            api_key = os.getenv("GEMINI_API_KEY", "")
            if not api_key:
                return {"text": "GEMINI_API_KEY not available for fallback", "confidence": 0.0}
            
            gemini_qa = GeminiQA(api_key=api_key)
            response = await gemini_qa.chat(prompt)
            logger.info("Fallback to GeminiQA successful")
            return response
        except Exception as e:
            logger.error(f"Fallback to GeminiQA also failed: {e}")
            return {"text": f"Error: All QA systems failed. Last error: {e}", "confidence": 0.0}

    async def ask_question(self, question: str, context: Optional[str] = None, pmid: Optional[str] = None) -> Dict:
        """
        Adapter used by paper_analysis.py and other routers.
        Ensures a common response shape: {'answer': str, 'confidence': float}
        """
        if not self.qa_system:
            return {"answer": "Model not available. Check GEMINI_API_KEY.", "confidence": 0.0, "pmid": pmid}
        
        # Use PaperQA's ask_question if available (more optimized for context+question)
        if self.use_paperqa and hasattr(self.qa_system, 'ask_question'):
            try:
                return await self.qa_system.ask_question(question, context, pmid)
            except Exception as e:
                logger.error(f"UnifiedQA.ask_question (PaperQA) error: {e}")
                # Fall through to generic chat method
        
        # Fallback to generic chat method
        prompt = question
        if context:
            prompt = f"Context: {context[:2000]}\n\nQuestion: {question}"

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

    async def analyze_image(
        self,
        image_url: str,
        prompt: str,
        model: Optional[str] = None
    ) -> str:
        """
        Analyze an image using visual LLM capabilities.
        
        Args:
            image_url: Image URL (data URL or HTTP URL)
            prompt: Text prompt for image analysis
            model: Optional model override (default: gemini-2.0-flash)
            
        Returns:
            Image description/analysis text, or an informative error string.
        """
        # Fast exit if Gemini is not configured – avoid hitting external APIs at all.
        if not GEMINI_API_KEY:
            logger.warning("Image analysis requested but GEMINI_API_KEY is not configured.")
            return (
                "Image analysis is unavailable because GEMINI_API_KEY is not configured. "
                "Set GEMINI_API_KEY in your environment or .env to enable visual analysis."
            )

        try:
            if PAPERQA_AVAILABLE and isinstance(self.qa_system, PaperQAAgent):
                # Use Paper-QA's litellm integration with an explicit timeout
                import litellm

                model_name = model or "gemini/gemini-2.0-flash"

                try:
                    response = await asyncio.wait_for(
                        litellm.acompletion(
                            model=model_name,
                            messages=[
                                {
                                    "role": "user",
                                    "content": [
                                        {"type": "text", "text": prompt},
                                        {"type": "image_url", "image_url": {"url": image_url}},
                                    ],
                                }
                            ],
                        ),
                        timeout=GEMINI_TIMEOUT,
                    )
                except asyncio.TimeoutError:
                    logger.error("Image analysis via Paper-QA timed out after %ss", GEMINI_TIMEOUT)
                    return "Image analysis timed out while calling the visual LLM."

                return response.choices[0].message.content

            # Fallback: direct Gemini vision model
            import google.generativeai as genai
            from PIL import Image
            import requests
            from io import BytesIO
            import base64

            # Configure Gemini client once with our API key
            try:
                genai.configure(api_key=GEMINI_API_KEY)
            except Exception as cfg_exc:  # pragma: no cover - defensive
                logger.error("Failed to configure Gemini client: %s", cfg_exc)
                return (
                    "Image analysis is unavailable because the Gemini client could not be configured. "
                    "Check GEMINI_API_KEY and network connectivity."
                )

            # Handle data URLs vs remote URLs
            if image_url.startswith("data:"):
                # Extract base64 data
                header, data = image_url.split(",", 1)
                image_data = base64.b64decode(data)
                image = Image.open(BytesIO(image_data))
            else:
                # Download image with a bounded timeout
                try:
                    response = requests.get(image_url, timeout=10)
                    response.raise_for_status()
                except Exception as req_exc:
                    logger.error("Error downloading image %s: %s", image_url, req_exc)
                    return (
                        "Unable to download image for analysis. "
                        "Check that the URL is reachable from the backend."
                    )
                image = Image.open(BytesIO(response.content))

            vision_model_name = model or "gemini-2.0-flash"
            vision_model = genai.GenerativeModel(vision_model_name)

            async def _generate():
                # Run the blocking generate_content call in a thread with an overall timeout
                return await asyncio.to_thread(vision_model.generate_content, [prompt, image])

            try:
                response = await asyncio.wait_for(_generate(), timeout=GEMINI_TIMEOUT)
            except asyncio.TimeoutError:
                logger.error(
                    "Image analysis via Gemini vision model timed out after %ss", GEMINI_TIMEOUT
                )
                return "Image analysis timed out while calling the Gemini vision model."

            return getattr(response, "text", "") or "No description was generated for this image."

        except Exception as e:  # pragma: no cover - last-resort guard
            logger.error(f"Error analyzing image: {e}")
            return f"Error analyzing image: {str(e)}"

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
