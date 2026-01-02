"""Settings system for BioAnalyzer with Pydantic models and multiple loading sources."""

import json
import logging
import os
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Literal, Optional

import yaml
from pydantic import BaseModel, ConfigDict, Field, field_validator

logger = logging.getLogger(__name__)


class SummaryLength(str, Enum):
    """Summary length options."""

    SHORT = "short"
    MEDIUM = "medium"
    LONG = "long"


class SummaryQuality(str, Enum):
    """Summary quality options."""

    FAST = "fast"
    BALANCED = "balanced"
    HIGH = "high"


class RerankMethod(str, Enum):
    """Re-ranking method options."""

    KEYWORD = "keyword"
    LLM = "llm"
    HYBRID = "hybrid"


class LogLevel(str, Enum):
    """Logging level options."""

    DEBUG = "DEBUG"
    INFO = "INFO"
    WARNING = "WARNING"
    ERROR = "ERROR"
    CRITICAL = "CRITICAL"


class Environment(str, Enum):
    """Environment options."""

    DEVELOPMENT = "development"
    STAGING = "staging"
    PRODUCTION = "production"


class APIConfig(BaseModel):
    """API configuration settings."""

    model_config = ConfigDict(extra="allow")

    timeout: int = Field(default=30, ge=1, le=300, description="API timeout in seconds")
    analysis_timeout: int = Field(default=45, ge=1, le=600, description="Total analysis timeout in seconds")
    gemini_timeout: int = Field(default=30, ge=1, le=300, description="Gemini API timeout in seconds")
    frontend_timeout: int = Field(default=60, ge=1, le=600, description="Frontend timeout in seconds")
    ncbi_timeout: int = Field(default=60, ge=1, le=300, description="NCBI API timeout in seconds")
    ncbi_rate_limit_delay: float = Field(default=0.34, ge=0.0, le=10.0, description="NCBI rate limit delay in seconds")
    max_concurrent_requests: int = Field(default=3, ge=1, le=20, description="Maximum concurrent requests")
    verify_ssl: bool = Field(default=True, description="Verify SSL certificates")


class LLMConfig(BaseModel):
    """LLM provider configuration."""

    model_config = ConfigDict(extra="allow")

    provider: Optional[str] = Field(
        default=None, description="LLM provider (openai, anthropic, gemini, ollama, llamafile)"
    )
    model: Optional[str] = Field(default=None, description="Specific model to use")
    api_key: Optional[str] = Field(default=None, description="API key (can be set via env var)")

    # API Keys (can be set via env vars)
    gemini_api_key: Optional[str] = Field(default=None, description="Gemini API key")
    openai_api_key: Optional[str] = Field(default=None, description="OpenAI API key")
    anthropic_api_key: Optional[str] = Field(default=None, description="Anthropic API key")
    ollama_base_url: Optional[str] = Field(default="http://localhost:11434", description="Ollama server URL")


class RAGConfig(BaseModel):
    """RAG (Retrieval-Augmented Generation) configuration."""

    model_config = ConfigDict(extra="allow")

    enabled: bool = Field(default=True, description="Enable RAG features")
    top_k_chunks: int = Field(default=10, ge=1, le=100, description="Number of top chunks to use")
    rerank_method: RerankMethod = Field(default=RerankMethod.HYBRID, description="Re-ranking method")
    summary_length: SummaryLength = Field(default=SummaryLength.MEDIUM, description="Summary length")
    summary_quality: SummaryQuality = Field(default=SummaryQuality.BALANCED, description="Summary quality")
    summary_provider: Optional[str] = Field(default=None, description="LLM provider for summarization")
    summary_model: Optional[str] = Field(default=None, description="Model for summarization")
    use_cache: bool = Field(default=True, description="Enable summary caching")
    max_summary_key_points: int = Field(default=5, ge=1, le=20, description="Maximum key points per summary")


class CacheConfig(BaseModel):
    """Cache configuration."""

    model_config = ConfigDict(extra="allow")

    enabled: bool = Field(default=True, description="Enable caching")
    validity_hours: int = Field(default=24, ge=1, le=720, description="Cache validity in hours")
    max_size: int = Field(default=1000, ge=1, le=100000, description="Maximum cache entries")
    directory: Path = Field(default=Path("cache"), description="Cache directory")


class RateLimitConfig(BaseModel):
    """Rate limiting configuration."""

    model_config = ConfigDict(extra="allow")

    enabled: bool = Field(default=True, description="Enable rate limiting")
    requests_per_minute: int = Field(default=60, ge=1, le=1000, description="Requests per minute limit")


class LoggingConfig(BaseModel):
    """Logging configuration."""

    model_config = ConfigDict(extra="allow")

    level: LogLevel = Field(default=LogLevel.INFO, description="Logging level")
    format: str = Field(default="%(asctime)s - %(name)s - %(levelname)s - %(message)s", description="Log format")
    file_format: str = Field(
        default="%(asctime)s - %(name)s - %(levelname)s - %(funcName)s:%(lineno)d - %(message)s",
        description="File log format",
    )
    directory: Path = Field(default=Path("logs"), description="Log directory")
    max_file_size: int = Field(default=10 * 1024 * 1024, ge=1024, description="Maximum log file size in bytes")
    max_files: int = Field(default=5, ge=1, le=50, description="Maximum number of rotated log files")


class RetrievalConfig(BaseModel):
    """Data retrieval configuration."""

    model_config = ConfigDict(extra="allow")

    use_fulltext: bool = Field(default=False, description="Use full text retrieval")
    ncbi_api_key: Optional[str] = Field(default=None, description="NCBI API key")
    email: Optional[str] = Field(default=None, description="Email for NCBI API requests")
    ncbi_api_url: str = Field(default="https://eutils.ncbi.nlm.nih.gov/entrez/eutils", description="NCBI API URL")


class SecurityConfig(BaseModel):
    """Security configuration."""

    model_config = ConfigDict(extra="allow")

    cors_origins: List[str] = Field(default=["*"], description="CORS allowed origins")
    enable_request_id: bool = Field(default=True, description="Enable request ID tracking")


class BioAnalyzerSettings(BaseModel):
    """Settings for BioAnalyzer with support for file/env/CLI loading and presets."""

    model_config = ConfigDict(extra="allow", validate_assignment=True)

    version: str = Field(default="1.0.0", description="Settings schema version")
    preset: Optional[str] = Field(default=None, description="Preset configuration name")
    inherit_from: Optional[str] = Field(default=None, description="Path to settings file to inherit from")
    environment: Environment = Field(default=Environment.DEVELOPMENT, description="Environment")

    api: APIConfig = Field(default_factory=APIConfig, description="API configuration")
    llm: LLMConfig = Field(default_factory=LLMConfig, description="LLM configuration")
    rag: RAGConfig = Field(default_factory=RAGConfig, description="RAG configuration")
    cache: CacheConfig = Field(default_factory=CacheConfig, description="Cache configuration")
    rate_limit: RateLimitConfig = Field(default_factory=RateLimitConfig, description="Rate limiting configuration")
    logging: LoggingConfig = Field(default_factory=LoggingConfig, description="Logging configuration")
    retrieval: RetrievalConfig = Field(default_factory=RetrievalConfig, description="Retrieval configuration")
    security: SecurityConfig = Field(default_factory=SecurityConfig, description="Security configuration")

    @field_validator("preset")
    @classmethod
    def validate_preset(cls, v):
        """Validate preset name."""
        if v is not None:
            valid_presets = ["fast", "balanced", "high_quality", "development", "production"]
            if v not in valid_presets:
                raise ValueError(f"Invalid preset: {v}. Valid presets: {valid_presets}")
        return v

    def model_dump(self, **kwargs) -> Dict[str, Any]:
        """Export settings to dictionary."""
        return super().model_dump(**kwargs)

    def model_dump_json(self, **kwargs) -> str:
        """Export settings to JSON string."""
        return super().model_dump_json(**kwargs)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "BioAnalyzerSettings":
        """Create settings from dictionary."""
        return cls(**data)

    @classmethod
    def from_file(cls, file_path: Path) -> "BioAnalyzerSettings":
        """Load settings from JSON or YAML file."""
        file_path = Path(file_path)
        if not file_path.exists():
            raise FileNotFoundError(f"Settings file not found: {file_path}")

        with open(file_path, "r") as f:
            if file_path.suffix.lower() in [".yaml", ".yml"]:
                data = yaml.safe_load(f)
            else:
                data = json.load(f)

        # Handle inheritance
        if isinstance(data, dict) and "inherit_from" in data:
            inherit_path = Path(data["inherit_from"])
            if not inherit_path.is_absolute():
                inherit_path = file_path.parent / inherit_path
            base_settings = cls.from_file(inherit_path)
            # Merge: base settings first, then override with current file
            base_dict = base_settings.model_dump(exclude_none=True)
            base_dict.update(data)
            data = base_dict

        return cls.from_dict(data)

    def to_file(self, file_path: Path, format: Literal["json", "yaml"] = "json"):
        """Save settings to file."""
        file_path = Path(file_path)
        file_path.parent.mkdir(parents=True, exist_ok=True)

        data = self.model_dump(exclude_none=True)

        with open(file_path, "w") as f:
            if format == "yaml":
                yaml.dump(data, f, default_flow_style=False, sort_keys=False)
            else:
                json.dump(data, f, indent=2, sort_keys=False)

    @classmethod
    def from_env(cls) -> "BioAnalyzerSettings":
        """Load settings from environment variables."""
        settings = cls()

        # API settings
        if os.getenv("API_TIMEOUT"):
            settings.api.timeout = int(os.getenv("API_TIMEOUT"))
        if os.getenv("ANALYSIS_TIMEOUT"):
            settings.api.analysis_timeout = int(os.getenv("ANALYSIS_TIMEOUT"))
        if os.getenv("GEMINI_TIMEOUT"):
            settings.api.gemini_timeout = int(os.getenv("GEMINI_TIMEOUT"))
        if os.getenv("FRONTEND_TIMEOUT"):
            settings.api.frontend_timeout = int(os.getenv("FRONTEND_TIMEOUT"))
        if os.getenv("NCBI_RATE_LIMIT_DELAY"):
            settings.api.ncbi_rate_limit_delay = float(os.getenv("NCBI_RATE_LIMIT_DELAY"))
        if os.getenv("MAX_CONCURRENT_REQUESTS"):
            settings.api.max_concurrent_requests = int(os.getenv("MAX_CONCURRENT_REQUESTS"))

        # LLM settings
        if os.getenv("LLM_PROVIDER"):
            settings.llm.provider = os.getenv("LLM_PROVIDER").lower()
        if os.getenv("LLM_MODEL"):
            settings.llm.model = os.getenv("LLM_MODEL")
        if os.getenv("GEMINI_API_KEY"):
            settings.llm.gemini_api_key = os.getenv("GEMINI_API_KEY")
        if os.getenv("OPENAI_API_KEY"):
            settings.llm.openai_api_key = os.getenv("OPENAI_API_KEY")
        if os.getenv("ANTHROPIC_API_KEY"):
            settings.llm.anthropic_api_key = os.getenv("ANTHROPIC_API_KEY")
        if os.getenv("OLLAMA_BASE_URL"):
            settings.llm.ollama_base_url = os.getenv("OLLAMA_BASE_URL")

        # RAG settings
        if os.getenv("RAG_SUMMARY_PROVIDER"):
            settings.rag.summary_provider = os.getenv("RAG_SUMMARY_PROVIDER").lower()
        if os.getenv("RAG_SUMMARY_MODEL"):
            settings.rag.summary_model = os.getenv("RAG_SUMMARY_MODEL")
        if os.getenv("RAG_SUMMARY_LENGTH"):
            settings.rag.summary_length = SummaryLength(os.getenv("RAG_SUMMARY_LENGTH").lower())
        if os.getenv("RAG_SUMMARY_QUALITY"):
            settings.rag.summary_quality = SummaryQuality(os.getenv("RAG_SUMMARY_QUALITY").lower())
        if os.getenv("RAG_RERANK_METHOD"):
            settings.rag.rerank_method = RerankMethod(os.getenv("RAG_RERANK_METHOD").lower())
        if os.getenv("RAG_USE_SUMMARY_CACHE"):
            settings.rag.use_cache = os.getenv("RAG_USE_SUMMARY_CACHE").lower() in ("true", "1", "yes")
        if os.getenv("RAG_MAX_SUMMARY_KEY_POINTS"):
            settings.rag.max_summary_key_points = int(os.getenv("RAG_MAX_SUMMARY_KEY_POINTS"))
        if os.getenv("RAG_TOP_K_CHUNKS"):
            settings.rag.top_k_chunks = int(os.getenv("RAG_TOP_K_CHUNKS"))

        # Cache settings
        if os.getenv("CACHE_VALIDITY_HOURS"):
            settings.cache.validity_hours = int(os.getenv("CACHE_VALIDITY_HOURS"))
        if os.getenv("MAX_CACHE_SIZE"):
            settings.cache.max_size = int(os.getenv("MAX_CACHE_SIZE"))

        # Rate limiting
        if os.getenv("ENABLE_RATE_LIMITING"):
            settings.rate_limit.enabled = os.getenv("ENABLE_RATE_LIMITING").lower() in ("true", "1", "yes")
        if os.getenv("RATE_LIMIT_PER_MINUTE"):
            settings.rate_limit.requests_per_minute = int(os.getenv("RATE_LIMIT_PER_MINUTE"))

        # Retrieval settings
        if os.getenv("USE_FULLTEXT"):
            settings.retrieval.use_fulltext = os.getenv("USE_FULLTEXT").lower() in ("1", "true", "yes")
        if os.getenv("NCBI_API_KEY"):
            settings.retrieval.ncbi_api_key = os.getenv("NCBI_API_KEY")
        if os.getenv("EMAIL"):
            settings.retrieval.email = os.getenv("EMAIL")

        # Logging settings
        if os.getenv("LOG_LEVEL"):
            settings.logging.level = LogLevel(os.getenv("LOG_LEVEL").upper())

        # Environment
        if os.getenv("ENVIRONMENT"):
            settings.environment = Environment(os.getenv("ENVIRONMENT").lower())

        # Security
        if os.getenv("CORS_ORIGINS"):
            settings.security.cors_origins = os.getenv("CORS_ORIGINS").split(",")
        if os.getenv("ENABLE_REQUEST_ID"):
            settings.security.enable_request_id = os.getenv("ENABLE_REQUEST_ID").lower() in ("true", "1", "yes")

        return settings

    @classmethod
    def from_preset(cls, preset_name: str) -> "BioAnalyzerSettings":
        """Load settings from a preset configuration."""
        presets = {
            "fast": {
                "api": {
                    "timeout": 15,
                    "analysis_timeout": 30,
                    "gemini_timeout": 15,
                },
                "rag": {
                    "summary_quality": "fast",
                    "summary_length": "short",
                    "top_k_chunks": 5,
                    "rerank_method": "keyword",
                },
                "cache": {
                    "enabled": True,
                },
            },
            "balanced": {
                "api": {
                    "timeout": 30,
                    "analysis_timeout": 45,
                    "gemini_timeout": 30,
                },
                "rag": {
                    "summary_quality": "balanced",
                    "summary_length": "medium",
                    "top_k_chunks": 10,
                    "rerank_method": "hybrid",
                },
                "cache": {
                    "enabled": True,
                },
            },
            "high_quality": {
                "api": {
                    "timeout": 60,
                    "analysis_timeout": 120,
                    "gemini_timeout": 60,
                },
                "rag": {
                    "summary_quality": "high",
                    "summary_length": "long",
                    "top_k_chunks": 20,
                    "rerank_method": "llm",
                },
                "cache": {
                    "enabled": True,
                },
            },
            "development": {
                "environment": "development",
                "logging": {
                    "level": "DEBUG",
                },
                "cache": {
                    "enabled": True,
                },
            },
            "production": {
                "environment": "production",
                "logging": {
                    "level": "INFO",
                },
                "rate_limit": {
                    "enabled": True,
                    "requests_per_minute": 60,
                },
                "security": {
                    "cors_origins": ["*"],
                    "enable_request_id": True,
                },
            },
        }

        if preset_name not in presets:
            raise ValueError(f"Unknown preset: {preset_name}. Valid presets: {list(presets.keys())}")

        settings = cls()
        preset_data = presets[preset_name]

        # Create update dict with preset values
        update_dict = {"preset": preset_name}
        update_dict.update(preset_data)

        # Use Pydantic's model_validate to properly convert enum values
        # Merge with existing settings
        current_dict = settings.model_dump(exclude_none=True)

        # Deep merge
        def deep_merge(base: dict, override: dict) -> dict:
            result = base.copy()
            for key, value in override.items():
                if key in result and isinstance(result[key], dict) and isinstance(value, dict):
                    result[key] = deep_merge(result[key], value)
                else:
                    result[key] = value
            return result

        merged_dict = deep_merge(current_dict, update_dict)

        # Create new settings with merged data (Pydantic will validate enums)
        return cls.model_validate(merged_dict)

    def merge(self, other: "BioAnalyzerSettings") -> "BioAnalyzerSettings":
        """Merge another settings object into this one (other takes precedence)."""
        self_dict = self.model_dump(exclude_none=True)
        other_dict = other.model_dump(exclude_none=True)

        # Deep merge
        def deep_merge(base: dict, override: dict) -> dict:
            result = base.copy()
            for key, value in override.items():
                if key in result and isinstance(result[key], dict) and isinstance(value, dict):
                    result[key] = deep_merge(result[key], value)
                else:
                    result[key] = value
            return result

        merged = deep_merge(self_dict, other_dict)
        return self.from_dict(merged)

    def apply_to_environment(self):
        """Apply settings to environment variables (for backward compatibility)."""
        # API settings
        os.environ["API_TIMEOUT"] = str(self.api.timeout)
        os.environ["ANALYSIS_TIMEOUT"] = str(self.api.analysis_timeout)
        os.environ["GEMINI_TIMEOUT"] = str(self.api.gemini_timeout)
        os.environ["FRONTEND_TIMEOUT"] = str(self.api.frontend_timeout)
        os.environ["NCBI_RATE_LIMIT_DELAY"] = str(self.api.ncbi_rate_limit_delay)
        os.environ["MAX_CONCURRENT_REQUESTS"] = str(self.api.max_concurrent_requests)

        # LLM settings
        if self.llm.provider:
            os.environ["LLM_PROVIDER"] = self.llm.provider
        if self.llm.model:
            os.environ["LLM_MODEL"] = self.llm.model
        if self.llm.gemini_api_key:
            os.environ["GEMINI_API_KEY"] = self.llm.gemini_api_key
        if self.llm.openai_api_key:
            os.environ["OPENAI_API_KEY"] = self.llm.openai_api_key
        if self.llm.anthropic_api_key:
            os.environ["ANTHROPIC_API_KEY"] = self.llm.anthropic_api_key
        if self.llm.ollama_base_url:
            os.environ["OLLAMA_BASE_URL"] = self.llm.ollama_base_url

        # RAG settings
        if self.rag.summary_provider:
            os.environ["RAG_SUMMARY_PROVIDER"] = self.rag.summary_provider
        if self.rag.summary_model:
            os.environ["RAG_SUMMARY_MODEL"] = self.rag.summary_model
        os.environ["RAG_SUMMARY_LENGTH"] = self.rag.summary_length.value
        os.environ["RAG_SUMMARY_QUALITY"] = self.rag.summary_quality.value
        os.environ["RAG_RERANK_METHOD"] = self.rag.rerank_method.value
        os.environ["RAG_USE_SUMMARY_CACHE"] = str(self.rag.use_cache).lower()
        os.environ["RAG_MAX_SUMMARY_KEY_POINTS"] = str(self.rag.max_summary_key_points)
        os.environ["RAG_TOP_K_CHUNKS"] = str(self.rag.top_k_chunks)

        # Cache settings
        os.environ["CACHE_VALIDITY_HOURS"] = str(self.cache.validity_hours)
        os.environ["MAX_CACHE_SIZE"] = str(self.cache.max_size)

        # Rate limiting
        os.environ["ENABLE_RATE_LIMITING"] = str(self.rate_limit.enabled).lower()
        os.environ["RATE_LIMIT_PER_MINUTE"] = str(self.rate_limit.requests_per_minute)

        # Retrieval settings
        os.environ["USE_FULLTEXT"] = str(self.retrieval.use_fulltext).lower()
        if self.retrieval.ncbi_api_key:
            os.environ["NCBI_API_KEY"] = self.retrieval.ncbi_api_key
        if self.retrieval.email:
            os.environ["EMAIL"] = self.retrieval.email

        # Logging settings
        os.environ["LOG_LEVEL"] = self.logging.level.value

        # Environment
        os.environ["ENVIRONMENT"] = self.environment.value

        # Security
        os.environ["CORS_ORIGINS"] = ",".join(self.security.cors_origins)
        os.environ["ENABLE_REQUEST_ID"] = str(self.security.enable_request_id).lower()


class SettingsManager:
    """Manager for loading and managing settings."""

    DEFAULT_SETTINGS_DIR = Path.home() / ".bioanalyzer"
    DEFAULT_SETTINGS_FILE = DEFAULT_SETTINGS_DIR / "settings.json"

    def __init__(self, settings_file: Optional[Path] = None):
        """Initialize settings manager."""
        self.settings_file = settings_file or self.DEFAULT_SETTINGS_FILE
        self._settings: Optional[BioAnalyzerSettings] = None

    def load(
        self,
        from_file: Optional[Path] = None,
        from_env: bool = True,
        from_preset: Optional[str] = None,
        cli_overrides: Optional[Dict[str, Any]] = None,
    ) -> BioAnalyzerSettings:
        """Load settings from multiple sources with priority: CLI > File > Preset > Env > Defaults."""
        settings = BioAnalyzerSettings()

        if from_preset:
            settings = settings.merge(BioAnalyzerSettings.from_preset(from_preset))

        file_path = from_file or self.settings_file
        if file_path and Path(file_path).exists():
            file_settings = BioAnalyzerSettings.from_file(file_path)
            settings = settings.merge(file_settings)

        if from_env:
            env_settings = BioAnalyzerSettings.from_env()
            settings = settings.merge(env_settings)

        if cli_overrides:
            override_settings = BioAnalyzerSettings.from_dict(cli_overrides)
            settings = settings.merge(override_settings)

        self._settings = settings
        return settings

    def save(
        self,
        settings: Optional[BioAnalyzerSettings] = None,
        file_path: Optional[Path] = None,
        format: Literal["json", "yaml"] = "json",
    ):
        """Save settings to file."""
        settings = settings or self._settings
        if settings is None:
            raise ValueError("No settings to save. Load settings first or provide settings parameter.")

        file_path = file_path or self.settings_file
        settings.to_file(file_path, format=format)
        logger.info(f"Settings saved to {file_path}")

    def get_settings(self) -> BioAnalyzerSettings:
        """Get current settings."""
        if self._settings is None:
            self._settings = self.load()
        return self._settings

    def migrate_settings(self, old_file: Path, new_file: Optional[Path] = None) -> BioAnalyzerSettings:
        """Migrate settings from old format to new format."""
        try:
            if old_file.suffix.lower() in [".yaml", ".yml"]:
                with open(old_file, "r") as f:
                    old_data = yaml.safe_load(f)
            else:
                with open(old_file, "r") as f:
                    old_data = json.load(f)
        except Exception as e:
            raise ValueError(f"Failed to load old settings: {e}")

        new_settings = BioAnalyzerSettings()

        if isinstance(old_data, dict):
            for key, value in old_data.items():
                if key == "api_timeout":
                    new_settings.api.timeout = value
                elif key == "llm_provider":
                    new_settings.llm.provider = value
                elif key == "rag_enabled":
                    new_settings.rag.enabled = value

        if new_file is None:
            new_file = old_file.with_suffix(".new" + old_file.suffix)

        new_settings.to_file(new_file)
        logger.info(f"Settings migrated from {old_file} to {new_file}")

        return new_settings


_settings_manager: Optional[SettingsManager] = None
_settings: Optional[BioAnalyzerSettings] = None


def get_settings_manager() -> SettingsManager:
    """Get global settings manager instance."""
    global _settings_manager
    if _settings_manager is None:
        _settings_manager = SettingsManager()
    return _settings_manager


def load_settings(**kwargs) -> BioAnalyzerSettings:
    """Load settings using global manager."""
    global _settings
    manager = get_settings_manager()
    _settings = manager.load(**kwargs)
    return _settings


def get_settings() -> BioAnalyzerSettings:
    """Get current settings."""
    global _settings
    if _settings is None:
        _settings = load_settings()
    return _settings


def save_settings(settings: Optional[BioAnalyzerSettings] = None, **kwargs):
    """Save settings using global manager."""
    manager = get_settings_manager()
    manager.save(settings, **kwargs)
