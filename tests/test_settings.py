"""
Tests for app/core/settings.py - previously had zero test coverage (59%,
entirely incidental from other modules importing it). Covers the Pydantic
settings model, file/env/preset loading, SettingsManager, and the
module-level singleton accessors.
"""

import json

import pytest
import yaml

from app.core import settings as settings_module
from app.core.settings import (
    BioAnalyzerSettings,
    SettingsManager,
    Environment,
    LogLevel,
    RerankMethod,
    SummaryLength,
    SummaryQuality,
    get_settings_manager,
    load_settings,
    get_settings,
    save_settings,
)


@pytest.fixture(autouse=True)
def reset_global_singletons(monkeypatch):
    """The module caches a global SettingsManager/Settings instance - reset
    between tests so one test's load() doesn't leak into another's."""
    monkeypatch.setattr(settings_module, "_settings_manager", None)
    monkeypatch.setattr(settings_module, "_settings", None)


@pytest.fixture
def clean_env(monkeypatch):
    """Strip every env var from_env()/apply_to_environment() touch, so tests
    aren't affected by the real environment (e.g. GEMINI_API_KEY in CI)."""
    for var in (
        "API_TIMEOUT",
        "ANALYSIS_TIMEOUT",
        "GEMINI_TIMEOUT",
        "FRONTEND_TIMEOUT",
        "NCBI_RATE_LIMIT_DELAY",
        "MAX_CONCURRENT_REQUESTS",
        "LLM_PROVIDER",
        "LLM_MODEL",
        "GEMINI_API_KEY",
        "OPENAI_API_KEY",
        "ANTHROPIC_API_KEY",
        "OLLAMA_BASE_URL",
        "RAG_SUMMARY_PROVIDER",
        "RAG_SUMMARY_MODEL",
        "RAG_SUMMARY_LENGTH",
        "RAG_SUMMARY_QUALITY",
        "RAG_RERANK_METHOD",
        "RAG_USE_SUMMARY_CACHE",
        "RAG_MAX_SUMMARY_KEY_POINTS",
        "RAG_TOP_K_CHUNKS",
        "CACHE_VALIDITY_HOURS",
        "MAX_CACHE_SIZE",
        "ENABLE_RATE_LIMITING",
        "RATE_LIMIT_PER_MINUTE",
        "USE_FULLTEXT",
        "NCBI_API_KEY",
        "EMAIL",
        "LOG_LEVEL",
        "ENVIRONMENT",
        "CORS_ORIGINS",
        "ENABLE_REQUEST_ID",
    ):
        monkeypatch.delenv(var, raising=False)
    yield monkeypatch


class TestValidatePreset:
    def test_valid_preset_names_accepted(self):
        for name in ("fast", "balanced", "high_quality", "development", "production"):
            s = BioAnalyzerSettings(preset=name)
            assert s.preset == name

    def test_none_preset_accepted(self):
        assert BioAnalyzerSettings(preset=None).preset is None

    def test_invalid_preset_raises(self):
        with pytest.raises(ValueError, match="Invalid preset"):
            BioAnalyzerSettings(preset="not-a-real-preset")


class TestModelDumpRoundtrip:
    def test_model_dump_and_json_roundtrip(self):
        s = BioAnalyzerSettings()
        d = s.model_dump()
        assert d["version"] == "1.0.0"
        json_str = s.model_dump_json()
        assert json.loads(json_str)["version"] == "1.0.0"

    def test_from_dict_reconstructs_equivalent_settings(self):
        s = BioAnalyzerSettings()
        s.api.timeout = 99
        rebuilt = BioAnalyzerSettings.from_dict(s.model_dump())
        assert rebuilt.api.timeout == 99


class TestFromFile:
    def test_loads_json_file(self, tmp_path):
        path = tmp_path / "settings.json"
        path.write_text(json.dumps({"api": {"timeout": 77}}))
        s = BioAnalyzerSettings.from_file(path)
        assert s.api.timeout == 77

    def test_loads_yaml_file(self, tmp_path):
        path = tmp_path / "settings.yaml"
        path.write_text(yaml.dump({"api": {"timeout": 55}}))
        s = BioAnalyzerSettings.from_file(path)
        assert s.api.timeout == 55

    def test_raises_when_file_missing(self, tmp_path):
        with pytest.raises(FileNotFoundError):
            BioAnalyzerSettings.from_file(tmp_path / "nope.json")

    def test_inherits_from_base_file(self, tmp_path):
        base_path = tmp_path / "base.json"
        base_path.write_text(
            json.dumps({"api": {"timeout": 11}, "cache": {"max_size": 500}})
        )
        child_path = tmp_path / "child.json"
        child_path.write_text(
            json.dumps({"inherit_from": "base.json", "api": {"timeout": 22}})
        )
        s = BioAnalyzerSettings.from_file(child_path)
        assert s.api.timeout == 22  # overridden by child
        assert s.cache.max_size == 500  # inherited from base


class TestToFile:
    def test_writes_json(self, tmp_path):
        path = tmp_path / "out.json"
        BioAnalyzerSettings().to_file(path, format="json")
        data = json.loads(path.read_text())
        assert data["version"] == "1.0.0"

    def test_writes_yaml(self, tmp_path):
        path = tmp_path / "out.yaml"
        BioAnalyzerSettings().to_file(path, format="yaml")
        data = yaml.safe_load(path.read_text())
        assert data["version"] == "1.0.0"

    def test_creates_parent_directories(self, tmp_path):
        path = tmp_path / "nested" / "dir" / "out.json"
        BioAnalyzerSettings().to_file(path)
        assert path.exists()


class TestFromEnv:
    def test_defaults_when_no_env_vars_set(self, clean_env):
        s = BioAnalyzerSettings.from_env()
        assert s.api.timeout == 30
        assert s.llm.provider is None

    def test_reads_api_settings(self, clean_env):
        clean_env.setenv("API_TIMEOUT", "12")
        clean_env.setenv("ANALYSIS_TIMEOUT", "34")
        clean_env.setenv("MAX_CONCURRENT_REQUESTS", "7")
        s = BioAnalyzerSettings.from_env()
        assert s.api.timeout == 12
        assert s.api.analysis_timeout == 34
        assert s.api.max_concurrent_requests == 7

    def test_reads_llm_settings(self, clean_env):
        clean_env.setenv("LLM_PROVIDER", "GEMINI")
        clean_env.setenv("GEMINI_API_KEY", "test-key-123")
        s = BioAnalyzerSettings.from_env()
        assert s.llm.provider == "gemini"
        assert s.llm.gemini_api_key == "test-key-123"

    def test_reads_rag_enum_settings(self, clean_env):
        clean_env.setenv("RAG_SUMMARY_LENGTH", "SHORT")
        clean_env.setenv("RAG_SUMMARY_QUALITY", "HIGH")
        clean_env.setenv("RAG_RERANK_METHOD", "LLM")
        clean_env.setenv("RAG_TOP_K_CHUNKS", "15")
        s = BioAnalyzerSettings.from_env()
        assert s.rag.summary_length == SummaryLength.SHORT
        assert s.rag.summary_quality == SummaryQuality.HIGH
        assert s.rag.rerank_method == RerankMethod.LLM
        assert s.rag.top_k_chunks == 15

    def test_reads_boolean_flags_case_insensitively(self, clean_env):
        clean_env.setenv("RAG_USE_SUMMARY_CACHE", "Yes")
        clean_env.setenv("ENABLE_RATE_LIMITING", "1")
        clean_env.setenv("USE_FULLTEXT", "TRUE")
        s = BioAnalyzerSettings.from_env()
        assert s.rag.use_cache is True
        assert s.rate_limit.enabled is True
        assert s.retrieval.use_fulltext is True

    def test_reads_retrieval_and_logging_settings(self, clean_env):
        clean_env.setenv("NCBI_API_KEY", "ncbi-key")
        clean_env.setenv("EMAIL", "me@example.com")
        clean_env.setenv("LOG_LEVEL", "debug")
        s = BioAnalyzerSettings.from_env()
        assert s.retrieval.ncbi_api_key == "ncbi-key"
        assert s.retrieval.email == "me@example.com"
        assert s.logging.level == LogLevel.DEBUG

    def test_reads_environment_and_security_settings(self, clean_env):
        clean_env.setenv("ENVIRONMENT", "production")
        clean_env.setenv("CORS_ORIGINS", "https://a.com,https://b.com")
        clean_env.setenv("ENABLE_REQUEST_ID", "false")
        s = BioAnalyzerSettings.from_env()
        assert s.environment == Environment.PRODUCTION
        assert s.security.cors_origins == ["https://a.com", "https://b.com"]
        assert s.security.enable_request_id is False


class TestFromPreset:
    def test_fast_preset(self):
        s = BioAnalyzerSettings.from_preset("fast")
        assert s.preset == "fast"
        assert s.api.timeout == 15
        assert s.rag.rerank_method == RerankMethod.KEYWORD

    def test_balanced_preset(self):
        s = BioAnalyzerSettings.from_preset("balanced")
        assert s.rag.summary_quality == SummaryQuality.BALANCED

    def test_high_quality_preset(self):
        s = BioAnalyzerSettings.from_preset("high_quality")
        assert s.rag.top_k_chunks == 20
        assert s.rag.rerank_method == RerankMethod.LLM

    def test_development_preset(self):
        s = BioAnalyzerSettings.from_preset("development")
        assert s.environment == Environment.DEVELOPMENT
        assert s.logging.level == LogLevel.DEBUG

    def test_production_preset(self):
        s = BioAnalyzerSettings.from_preset("production")
        assert s.environment == Environment.PRODUCTION
        assert s.rate_limit.enabled is True

    def test_unknown_preset_raises(self):
        with pytest.raises(ValueError, match="Unknown preset"):
            BioAnalyzerSettings.from_preset("nonexistent")


class TestMerge:
    def test_other_takes_precedence(self):
        base = BioAnalyzerSettings()
        base.api.timeout = 10
        override = BioAnalyzerSettings()
        override.api.timeout = 20
        merged = base.merge(override)
        assert merged.api.timeout == 20

    def test_none_valued_fields_on_override_keep_base_values(self):
        # merge() drops None-valued fields from `other` (exclude_none=True)
        # before merging, so a field at its real (non-None) default on
        # `other` always wins - only genuinely-None fields fall back to base.
        base = BioAnalyzerSettings()
        base.llm.provider = "anthropic"
        override = BioAnalyzerSettings()
        assert override.llm.provider is None
        merged = base.merge(override)
        assert merged.llm.provider == "anthropic"


class TestApplyToEnvironment:
    def test_sets_core_env_vars(self, clean_env):
        s = BioAnalyzerSettings()
        s.api.timeout = 42
        s.apply_to_environment()
        import os

        assert os.environ["API_TIMEOUT"] == "42"
        assert os.environ["RAG_SUMMARY_LENGTH"] == s.rag.summary_length.value
        assert os.environ["ENVIRONMENT"] == s.environment.value

    def test_only_sets_optional_vars_when_present(self, clean_env):
        import os

        s = BioAnalyzerSettings()
        assert s.llm.gemini_api_key is None
        s.apply_to_environment()
        assert "GEMINI_API_KEY" not in os.environ

        s.llm.gemini_api_key = "abc123"
        s.apply_to_environment()
        assert os.environ["GEMINI_API_KEY"] == "abc123"


class TestSettingsManager:
    def test_init_uses_default_path_when_none_given(self):
        manager = SettingsManager()
        assert manager.settings_file == SettingsManager.DEFAULT_SETTINGS_FILE

    def test_init_uses_provided_path(self, tmp_path):
        custom = tmp_path / "custom.json"
        manager = SettingsManager(settings_file=custom)
        assert manager.settings_file == custom

    def test_load_with_no_sources_returns_defaults(self, tmp_path, clean_env):
        manager = SettingsManager(settings_file=tmp_path / "missing.json")
        s = manager.load(from_env=False)
        assert s.api.timeout == 30

    def test_load_applies_preset(self, tmp_path, clean_env):
        manager = SettingsManager(settings_file=tmp_path / "missing.json")
        s = manager.load(from_env=False, from_preset="fast")
        assert s.api.timeout == 15

    def test_load_applies_file_over_preset(self, tmp_path, clean_env):
        path = tmp_path / "settings.json"
        path.write_text(json.dumps({"api": {"timeout": 7}}))
        manager = SettingsManager(settings_file=path)
        s = manager.load(from_env=False, from_preset="fast")
        assert s.api.timeout == 7

    def test_load_applies_cli_overrides_last(self, tmp_path, clean_env):
        path = tmp_path / "settings.json"
        path.write_text(json.dumps({"api": {"timeout": 7}}))
        manager = SettingsManager(settings_file=path)
        s = manager.load(from_env=False, cli_overrides={"api": {"timeout": 99}})
        assert s.api.timeout == 99

    def test_load_applies_env_over_file(self, tmp_path, clean_env):
        path = tmp_path / "settings.json"
        path.write_text(json.dumps({"api": {"timeout": 7}}))
        clean_env.setenv("API_TIMEOUT", "55")
        manager = SettingsManager(settings_file=path)
        s = manager.load(from_env=True)
        assert s.api.timeout == 55

    def test_save_writes_provided_settings(self, tmp_path):
        manager = SettingsManager(settings_file=tmp_path / "settings.json")
        s = BioAnalyzerSettings()
        s.api.timeout = 88
        manager.save(settings=s)
        saved = json.loads((tmp_path / "settings.json").read_text())
        assert saved["api"]["timeout"] == 88

    def test_save_uses_loaded_settings_when_none_provided(self, tmp_path, clean_env):
        manager = SettingsManager(settings_file=tmp_path / "settings.json")
        manager.load(from_env=False)
        manager.save()
        assert (tmp_path / "settings.json").exists()

    def test_save_raises_when_nothing_to_save(self, tmp_path):
        manager = SettingsManager(settings_file=tmp_path / "settings.json")
        with pytest.raises(ValueError, match="No settings to save"):
            manager.save()

    def test_get_settings_loads_lazily(self, tmp_path, clean_env):
        manager = SettingsManager(settings_file=tmp_path / "missing.json")
        assert manager._settings is None
        s = manager.get_settings()
        assert s is not None
        assert manager._settings is s

    def test_migrate_settings_json(self, tmp_path):
        old_path = tmp_path / "old.json"
        old_path.write_text(
            json.dumps(
                {"api_timeout": 33, "llm_provider": "openai", "rag_enabled": False}
            )
        )
        manager = SettingsManager()
        new_settings = manager.migrate_settings(old_path)
        assert new_settings.api.timeout == 33
        assert new_settings.llm.provider == "openai"
        assert new_settings.rag.enabled is False
        assert old_path.with_suffix(".new.json").exists()

    def test_migrate_settings_yaml(self, tmp_path):
        old_path = tmp_path / "old.yaml"
        old_path.write_text(yaml.dump({"api_timeout": 21}))
        manager = SettingsManager()
        new_path = tmp_path / "migrated.json"
        new_settings = manager.migrate_settings(old_path, new_file=new_path)
        assert new_settings.api.timeout == 21
        assert new_path.exists()

    def test_migrate_settings_raises_on_unreadable_file(self, tmp_path):
        old_path = tmp_path / "broken.json"
        old_path.write_text("{not valid json")
        manager = SettingsManager()
        with pytest.raises(ValueError, match="Failed to load old settings"):
            manager.migrate_settings(old_path)


class TestModuleLevelAccessors:
    def test_get_settings_manager_returns_singleton(self):
        m1 = get_settings_manager()
        m2 = get_settings_manager()
        assert m1 is m2

    def test_load_settings_sets_global(self, tmp_path, clean_env, monkeypatch):
        monkeypatch.setattr(
            settings_module.SettingsManager,
            "DEFAULT_SETTINGS_FILE",
            tmp_path / "missing.json",
        )
        s = load_settings(from_env=False)
        assert s is not None
        assert get_settings() is s

    def test_get_settings_loads_if_unset(self, tmp_path, clean_env, monkeypatch):
        monkeypatch.setattr(
            settings_module.SettingsManager,
            "DEFAULT_SETTINGS_FILE",
            tmp_path / "missing.json",
        )
        s = get_settings()
        assert s is not None

    def test_save_settings_uses_manager(self, tmp_path, clean_env, monkeypatch):
        monkeypatch.setattr(
            settings_module.SettingsManager,
            "DEFAULT_SETTINGS_FILE",
            tmp_path / "settings.json",
        )
        load_settings(from_env=False)
        save_settings()
        assert (tmp_path / "settings.json").exists()
