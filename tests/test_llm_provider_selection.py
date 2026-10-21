"""Regression tests for issue #136: LLM_PROVIDER was ignored by the analysis
pipeline, which hardcoded Gemini in two places (the analyzer singletons used by
/api/v1/analyze and /api/v2/analyze, and the app lifespan used by /qa). A
deployment with only OPENAI_API_KEY or ANTHROPIC_API_KEY set still sent every
request to Gemini, and model_used always reported DEFAULT_MODEL.
"""

import types

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from app.models.llm_provider import (
    LITELLM_AVAILABLE,
    LLMProvider,
    LLMProviderManager,
    resolve_provider_and_model,
)
from app.models.unified_qa import UnifiedQA

requires_litellm = pytest.mark.skipif(
    not LITELLM_AVAILABLE, reason="LiteLLM is not installed"
)

_PROVIDER_ENV_VARS = (
    "OPENAI_API_KEY",
    "ANTHROPIC_API_KEY",
    "GEMINI_API_KEY",
    "OLLAMA_BASE_URL",
    "OLLAMA_HOST",
)


@pytest.fixture
def clean_llm_env(monkeypatch):
    """No provider keys, and no LLM_* overrides leaking in from a real .env.

    app.utils.config reads LLM_PROVIDER/LLM_MODEL/DEFAULT_MODEL at import time,
    so those are patched on the module rather than in the environment.
    """
    for var in _PROVIDER_ENV_VARS:
        monkeypatch.delenv(var, raising=False)
    monkeypatch.setattr("app.utils.config.LLM_PROVIDER", None)
    monkeypatch.setattr("app.utils.config.LLM_MODEL", None)
    monkeypatch.setattr("app.utils.config.DEFAULT_MODEL", "gemini")
    return monkeypatch


class TestResolveProviderAndModel:
    def test_detects_openai_from_its_api_key(self, clean_llm_env):
        clean_llm_env.setenv("OPENAI_API_KEY", "test-openai-key")
        assert resolve_provider_and_model() == ("openai", None)

    def test_detects_anthropic_from_its_api_key(self, clean_llm_env):
        clean_llm_env.setenv("ANTHROPIC_API_KEY", "test-anthropic-key")
        assert resolve_provider_and_model() == ("anthropic", None)

    def test_detects_ollama_from_base_url(self, clean_llm_env):
        clean_llm_env.setenv("OLLAMA_BASE_URL", "http://localhost:11434")
        assert resolve_provider_and_model() == ("ollama", None)

    def test_llm_provider_overrides_detection(self, clean_llm_env):
        clean_llm_env.setenv("OPENAI_API_KEY", "test-openai-key")
        clean_llm_env.setattr("app.utils.config.LLM_PROVIDER", "anthropic")
        provider, _ = resolve_provider_and_model()
        assert provider == "anthropic"

    def test_llm_model_is_used_for_any_provider(self, clean_llm_env):
        clean_llm_env.setenv("OPENAI_API_KEY", "test-openai-key")
        clean_llm_env.setattr("app.utils.config.LLM_MODEL", "gpt-4o-mini")
        assert resolve_provider_and_model() == ("openai", "gpt-4o-mini")

    def test_default_model_is_honoured_for_gemini(self, clean_llm_env):
        clean_llm_env.setenv("GEMINI_API_KEY", "test-gemini-key")
        clean_llm_env.setattr(
            "app.utils.config.DEFAULT_MODEL", "models/gemini-2.5-flash"
        )
        assert resolve_provider_and_model() == ("gemini", "models/gemini-2.5-flash")

    def test_gemini_default_model_is_not_leaked_to_other_providers(self, clean_llm_env):
        """DEFAULT_MODEL has always named a Gemini model; handing it to OpenAI
        would request a model called "models/gemini-2.5-flash"."""
        clean_llm_env.setenv("OPENAI_API_KEY", "test-openai-key")
        clean_llm_env.setattr(
            "app.utils.config.DEFAULT_MODEL", "models/gemini-2.5-flash"
        )
        assert resolve_provider_and_model() == ("openai", None)

    def test_bare_provider_label_is_not_treated_as_a_model(self, clean_llm_env):
        """DEFAULT_MODEL defaults to "gemini", which is a provider label and
        would resolve to the nonexistent model "gemini/gemini"."""
        clean_llm_env.setenv("GEMINI_API_KEY", "test-gemini-key")
        assert resolve_provider_and_model() == ("gemini", None)


@requires_litellm
class TestSingletonHonoursProvider:
    @pytest.fixture(autouse=True)
    def _reset_singleton(self, monkeypatch):
        import app.services.bugsigdb_analyzer.singletons as singletons

        monkeypatch.setattr(singletons, "_unified_qa", None)
        monkeypatch.setattr(singletons, "GEMINI_API_KEY", "")
        yield
        singletons._unified_qa = None

    def test_openai_only_deployment_uses_openai(self, clean_llm_env):
        from app.services.bugsigdb_analyzer.singletons import get_unified_qa

        clean_llm_env.setenv("OPENAI_API_KEY", "test-openai-key")

        qa = get_unified_qa()

        assert qa is not None
        assert qa.llm_manager is not None
        assert qa.llm_manager.provider == LLMProvider.OPENAI

    def test_llm_provider_override_wins_over_detection(self, clean_llm_env):
        from app.services.bugsigdb_analyzer.singletons import get_unified_qa

        clean_llm_env.setenv("OPENAI_API_KEY", "test-openai-key")
        clean_llm_env.setenv("ANTHROPIC_API_KEY", "test-anthropic-key")
        clean_llm_env.setattr("app.utils.config.LLM_PROVIDER", "anthropic")

        qa = get_unified_qa()

        assert qa is not None
        assert qa.llm_manager.provider == LLMProvider.ANTHROPIC

    def test_ollama_deployment_can_be_used_for_extraction(self, clean_llm_env):
        from app.services.bugsigdb_analyzer.singletons import get_unified_qa

        clean_llm_env.setenv("OLLAMA_BASE_URL", "http://localhost:11434")

        qa = get_unified_qa()

        assert qa is not None
        assert qa.llm_manager.provider == LLMProvider.OLLAMA


@requires_litellm
class TestUnifiedQAProviderWiring:
    def test_detects_provider_when_none_given(self, clean_llm_env):
        clean_llm_env.setenv("ANTHROPIC_API_KEY", "test-anthropic-key")

        qa = UnifiedQA(use_paperqa=False)

        assert qa.llm_manager.provider == LLMProvider.ANTHROPIC
        assert qa.provider == "anthropic"

    def test_paperqa_does_not_hijack_a_non_gemini_provider(self, clean_llm_env):
        """PaperQAAgent is Gemini-backed and takes precedence in chat(), so it
        must stay off when the configured provider is something else."""
        clean_llm_env.setenv("OPENAI_API_KEY", "test-openai-key")

        qa = UnifiedQA(provider="openai", gemini_api_key="test-gemini-key")

        assert qa.use_paperqa is False
        assert qa.qa_system is None

    def test_reports_the_resolved_model(self, clean_llm_env):
        clean_llm_env.setenv("OPENAI_API_KEY", "test-openai-key")

        qa = UnifiedQA(provider="openai", model=None, use_paperqa=False)

        assert qa.model == LLMProviderManager.DEFAULT_MODELS[LLMProvider.OPENAI]


class TestDescribeActiveModel:
    @staticmethod
    def _fake_qa(provider=None, model=None, qa_system=None):
        manager = (
            types.SimpleNamespace(provider=provider, model=model)
            if provider is not None
            else None
        )
        return types.SimpleNamespace(llm_manager=manager, qa_system=qa_system)

    def test_prefixes_the_provider_when_the_model_does_not(self, monkeypatch):
        from app.services.bugsigdb_analyzer.singletons import describe_active_model

        monkeypatch.setattr(
            "app.services.bugsigdb_analyzer.get_unified_qa",
            lambda: self._fake_qa(LLMProvider.OPENAI, "gpt-4o"),
        )
        assert describe_active_model() == "openai/gpt-4o"

    def test_keeps_an_already_prefixed_model(self, monkeypatch):
        from app.services.bugsigdb_analyzer.singletons import describe_active_model

        monkeypatch.setattr(
            "app.services.bugsigdb_analyzer.get_unified_qa",
            lambda: self._fake_qa(LLMProvider.GEMINI, "gemini/gemini-2.0-flash"),
        )
        assert describe_active_model() == "gemini/gemini-2.0-flash"

    def test_falls_back_to_the_gemini_qa_model(self, monkeypatch):
        from app.services.bugsigdb_analyzer.singletons import describe_active_model

        monkeypatch.setattr(
            "app.services.bugsigdb_analyzer.get_unified_qa",
            lambda: self._fake_qa(
                qa_system=types.SimpleNamespace(model="gemini-2.5-flash")
            ),
        )
        assert describe_active_model() == "gemini-2.5-flash"

    def test_falls_back_to_default_model_without_a_client(self, monkeypatch):
        from app.services.bugsigdb_analyzer.singletons import describe_active_model

        monkeypatch.setattr(
            "app.services.bugsigdb_analyzer.get_unified_qa", lambda: None
        )
        assert isinstance(describe_active_model(), str)
        assert describe_active_model()


@pytest.mark.asyncio
class TestLifespanProviderWiring:
    async def test_lifespan_builds_the_qa_client_for_the_configured_provider(
        self, clean_llm_env
    ):
        from fastapi import FastAPI

        import app.core.lifespan as lifespan_module

        clean_llm_env.setenv("ANTHROPIC_API_KEY", "test-anthropic-key")
        recorder = MagicMock(return_value="qa-client")
        clean_llm_env.setattr(lifespan_module, "UnifiedQA", recorder)
        clean_llm_env.setattr(
            lifespan_module, "PubMedRetriever", MagicMock(return_value="retriever")
        )

        app = FastAPI()
        async with lifespan_module.lifespan(app):
            assert app.state.unified_qa == "qa-client"

        assert recorder.call_args.kwargs["provider"] == "anthropic"


@pytest.mark.asyncio
class TestModelUsedReportsWhatRan:
    @patch("app.services.bugsigdb_analyzer.is_in_bugsigdb", return_value=False)
    @patch("app.services.bugsigdb_analyzer.get_unified_qa")
    @patch("app.services.bugsigdb_analyzer.get_pubmed_retriever")
    @patch("app.services.bugsigdb_analyzer.get_cache_manager")
    async def test_simple_analysis_reports_the_active_model(
        self, mock_get_cache, mock_get_retriever, mock_get_qa, mock_in_bugsigdb
    ):
        pytest.importorskip("defusedxml")
        from app.services.bugsigdb_analyzer import analyze_paper_simple

        cache_manager = MagicMock()
        cache_manager.get_analysis_result.return_value = None
        cache_manager.is_cache_valid.return_value = False
        mock_get_cache.return_value = cache_manager

        retriever = MagicMock()
        retriever.get_texts_for_analysis_async = AsyncMock(
            return_value={
                "title": "A Test Paper",
                "abstract": "Abstract about 30 human patients.",
                "full_text": "",
                "publication_date": "2023-05-01",
                "journal": "Test Journal",
                "authors": ["A. Author"],
            }
        )
        mock_get_retriever.return_value = retriever

        qa = MagicMock()
        qa.chat = AsyncMock(return_value={"text": '{"host_species_raw": "human"}'})
        qa.llm_manager = types.SimpleNamespace(
            provider=LLMProvider.OPENAI, model="gpt-4o"
        )
        mock_get_qa.return_value = qa

        result = await analyze_paper_simple("12345678")

        assert result["model_used"] == "openai/gpt-4o"
        stored = cache_manager.store_analysis_result.call_args.kwargs
        assert stored["source"] == "openai/gpt-4o"
