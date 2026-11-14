"""Determinism/JSON-mode plumbing for the LLM call path.

Background: the extraction prompt ran at LiteLLM's 0.7 default temperature
because LLMProviderManager.chat defaulted to 0.7 and UnifiedQA.chat passed
none, so 33/100 Condition answers changed between two identical benchmark
runs. These tests pin the new contract:

- temperature comes from LLM_TEMPERATURE (default 0.0) unless a caller
  passes one explicitly (summarization/re-ranking do);
- seed and response_format are only sent to providers that accept them,
  so Gemini/Anthropic/Ollama calls don't break;
- GEMINI_TIMEOUT (per call) is never longer than ANALYSIS_TIMEOUT (per
  extraction attempt).
"""

import types
from unittest.mock import AsyncMock

import pytest

import app.utils.config as config
from app.models import llm_provider as llm_provider_module
from app.models.llm_provider import LLMProvider, LLMProviderManager


@pytest.fixture(autouse=True)
def _fake_keys(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "test-key")
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    monkeypatch.setenv("OLLAMA_BASE_URL", "http://localhost:11434")


def _fake_response(text="{}"):
    message = types.SimpleNamespace(content=text)
    choice = types.SimpleNamespace(message=message)
    return types.SimpleNamespace(choices=[choice])


@pytest.fixture
def capture_completion(monkeypatch):
    """Replace litellm.acompletion with a recorder; returns the kwargs list."""
    recorder = AsyncMock(return_value=_fake_response('{"ok": true}'))
    monkeypatch.setattr(llm_provider_module.litellm, "acompletion", recorder)
    return recorder


# ---------------------------------------------------------------------------
# config
# ---------------------------------------------------------------------------


class TestConfigDefaults:
    def test_temperature_defaults_to_zero(self):
        assert config.LLM_TEMPERATURE == 0.0

    def test_seed_defaults_to_zero(self):
        assert config.LLM_SEED == 0

    def test_parse_optional_int_env_accepts_none_keyword(self, monkeypatch):
        monkeypatch.setenv("X_SEED", "none")
        assert config._parse_optional_int_env("X_SEED", 0) is None

    def test_parse_optional_int_env_falls_back_on_garbage(self, monkeypatch):
        monkeypatch.setenv("X_SEED", "abc")
        assert config._parse_optional_int_env("X_SEED", 7) == 7

    def test_parse_float_env_falls_back_on_garbage(self, monkeypatch):
        monkeypatch.setenv("X_TEMP", "warm")
        assert config._parse_float_env("X_TEMP", 0.0) == 0.0

    def test_inner_timeout_never_exceeds_outer(self):
        assert config._enforce_timeout_nesting(60, 90) == 60
        assert config._enforce_timeout_nesting(120, 90) == 90
        assert config.GEMINI_TIMEOUT <= config.ANALYSIS_TIMEOUT


# ---------------------------------------------------------------------------
# LLMProviderManager: temperature / seed / json_mode per provider
# ---------------------------------------------------------------------------


class TestProviderCapabilities:
    """Uses LiteLLM's own get_supported_openai_params, so these assertions
    also document what the pinned LiteLLM release reports per provider."""

    def test_gemini_json_mode_but_no_seed(self):
        mgr = LLMProviderManager(provider="gemini", model="gemini-2.5-flash")
        assert mgr.supports_json_mode() is True
        assert mgr.supports_seed() is False

    def test_openai_supports_both(self):
        mgr = LLMProviderManager(provider="openai", model="gpt-4o")
        assert mgr.supports_json_mode() is True
        assert mgr.supports_seed() is True

    def test_anthropic_json_mode_is_not_sent(self):
        # LiteLLM would emulate response_format for Claude via a forced tool
        # call; the extraction prompt already demands JSON, so keep the
        # prompt-only contract there.
        mgr = LLMProviderManager(provider="anthropic")
        assert mgr.supports_json_mode() is False
        assert mgr.supports_seed() is False

    def test_ollama_supports_both(self):
        mgr = LLMProviderManager(provider="ollama", model="llama3")
        assert mgr.supports_json_mode() is True
        assert mgr.supports_seed() is True

    def test_unknown_capability_lookup_is_conservative(self, monkeypatch):
        mgr = LLMProviderManager(provider="openai", model="gpt-4o")
        monkeypatch.setattr(mgr, "_supported_params", lambda: None)
        assert mgr.supports_seed() is False
        assert mgr.supports_json_mode() is False


@pytest.mark.asyncio
class TestChatSampling:
    async def test_default_temperature_is_configured_value(
        self, capture_completion, monkeypatch
    ):
        monkeypatch.setattr(config, "LLM_TEMPERATURE", 0.0)
        mgr = LLMProviderManager(provider="gemini", model="gemini-2.5-flash")
        await mgr.chat([{"role": "user", "content": "hi"}])
        kwargs = capture_completion.call_args.kwargs
        assert kwargs["temperature"] == 0.0
        assert kwargs["drop_params"] is True

    async def test_env_temperature_override_is_used(
        self, capture_completion, monkeypatch
    ):
        monkeypatch.setattr(config, "LLM_TEMPERATURE", 0.25)
        mgr = LLMProviderManager(provider="gemini", model="gemini-2.5-flash")
        await mgr.chat([{"role": "user", "content": "hi"}])
        assert capture_completion.call_args.kwargs["temperature"] == 0.25

    async def test_explicit_temperature_wins(self, capture_completion, monkeypatch):
        monkeypatch.setattr(config, "LLM_TEMPERATURE", 0.0)
        mgr = LLMProviderManager(provider="gemini", model="gemini-2.5-flash")
        await mgr.chat([{"role": "user", "content": "hi"}], temperature=0.3)
        assert capture_completion.call_args.kwargs["temperature"] == 0.3

    async def test_gemini_gets_response_format_but_no_seed(
        self, capture_completion, monkeypatch
    ):
        monkeypatch.setattr(config, "LLM_SEED", 0)
        mgr = LLMProviderManager(provider="gemini", model="gemini-2.5-flash")
        await mgr.chat([{"role": "user", "content": "hi"}], json_mode=True)
        kwargs = capture_completion.call_args.kwargs
        assert kwargs["response_format"] == {"type": "json_object"}
        assert "seed" not in kwargs

    async def test_openai_gets_seed_and_response_format(
        self, capture_completion, monkeypatch
    ):
        monkeypatch.setattr(config, "LLM_SEED", 0)
        mgr = LLMProviderManager(provider="openai", model="gpt-4o")
        await mgr.chat([{"role": "user", "content": "hi"}], json_mode=True)
        kwargs = capture_completion.call_args.kwargs
        assert kwargs["seed"] == 0
        assert kwargs["response_format"] == {"type": "json_object"}

    async def test_anthropic_gets_neither(self, capture_completion, monkeypatch):
        monkeypatch.setattr(config, "LLM_SEED", 0)
        mgr = LLMProviderManager(provider="anthropic")
        await mgr.chat([{"role": "user", "content": "hi"}], json_mode=True)
        kwargs = capture_completion.call_args.kwargs
        assert "seed" not in kwargs
        assert "response_format" not in kwargs
        assert kwargs["temperature"] == 0.0

    async def test_json_mode_off_by_default(self, capture_completion):
        mgr = LLMProviderManager(provider="openai", model="gpt-4o")
        await mgr.chat([{"role": "user", "content": "hi"}])
        assert "response_format" not in capture_completion.call_args.kwargs

    async def test_seed_disabled_with_none(self, capture_completion, monkeypatch):
        monkeypatch.setattr(config, "LLM_SEED", None)
        mgr = LLMProviderManager(provider="openai", model="gpt-4o")
        await mgr.chat([{"role": "user", "content": "hi"}])
        assert "seed" not in capture_completion.call_args.kwargs

    async def test_explicit_seed_wins(self, capture_completion, monkeypatch):
        monkeypatch.setattr(config, "LLM_SEED", 0)
        mgr = LLMProviderManager(provider="openai", model="gpt-4o")
        await mgr.chat([{"role": "user", "content": "hi"}], seed=42)
        assert capture_completion.call_args.kwargs["seed"] == 42

    async def test_provider_error_text_is_masked(self, monkeypatch):
        secret = "sk" + "-abcdefghijklmnopqrstuvwxyz0123456789ABCDEF"
        failing = AsyncMock(side_effect=RuntimeError(f"bad key {secret}"))
        monkeypatch.setattr(llm_provider_module.litellm, "acompletion", failing)
        mgr = LLMProviderManager(provider="openai", model="gpt-4o")
        resp = await mgr.chat([{"role": "user", "content": "hi"}])
        assert resp["confidence"] == 0.0
        assert secret not in resp["text"]
        assert secret not in resp["error"]


# ---------------------------------------------------------------------------
# GeminiQA fallback path uses the same temperature + native JSON mode
# ---------------------------------------------------------------------------


class TestGeminiQAGenerationConfig:
    def test_chat_config_uses_configured_temperature(self, monkeypatch):
        pytest.importorskip("google.generativeai")
        from app.models import gemini_qa

        monkeypatch.setattr(gemini_qa, "LLM_TEMPERATURE", 0.0)
        cfg = gemini_qa._chat_generation_config(json_mode=False)
        assert cfg.temperature == 0.0
        assert cfg.max_output_tokens == gemini_qa._CHAT_MAX_OUTPUT_TOKENS
        assert not getattr(cfg, "response_mime_type", None)

    def test_json_mode_sets_mime_type_and_larger_budget(self, monkeypatch):
        pytest.importorskip("google.generativeai")
        from app.models import gemini_qa

        monkeypatch.setattr(gemini_qa, "LLM_TEMPERATURE", 0.0)
        cfg = gemini_qa._chat_generation_config(json_mode=True)
        assert cfg.response_mime_type == "application/json"
        assert cfg.max_output_tokens == gemini_qa._JSON_MAX_OUTPUT_TOKENS
        assert cfg.temperature == 0.0

    def test_provider_enum_unchanged(self):
        # Guard against the capability table silently dropping a provider.
        assert {p.value for p in LLMProvider} == {
            "openai",
            "anthropic",
            "gemini",
            "ollama",
            "llamafile",
        }
