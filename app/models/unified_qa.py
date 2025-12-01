# app/models/unified_qa.py
import logging
import os
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
                    # Use Paper-QA agent (preferred)
                    self.qa_system = PaperQAAgent(api_key=api_key_candidate)
                    logger.info("UnifiedQA: PaperQAAgent initialized successfully.")
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
            return await self.qa_system.chat(prompt)
        except Exception as e:
            logger.error(f"UnifiedQA.chat error: {e}")
            return {"text": f"Error: {e}", "confidence": 0.0}

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
            Image description/analysis text
        """
        try:
            if PAPERQA_AVAILABLE and isinstance(self.qa_system, PaperQAAgent):
                # Use Paper-QA's litellm integration
                import litellm
                
                model_name = model or "gemini/gemini-2.0-flash"
                
                response = await litellm.acompletion(
                    model=model_name,
                    messages=[
                        {
                            "role": "user",
                            "content": [
                                {"type": "text", "text": prompt},
                                {"type": "image_url", "image_url": {"url": image_url}}
                            ]
                        }
                    ]
                )
                
                return response.choices[0].message.content
            else:
                # Use GeminiQA with vision model
                import google.generativeai as genai
                from PIL import Image
                import requests
                from io import BytesIO
                import base64
                
                # Handle data URLs
                if image_url.startswith('data:'):
                    # Extract base64 data
                    header, data = image_url.split(',', 1)
                    image_data = base64.b64decode(data)
                    image = Image.open(BytesIO(image_data))
                else:
                    # Download image
                    response = requests.get(image_url)
                    image = Image.open(BytesIO(response.content))
                
                # Use Gemini vision model
                vision_model = genai.GenerativeModel('gemini-2.0-flash')
                response = vision_model.generate_content([prompt, image])
                
                return response.text
                
        except Exception as e:
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
