"""LLM provider abstraction layer using LiteLLM for multiple providers."""

import os
import logging
from typing import Optional, Dict, List, Any
from enum import Enum
from app.utils.credential_masking import mask_exception_message, mask_string

logger = logging.getLogger(__name__)

try:
    import litellm

    LITELLM_AVAILABLE = True
except ImportError:
    LITELLM_AVAILABLE = False
    litellm = None
    logger.warning("LiteLLM not available. Install with: pip install litellm")


class LLMProvider(str, Enum):
    """Supported LLM providers."""

    OPENAI = "openai"
    ANTHROPIC = "anthropic"
    GEMINI = "gemini"
    OLLAMA = "ollama"
    LLAMAFILE = "llamafile"


class LLMProviderManager:
    """Manages LLM provider configuration and provides unified interface."""

    DEFAULT_MODELS = {
        LLMProvider.OPENAI: "gpt-4o",
        LLMProvider.ANTHROPIC: "claude-3-5-sonnet-20241022",
        LLMProvider.GEMINI: "gemini/gemini-2.0-flash",
        LLMProvider.OLLAMA: "ollama/llama3",
        LLMProvider.LLAMAFILE: "llamafile/llama-3.2-3b",
    }

    REQUIRED_ENV_VARS = {
        LLMProvider.OPENAI: ["OPENAI_API_KEY"],
        LLMProvider.ANTHROPIC: ["ANTHROPIC_API_KEY"],
        LLMProvider.GEMINI: ["GEMINI_API_KEY"],
        LLMProvider.OLLAMA: [],  # No API key needed for local Ollama
        LLMProvider.LLAMAFILE: [],  # No API key needed for local llamafile
    }

    def __init__(self, provider: Optional[str] = None, model: Optional[str] = None):
        """Initialize LLM provider manager."""
        if not LITELLM_AVAILABLE:
            raise ImportError(
                "LiteLLM is not installed. Install with: pip install litellm"
            )

        if provider is None:
            provider = self._detect_provider()

        try:
            self.provider = LLMProvider(provider.lower())
        except ValueError:
            raise ValueError(
                f"Unknown provider: {provider}. Supported providers: {[p.value for p in LLMProvider]}"
            )

        self.model = model or self.DEFAULT_MODELS.get(self.provider, "gpt-4o")

        # Automatically prefix Gemini and Ollama models if the prefix is missing
        if self.provider == LLMProvider.GEMINI and not self.model.startswith("gemini/"):
            self.model = f"gemini/{self.model}"
        elif self.provider == LLMProvider.OLLAMA and not self.model.startswith(
            "ollama/"
        ):
            self.model = f"ollama/{self.model}"

        self._validate_provider_config()
        self._configure_litellm()

        logger.info(
            f"LLMProviderManager initialized: provider={self.provider.value}, model={self.model}"
        )

    def _detect_provider(self) -> str:
        """Detect provider from environment variables."""
        # Check in order of preference
        if os.getenv("OPENAI_API_KEY"):
            return LLMProvider.OPENAI.value
        elif os.getenv("ANTHROPIC_API_KEY"):
            return LLMProvider.ANTHROPIC.value
        elif os.getenv("GEMINI_API_KEY"):
            return LLMProvider.GEMINI.value
        elif os.getenv("OLLAMA_BASE_URL") or os.getenv("OLLAMA_HOST"):
            return LLMProvider.OLLAMA.value
        else:
            # Default to Gemini if available, otherwise OpenAI
            if os.getenv("GEMINI_API_KEY"):
                return LLMProvider.GEMINI.value
            return LLMProvider.OPENAI.value

    def _validate_provider_config(self):
        """Validate that required environment variables are set."""
        required_vars = self.REQUIRED_ENV_VARS.get(self.provider, [])
        missing_vars = []

        for var in required_vars:
            if not os.getenv(var):
                missing_vars.append(var)

        if missing_vars:
            logger.warning(
                f"Provider {self.provider.value} requires environment variables: {missing_vars}. "
                f"Some features may not work."
            )

    def _configure_litellm(self):
        """Configure LiteLLM with provider-specific settings."""
        # Set API keys in environment for LiteLLM
        if self.provider == LLMProvider.OPENAI:
            if os.getenv("OPENAI_API_KEY"):
                os.environ["OPENAI_API_KEY"] = os.getenv("OPENAI_API_KEY")
        elif self.provider == LLMProvider.ANTHROPIC:
            if os.getenv("ANTHROPIC_API_KEY"):
                os.environ["ANTHROPIC_API_KEY"] = os.getenv("ANTHROPIC_API_KEY")
        elif self.provider == LLMProvider.GEMINI:
            if os.getenv("GEMINI_API_KEY"):
                os.environ["GEMINI_API_KEY"] = os.getenv("GEMINI_API_KEY")
        elif self.provider == LLMProvider.OLLAMA:
            # Configure Ollama base URL if provided
            ollama_base = os.getenv("OLLAMA_BASE_URL") or os.getenv(
                "OLLAMA_HOST", "http://localhost:11434"
            )
            os.environ["OLLAMA_BASE_URL"] = ollama_base

        # Configure LiteLLM settings
        litellm.set_verbose = os.getenv("LITELLM_VERBOSE", "false").lower() == "true"

    async def chat(
        self,
        messages: List[Dict[str, str]],
        temperature: float = 0.7,
        max_tokens: Optional[int] = None,
        timeout: float = 60.0,
    ) -> Dict[str, Any]:
        """
        Send a chat completion request using LiteLLM.

        Args:
            messages: List of message dicts with 'role' and 'content' keys
            temperature: Sampling temperature (0.0 to 2.0)
            max_tokens: Maximum tokens to generate
            timeout: Request timeout in seconds

        Returns:
            Response dict with 'text' and 'confidence' keys
        """
        import asyncio

        try:
            response = await asyncio.wait_for(
                litellm.acompletion(
                    model=self.model,
                    messages=messages,
                    temperature=temperature,
                    max_tokens=max_tokens,
                ),
                timeout=timeout,
            )

            # Extract text from response
            text = response.choices[0].message.content if response.choices else ""

            # Estimate confidence (higher for longer, more complete responses)
            confidence = min(1.0, 0.5 + (len(text) / 1000) * 0.1)

            return {
                "text": text,
                "confidence": confidence,
                "model": self.model,
                "provider": self.provider.value,
            }
        except asyncio.TimeoutError:
            logger.error(f"LLM request timed out after {timeout}s")
            return {
                "text": f"Request timed out after {timeout} seconds",
                "confidence": 0.0,
                "error": "timeout",
            }
        except Exception as e:
            # Mask any credentials in error message
            safe_error = mask_exception_message(e)
            logger.error(f"LLM request failed: {safe_error}")
            return {
                "text": f"Error: {safe_error}",
                "confidence": 0.0,
                "error": safe_error,
            }

    async def analyze_image(
        self,
        image_url: str,
        prompt: str,
        timeout: float = 60.0,
    ) -> str:
        """
        Analyze an image using vision-capable models.

        Args:
            image_url: Image URL (data URL or HTTP URL)
            prompt: Text prompt for image analysis
            timeout: Request timeout in seconds

        Returns:
            Image description/analysis text
        """
        import asyncio

        # Check if model supports vision
        vision_models = [
            "gpt-4o",
            "gpt-4-vision",
            "claude-3-opus",
            "claude-3-sonnet",
            "claude-3-5-sonnet",
            "gemini/gemini-2.0-flash",
            "gemini/gemini-pro-vision",
        ]

        if not any(model in self.model for model in vision_models):
            return f"Model {self.model} does not support image analysis. Use a vision-capable model."

        try:
            response = await asyncio.wait_for(
                litellm.acompletion(
                    model=self.model,
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
                timeout=timeout,
            )

            return response.choices[0].message.content if response.choices else ""
        except asyncio.TimeoutError:
            logger.error(f"Image analysis timed out after {timeout}s")
            return "Image analysis timed out."
        except Exception as e:
            # Mask any credentials in error message
            safe_error = mask_exception_message(e)
            logger.error(f"Image analysis failed: {safe_error}")
            return f"Error analyzing image: {safe_error}"

    @staticmethod
    def get_available_providers() -> List[str]:
        """Get list of available providers based on environment variables."""
        available = []

        if os.getenv("OPENAI_API_KEY"):
            available.append(LLMProvider.OPENAI.value)
        if os.getenv("ANTHROPIC_API_KEY"):
            available.append(LLMProvider.ANTHROPIC.value)
        if os.getenv("GEMINI_API_KEY"):
            available.append(LLMProvider.GEMINI.value)
        if os.getenv("OLLAMA_BASE_URL") or os.getenv("OLLAMA_HOST"):
            available.append(LLMProvider.OLLAMA.value)
        # llamafile is always available if installed locally

        return available

    @staticmethod
    def get_supported_models(provider: str) -> List[str]:
        """Get list of supported models for a provider."""
        models = {
            LLMProvider.OPENAI.value: [
                "gpt-4o",
                "gpt-4o-mini",
                "gpt-4-turbo",
                "gpt-4",
                "gpt-3.5-turbo",
            ],
            LLMProvider.ANTHROPIC.value: [
                "claude-3-5-sonnet-20241022",
                "claude-3-opus-20240229",
                "claude-3-sonnet-20240229",
                "claude-3-haiku-20240307",
            ],
            LLMProvider.GEMINI.value: [
                "gemini/gemini-2.0-flash",
                "gemini/gemini-1.5-pro",
                "gemini/gemini-1.5-flash",
            ],
            LLMProvider.OLLAMA.value: [
                "ollama/llama3",
                "ollama/llama3.1",
                "ollama/mistral",
                "ollama/codellama",
            ],
            LLMProvider.LLAMAFILE.value: [
                "llamafile/llama-3.2-3b",
                "llamafile/llama-3.1-8b",
            ],
        }
        return models.get(provider.lower(), [])
