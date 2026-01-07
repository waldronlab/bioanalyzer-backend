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
    # When API key is missing, LiteLLM will attempt the request and return an error
    # The response should contain either "Model not available" or an error message
    assert "Model not available" in resp["text"] or "Error:" in resp["text"] or "API key" in resp["text"]
    assert resp["confidence"] == 0.0


@pytest.mark.asyncio
async def test_analyze_image_without_gemini_key(monkeypatch):
    """
    analyze_image should handle missing GEMINI_API_KEY gracefully.
    When the API key is missing, LiteLLM will attempt the request and may fail
    with various error messages (authentication error, image fetch error, etc.).
    """
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)

    qa = UnifiedQA(use_gemini=True, gemini_api_key=None, use_paperqa=False)
    result = await qa.analyze_image("http://example.com/image.png", "Describe")

    assert isinstance(result, str)
    # When API key is missing or image URL is invalid, various error messages are possible
    # Check for any of the expected error indicators
    assert (
        "Image analysis is unavailable because GEMINI_API_KEY is not configured" in result
        or "Error" in result
        or "API key" in result
        or "Unable to fetch image" in result
    )
