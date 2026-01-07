# app/models/unified_qa.py
import logging
import os
import asyncio
from typing import Dict, List, Optional, Union

from app.utils.config import GEMINI_API_KEY, GEMINI_TIMEOUT, LLM_MODEL, LLM_PROVIDER
from app.utils.credential_masking import mask_exception_message

# Try to import LiteLLM provider manager first
try:
    from .llm_provider import LLMProviderManager, LITELLM_AVAILABLE
except ImportError:
    LITELLM_AVAILABLE = False
    LLMProviderManager = None

# Try to import Paper-QA first, fallback to GeminiQA if not available
try:
    from .paperqa_agent import PaperQAAgent

    PAPERQA_AVAILABLE = True
except ImportError:
    PAPERQA_AVAILABLE = False

logger = logging.getLogger(__name__)
if not PAPERQA_AVAILABLE:
    logger.warning("Paper-QA not available, falling back to GeminiQA")


class UnifiedQA:
    """Wrapper around LLM providers for question answering.

    Tries LiteLLM first (supports multiple providers), falls back to Paper-QA,
    then GeminiQA if those fail. Auto-detects provider from available API keys.
    """

    def __init__(
        self,
        provider: Optional[str] = None,
        model: Optional[str] = None,
        use_gemini: Optional[bool] = None,
        gemini_api_key: Optional[str] = None,
        use_paperqa: bool = True,
    ):
        """Set up QA system with the specified provider.

        Args:
            provider: LLM provider (gemini, openai, anthropic, ollama). Auto-detects if None.
            model: Specific model name. Uses provider default if None.
            use_gemini: Deprecated. Use provider='gemini' instead.
            gemini_api_key: Override GEMINI_API_KEY env var.
            use_paperqa: Try Paper-QA as fallback (default: True).
        """
        if use_gemini is not None:
            logger.warning(
                "use_gemini parameter is deprecated. Use provider='gemini' instead."
            )
            if use_gemini and provider is None:
                provider = "gemini"

        if provider is None:
            provider = LLM_PROVIDER

        if model is None:
            model = LLM_MODEL

        self.provider = provider
        self.model = model
        self.use_paperqa = bool(use_paperqa) and PAPERQA_AVAILABLE

        self.llm_manager = None
        if LITELLM_AVAILABLE and LLMProviderManager:
            try:
                self.llm_manager = LLMProviderManager(provider=provider, model=model)
                logger.info(
                    f"UnifiedQA: Using LiteLLM with provider={self.llm_manager.provider.value}, model={self.llm_manager.model}"
                )
            except Exception as e:
                logger.warning(f"UnifiedQA: Failed to initialize LiteLLM: {e}")
                self.llm_manager = None

        if self.llm_manager is None:
            api_key_candidate = None
            if (
                gemini_api_key
                and isinstance(gemini_api_key, str)
                and gemini_api_key.strip()
            ):
                api_key_candidate = gemini_api_key.strip()
            else:
                env_key = os.getenv("GEMINI_API_KEY", "")
                if env_key and env_key.strip():
                    api_key_candidate = env_key.strip()

            if api_key_candidate:
                try:
                    if self.use_paperqa:
                        try:
                            self.qa_system = PaperQAAgent(api_key=api_key_candidate)
                            logger.info(
                                "UnifiedQA: PaperQAAgent initialized successfully (fallback)."
                            )
                        except Exception as paperqa_error:
                            logger.warning(
                                f"UnifiedQA: Paper-QA initialization failed: {paperqa_error}"
                            )
                            logger.info(
                                "UnifiedQA: Falling back to GeminiQA due to Paper-QA issues"
                            )
                            from .gemini_qa import GeminiQA

                            self.qa_system = GeminiQA(api_key=api_key_candidate)
                            self.use_paperqa = False
                            logger.info(
                                "UnifiedQA: GeminiQA initialized successfully (Paper-QA unavailable)."
                            )
                    else:
                        from .gemini_qa import GeminiQA

                        self.qa_system = GeminiQA(api_key=api_key_candidate)
                        logger.info(
                            "UnifiedQA: GeminiQA initialized successfully (Paper-QA not used)."
                        )
                except Exception as e:
                    self.qa_system = None
                    logger.error(f"UnifiedQA: failed to initialize QA system: {e}")
                    if self.use_paperqa:
                        try:
                            from .gemini_qa import GeminiQA

                            self.qa_system = GeminiQA(api_key=api_key_candidate)
                            self.use_paperqa = False
                            logger.info(
                                "UnifiedQA: Fallback to GeminiQA after Paper-QA failure."
                            )
                        except Exception as e2:
                            logger.error(
                                f"UnifiedQA: Fallback to GeminiQA also failed: {e2}"
                            )
        else:
            self.qa_system = None
            logger.warning(
                "UnifiedQA: QA system not initialized (no API keys). Chat functionality will be limited."
            )

    async def chat(self, prompt: str) -> dict:
        """Chat with the QA system. Returns dict with 'text' and 'confidence' keys."""
        if self.llm_manager:
            try:
                response = await self.llm_manager.chat(
                    messages=[{"role": "user", "content": prompt}],
                    timeout=GEMINI_TIMEOUT,
                )
                return response
            except Exception as e:
                safe_error = mask_exception_message(e)
                logger.error(f"UnifiedQA.chat (LiteLLM) error: {safe_error}")

        if not self.qa_system:
            return {
                "text": "Model not available. Check API keys or LLM_PROVIDER config.",
                "confidence": 0.0,
            }
        try:
            response = await self.qa_system.chat(prompt)
            if (
                response.get("text", "").startswith("Error:")
                or "router" in str(response.get("text", "")).lower()
            ):
                logger.warning(
                    f"Paper-QA returned error, falling back to GeminiQA: {response.get('text')}"
                )
                return await self._fallback_to_gemini(prompt)
            return response
        except Exception as e:
            safe_error = mask_exception_message(e)
            logger.error(f"UnifiedQA.chat error: {safe_error}")
            logger.info("Attempting fallback to GeminiQA after error")
            return await self._fallback_to_gemini(prompt)

    async def _fallback_to_gemini(self, prompt: str) -> dict:
        """Fallback to Gemini API when Paper-QA fails."""
        try:
            from .gemini_qa import GeminiQA

            api_key = os.getenv("GEMINI_API_KEY", "")
            if not api_key:
                return {
                    "text": "GEMINI_API_KEY not available for fallback",
                    "confidence": 0.0,
                }

            gemini_qa = GeminiQA(api_key=api_key)
            response = await gemini_qa.chat(prompt)
            logger.info("Fallback to GeminiQA successful")
            return response
        except Exception as e:
            safe_error = mask_exception_message(e)
            logger.error(f"Fallback to GeminiQA also failed: {safe_error}")
            return {
                "text": f"Error: All QA systems failed. Last error: {safe_error}",
                "confidence": 0.0,
            }

    async def ask_question(
        self, question: str, context: Optional[str] = None, pmid: Optional[str] = None
    ) -> Dict:
        """Ask a question with optional context. Returns {'answer': str, 'confidence': float}."""
        if self.llm_manager:
            try:
                prompt = question
                if context:
                    prompt = f"Context: {context[:2000]}\n\nQuestion: {question}"

                resp = await self.llm_manager.chat(
                    messages=[{"role": "user", "content": prompt}],
                    timeout=GEMINI_TIMEOUT,
                )
                text = resp.get("text") or ""
                confidence = float(resp.get("confidence", 0.0) or 0.0)
                return {"answer": text, "confidence": confidence, "pmid": pmid}
            except Exception as e:
                logger.error(f"UnifiedQA.ask_question (LiteLLM) error: {e}")

        if not self.qa_system:
            return {
                "answer": "Model not available. Check API keys or LLM_PROVIDER config.",
                "confidence": 0.0,
                "pmid": pmid,
            }

        if self.use_paperqa and hasattr(self.qa_system, "ask_question"):
            try:
                return await self.qa_system.ask_question(question, context, pmid)
            except Exception as e:
                logger.error(f"UnifiedQA.ask_question (PaperQA) error: {e}")

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
            return {
                "error": "QA system not available",
                "confidence": 0.0,
                "status": "error",
            }
        try:
            return await self.qa_system.analyze_paper(paper_content)
        except Exception as e:
            logger.error(f"UnifiedQA.analyze_paper error: {e}")
            return {"error": str(e), "confidence": 0.0, "status": "error"}

    async def analyze_image(
        self, image_url: str, prompt: str, model: Optional[str] = None
    ) -> str:
        """Analyze an image using visual LLM capabilities."""
        if self.llm_manager:
            try:
                if model:
                    original_model = self.llm_manager.model
                    self.llm_manager.model = model

                result = await self.llm_manager.analyze_image(
                    image_url=image_url,
                    prompt=prompt,
                    timeout=GEMINI_TIMEOUT,
                )

                if model:
                    self.llm_manager.model = original_model

                return result
            except Exception as e:
                logger.error(f"UnifiedQA.analyze_image (LiteLLM) error: {e}")

        if not GEMINI_API_KEY and not self.llm_manager:
            logger.warning("Image analysis requested but no API keys are configured.")
            return (
                "Image analysis is unavailable because no API keys are configured. "
                "Set LLM_PROVIDER and appropriate API keys in your environment or .env to enable visual analysis."
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
                                        {
                                            "type": "image_url",
                                            "image_url": {"url": image_url},
                                        },
                                    ],
                                }
                            ],
                        ),
                        timeout=GEMINI_TIMEOUT,
                    )
                except asyncio.TimeoutError:
                    logger.error(
                        "Image analysis via Paper-QA timed out after %ss",
                        GEMINI_TIMEOUT,
                    )
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
                return await asyncio.to_thread(
                    vision_model.generate_content, [prompt, image]
                )

            try:
                response = await asyncio.wait_for(_generate(), timeout=GEMINI_TIMEOUT)
            except asyncio.TimeoutError:
                logger.error(
                    "Image analysis via Gemini vision model timed out after %ss",
                    GEMINI_TIMEOUT,
                )
                return "Image analysis timed out while calling the Gemini vision model."

            return (
                getattr(response, "text", "")
                or "No description was generated for this image."
            )

        except Exception as e:  # pragma: no cover - last-resort guard
            logger.error(f"Error analyzing image: {e}")
            return f"Error analyzing image: {str(e)}"

    async def analyze_paper_enhanced(
        self, prompt: str
    ) -> Dict[str, Union[str, float, List[str]]]:
        """Enhanced analysis method for BugSigDB curation requirements."""
        if self.use_gemini and self.qa_system:
            return await self.qa_system.analyze_paper_enhanced(prompt)
        else:
            return {
                "error": "No enhanced analysis available",
                "key_findings": "{}",
                "confidence": 0.0,
            }
