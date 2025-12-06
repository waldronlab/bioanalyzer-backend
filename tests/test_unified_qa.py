import os

import pytest

from app.models.unified_qa import UnifiedQA


@pytest.mark.asyncio
async def test_unified_qa_chat_without_gemini_key(monkeypatch):
    """
    UnifiedQA should not raise when GEMINI_API_KEY is missing and should
    return a clear, non-crashing message from chat().
    """
    # Ensure GEMINI_API_KEY is not present in the environment for this test
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)

    qa = UnifiedQA(use_gemini=True, gemini_api_key=None, use_paperqa=False)
    resp = await qa.chat("Hello")

    assert isinstance(resp, dict)
    assert "text" in resp
    assert "confidence" in resp
    assert "Model not available" in resp["text"]
    assert resp["confidence"] == 0.0


@pytest.mark.asyncio
async def test_analyze_image_without_gemini_key(monkeypatch):
    """
    analyze_image should short-circuit with an informative message when
    GEMINI_API_KEY is not configured, rather than attempting network calls.
    """
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)

    qa = UnifiedQA(use_gemini=True, gemini_api_key=None, use_paperqa=False)
    result = await qa.analyze_image("http://example.com/image.png", "Describe")

    assert isinstance(result, str)
    assert "Image analysis is unavailable because GEMINI_API_KEY is not configured" in result


