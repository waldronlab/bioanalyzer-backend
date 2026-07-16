import pytest

from app.models.llm_provider import LLMProviderManager


@pytest.fixture(autouse=True)
def _fake_gemini_key(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "test-key")


class TestGeminiModelPrefixNormalization:
    """Regression tests for a real production bug found via
    docs/BUGSIGDB_ACCURACY_BENCHMARK.md: app.utils.config.DEFAULT_MODEL is
    shared between GeminiQA (Google's native genai SDK, expects
    "models/gemini-x.y") and this LiteLLM-based manager (expects
    "gemini/gemini-x.y"). Naively prepending "gemini/" to an
    already-"models/"-prefixed value produced "gemini/models/gemini-x.y",
    which LiteLLM can't resolve - every LLM call failed with
    litellm.NotFoundError and silently fell back to the much weaker regex
    heuristic extractor, for ~98% of calls in a live benchmark run."""

    def test_strips_models_prefix_before_adding_gemini_prefix(self):
        mgr = LLMProviderManager(provider="gemini", model="models/gemini-2.5-flash")
        assert mgr.model == "gemini/gemini-2.5-flash"

    def test_leaves_already_correct_gemini_prefix_untouched(self):
        mgr = LLMProviderManager(provider="gemini", model="gemini/gemini-2.0-flash")
        assert mgr.model == "gemini/gemini-2.0-flash"

    def test_bare_model_name_gets_gemini_prefix(self):
        mgr = LLMProviderManager(provider="gemini", model="gemini-2.0-flash")
        assert mgr.model == "gemini/gemini-2.0-flash"

    def test_default_model_is_used_when_none_given(self):
        mgr = LLMProviderManager(provider="gemini", model=None)
        assert mgr.model == "gemini/gemini-2.0-flash"
