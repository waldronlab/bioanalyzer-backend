"""UnifiedQA.chat must forward the configured temperature and the caller's
json_mode to whichever backend answers, and must not pass json_mode to a
backend (Paper-QA, test doubles) whose chat() doesn't accept it."""

from unittest.mock import AsyncMock, MagicMock

import pytest

from app.models import unified_qa as unified_qa_module
from app.models.unified_qa import UnifiedQA


@pytest.fixture
def qa(monkeypatch):
    """A UnifiedQA whose LiteLLM manager is a recorder."""
    monkeypatch.setenv("GEMINI_API_KEY", "test-key")
    instance = UnifiedQA(provider="gemini", use_paperqa=False)
    instance.llm_manager = MagicMock()
    instance.llm_manager.chat = AsyncMock(return_value={"text": "{}", "confidence": 1})
    instance.qa_system = None
    return instance


@pytest.mark.asyncio
async def test_chat_passes_configured_temperature_and_json_mode_off(qa, monkeypatch):
    monkeypatch.setattr(unified_qa_module, "LLM_TEMPERATURE", 0.0)
    await qa.chat("hello")
    kwargs = qa.llm_manager.chat.call_args.kwargs
    assert kwargs["temperature"] == 0.0
    assert kwargs["json_mode"] is False


@pytest.mark.asyncio
async def test_chat_forwards_json_mode(qa):
    await qa.chat("extract", json_mode=True)
    assert qa.llm_manager.chat.call_args.kwargs["json_mode"] is True


@pytest.mark.asyncio
async def test_chat_explicit_temperature_overrides_config(qa, monkeypatch):
    monkeypatch.setattr(unified_qa_module, "LLM_TEMPERATURE", 0.0)
    await qa.chat("brainstorm", temperature=0.9)
    assert qa.llm_manager.chat.call_args.kwargs["temperature"] == 0.9


@pytest.mark.asyncio
async def test_chat_with_only_passes_json_mode_when_accepted():
    class Accepts:
        async def chat(self, prompt, *, json_mode=False):
            return {"text": f"json_mode={json_mode}", "confidence": 1.0}

    class Legacy:
        async def chat(self, prompt):
            return {"text": "legacy", "confidence": 1.0}

    out = await UnifiedQA._chat_with(Accepts(), "p", json_mode=True)
    assert out["text"] == "json_mode=True"
    out = await UnifiedQA._chat_with(Legacy(), "p", json_mode=True)
    assert out["text"] == "legacy"


@pytest.mark.asyncio
async def test_fallback_to_gemini_forwards_json_mode(qa, monkeypatch):
    recorded = {}

    class FakeGeminiQA:
        def __init__(self, api_key=None):
            recorded["api_key"] = api_key

        async def chat(self, prompt, *, json_mode=False):
            recorded["json_mode"] = json_mode
            return {"text": "{}", "confidence": 1.0}

    monkeypatch.setenv("GEMINI_API_KEY", "test-key")
    monkeypatch.setattr("app.models.gemini_qa.GeminiQA", FakeGeminiQA)

    out = await qa._fallback_to_gemini("p", json_mode=True)
    assert out["text"] == "{}"
    assert recorded["json_mode"] is True
