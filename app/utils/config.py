import os
from pathlib import Path
import logging
from typing import List, Optional
from .credential_masking import mask_exception_message, mask_string
from app.core.settings import get_settings

try:
    from dotenv import load_dotenv  # type: ignore
except ImportError:

    def load_dotenv(*args: object, **kwargs: object) -> None:  # type: ignore[no-redef]
        """Fallback when python-dotenv is not installed."""
        logger = logging.getLogger(__name__)
        logger.warning(
            "python-dotenv not installed; .env files will not be auto-loaded. "
            "Install it with 'pip install python-dotenv' for local development."
        )


def get_genai():
    try:
        import google.generativeai as genai
        return genai
    except ImportError:
        raise RuntimeError(
            "google-generativeai is not installed. "
            "Install with: pip install google-generativeai"
        )

possible_env_paths = [
    Path(__file__).parents[1] / ".env",  # Original location
    Path("/app/.env"),  # Docker container location
    Path(".env"),  # Current directory
    Path(__file__).parents[2] / ".env",  # Project root
]

env_loaded = False
for env_path in possible_env_paths:
    if env_path.exists():
        load_dotenv(dotenv_path=env_path)
        env_loaded = True
        break

if not env_loaded:
    load_dotenv()

NCBI_API_KEY = os.getenv("NCBI_API_KEY", "")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")
EMAIL = os.getenv("EMAIL", "")

LLM_PROVIDER = os.getenv("LLM_PROVIDER", "").lower() or None
LLM_MODEL = os.getenv("LLM_MODEL", "") or None

DEFAULT_MODEL = os.getenv("DEFAULT_MODEL", "gemini")
AVAILABLE_MODELS: List[str] = []

if GEMINI_API_KEY:
    AVAILABLE_MODELS.append("gemini")
if OPENAI_API_KEY:
    AVAILABLE_MODELS.append("openai")
if ANTHROPIC_API_KEY:
    AVAILABLE_MODELS.append("anthropic")
if os.getenv("OLLAMA_BASE_URL") or os.getenv("OLLAMA_HOST"):
    AVAILABLE_MODELS.append("ollama")


def validate_gemini_key() -> bool:
    """Validate Gemini API key by configuring the client."""
    if not GEMINI_API_KEY:
        return False
    try:
        genai.configure(api_key=GEMINI_API_KEY)
        return True
    except (ValueError, AttributeError) as e:
        safe_error = mask_exception_message(e)
        print(f"Gemini API key validation failed: {safe_error}")
        return False
    except Exception as e:
        # Catch-all for unexpected errors during configuration
        safe_error = mask_exception_message(e)
        print(f"Unexpected error validating Gemini key: {safe_error}")
        return False


def validate_env_vars() -> bool:
    """Validate that required environment variables are set."""
    missing_vars: List[str] = []

    if not NCBI_API_KEY:
        missing_vars.append("NCBI_API_KEY")
    if not EMAIL:
        missing_vars.append("EMAIL")
    if not GEMINI_API_KEY:
        missing_vars.append("GEMINI_API_KEY")

    # At least one LLM provider must be available
    if not AVAILABLE_MODELS:
        missing_vars.append("GEMINI_API_KEY")

    if missing_vars:
        print(
            f"Warning: Missing environment variables: {', '.join(missing_vars)}"
        )
        print("Set them in your .env file or environment.")

    return len(missing_vars) == 0


# Validate on import
validate_env_vars()


def check_required_vars() -> bool:
    """Check if all required environment variables are set."""
    missing_vars: List[str] = []

    if not NCBI_API_KEY:
        missing_vars.append("NCBI_API_KEY")
    if not EMAIL:
        missing_vars.append("EMAIL")
    if not GEMINI_API_KEY:
        missing_vars.append("GEMINI_API_KEY")

    if missing_vars:
        print("Missing required environment variables:")
        for var in missing_vars:
            print(f"- {var}")
        return False

    return True


# Performance Configuration - balanced timeouts for reliability
API_TIMEOUT = int(os.getenv("API_TIMEOUT", "30"))  # seconds - NCBI API timeout
ANALYSIS_TIMEOUT = int(
    os.getenv("ANALYSIS_TIMEOUT", "45")
)  # seconds - total analysis timeout
GEMINI_TIMEOUT = int(os.getenv("GEMINI_TIMEOUT", "30"))  # seconds - Gemini API timeout
FRONTEND_TIMEOUT = int(
    os.getenv("FRONTEND_TIMEOUT", "60")
)  # seconds - frontend timeout

# RAG Configuration - Advanced RAG with Contextual Summarization
RAG_SUMMARY_PROVIDER = (
    os.getenv("RAG_SUMMARY_PROVIDER", "").lower() or None
)  # Provider for summarization LLM
RAG_SUMMARY_MODEL = (
    os.getenv("RAG_SUMMARY_MODEL", "") or None
)  # Model for summarization (can be cheaper/faster)
RAG_SUMMARY_LENGTH = os.getenv(
    "RAG_SUMMARY_LENGTH", "medium"
)  # "short", "medium", "long"
RAG_SUMMARY_QUALITY = os.getenv(
    "RAG_SUMMARY_QUALITY", "balanced"
)  # "fast", "balanced", "high"
RAG_RERANK_METHOD = os.getenv(
    "RAG_RERANK_METHOD", "hybrid"
)  # "keyword", "llm", "hybrid"
RAG_USE_SUMMARY_CACHE = os.getenv("RAG_USE_SUMMARY_CACHE", "true").lower() in (
    "true",
    "1",
    "yes",
)
RAG_MAX_SUMMARY_KEY_POINTS = int(os.getenv("RAG_MAX_SUMMARY_KEY_POINTS", "5"))
RAG_TOP_K_CHUNKS = int(
    os.getenv("RAG_TOP_K_CHUNKS", "10")
)  # Number of top chunks to use after re-ranking

# Cache Configuration
CACHE_VALIDITY_HOURS = int(os.getenv("CACHE_VALIDITY_HOURS", "24"))
MAX_CACHE_SIZE = int(os.getenv("MAX_CACHE_SIZE", "1000"))  # number of entries

# Rate Limiting
NCBI_RATE_LIMIT_DELAY = float(os.getenv("NCBI_RATE_LIMIT_DELAY", "0.34"))  # seconds
MAX_CONCURRENT_REQUESTS = int(os.getenv("MAX_CONCURRENT_REQUESTS", "3"))

# Retrieval configuration
USE_FULLTEXT = os.getenv("USE_FULLTEXT", "0").lower() in ("1", "true", "yes")

# Production Configuration
ENVIRONMENT = os.getenv("ENVIRONMENT", "development").lower()
CORS_ORIGINS = (
    os.getenv("CORS_ORIGINS", "*").split(",") if os.getenv("CORS_ORIGINS") else ["*"]
)
ENABLE_RATE_LIMITING = os.getenv("ENABLE_RATE_LIMITING", "true").lower() in (
    "true",
    "1",
    "yes",
)
RATE_LIMIT_PER_MINUTE = int(os.getenv("RATE_LIMIT_PER_MINUTE", "60"))
ENABLE_REQUEST_ID = os.getenv("ENABLE_REQUEST_ID", "true").lower() in (
    "true",
    "1",
    "yes",
)

# Logging Configuration
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")
LOG_FORMAT = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
LOG_FILE_FORMAT = (
    "%(asctime)s - %(name)s - %(levelname)s - %(funcName)s:%(lineno)d - %(message)s"
)

# Logging paths
LOG_DIR = Path("logs")
LOG_DIR.mkdir(exist_ok=True)

# Main application log
MAIN_LOG_FILE = LOG_DIR / "bioanalyzer.log"
# Performance log for PMID queries
PERFORMANCE_LOG_FILE = LOG_DIR / "performance.log"
# Error log for detailed error tracking
ERROR_LOG_FILE = LOG_DIR / "errors.log"
# API log for external API calls
API_LOG_FILE = LOG_DIR / "api_calls.log"

# Log rotation settings
MAX_LOG_SIZE = 10 * 1024 * 1024  # 10MB
MAX_LOG_FILES = 5  # Keep 5 rotated log files


def setup_logging() -> logging.Logger:
    """Configure logging with file rotation.

    Falls back to console-only logging if file handlers can't be created.
    """
    import logging.handlers

    # Create formatters
    console_formatter = logging.Formatter(LOG_FORMAT)
    file_formatter = logging.Formatter(LOG_FILE_FORMAT)

    # Create handlers
    console_handler = logging.StreamHandler()
    console_handler.setLevel(getattr(logging, LOG_LEVEL.upper()))
    console_handler.setFormatter(console_formatter)

    # Configure root logger
    root_logger = logging.getLogger()
    root_logger.setLevel(logging.INFO)

    # Remove existing handlers to avoid duplicates
    for handler in root_logger.handlers[:]:
        root_logger.removeHandler(handler)

    # Try to create file handlers, but handle permission errors gracefully
    file_handlers_created: List[str] = []

    try:
        # Main application log handler with rotation
        main_file_handler = logging.handlers.RotatingFileHandler(
            MAIN_LOG_FILE,
            maxBytes=MAX_LOG_SIZE,
            backupCount=MAX_LOG_FILES,
            encoding="utf-8",
        )
        main_file_handler.setLevel(logging.INFO)
        main_file_handler.setFormatter(file_formatter)
        root_logger.addHandler(main_file_handler)
        file_handlers_created.append("main")
    except (PermissionError, OSError) as e:
        # Fall back to console-only logging if file handlers fail
        pass

    try:
        # Performance log handler
        perf_file_handler = logging.handlers.RotatingFileHandler(
            PERFORMANCE_LOG_FILE,
            maxBytes=MAX_LOG_SIZE,
            backupCount=MAX_LOG_FILES,
            encoding="utf-8",
        )
        perf_file_handler.setLevel(logging.INFO)
        perf_file_handler.setFormatter(file_formatter)
        root_logger.addHandler(perf_file_handler)
        file_handlers_created.append("performance")
    except (PermissionError, OSError) as e:
        pass

    try:
        # Error log handler
        error_file_handler = logging.handlers.RotatingFileHandler(
            ERROR_LOG_FILE,
            maxBytes=MAX_LOG_SIZE,
            backupCount=MAX_LOG_FILES,
            encoding="utf-8",
        )
        error_file_handler.setLevel(logging.ERROR)
        error_file_handler.setFormatter(file_formatter)
        root_logger.addHandler(error_file_handler)
        file_handlers_created.append("error")
    except (PermissionError, OSError) as e:
        pass

    try:
        # API log handler
        api_file_handler = logging.handlers.RotatingFileHandler(
            API_LOG_FILE,
            maxBytes=MAX_LOG_SIZE,
            backupCount=MAX_LOG_FILES,
            encoding="utf-8",
        )
        api_file_handler.setLevel(logging.INFO)
        api_file_handler.setFormatter(file_formatter)
        root_logger.addHandler(api_file_handler)
        file_handlers_created.append("api")
    except (PermissionError, OSError) as e:
        pass

    # Always add console handler (it should always work)
    root_logger.addHandler(console_handler)

    # Set specific logger levels
    logging.getLogger("app.api.app").setLevel(logging.INFO)
    logging.getLogger("app.services.data_retrieval").setLevel(logging.INFO)
    logging.getLogger("app.services.cache_manager").setLevel(logging.INFO)
    logging.getLogger("app.models.gemini_qa").setLevel(logging.INFO)

    # Reduce noise from external libraries
    logging.getLogger("urllib3").setLevel(logging.WARNING)
    logging.getLogger("requests").setLevel(logging.WARNING)
    logging.getLogger("Bio").setLevel(logging.WARNING)

    return root_logger


logger = setup_logging()

# ---------------------------------------------------------------------------
# Bridge to structured settings (app.core.settings)
# This keeps app.core.settings as the single source of truth while preserving
# existing config module attributes used across the codebase.
# ---------------------------------------------------------------------------
try:
    _settings = get_settings()

    # API / timeout settings
    API_TIMEOUT = _settings.api.timeout
    ANALYSIS_TIMEOUT = _settings.api.analysis_timeout
    GEMINI_TIMEOUT = _settings.api.gemini_timeout
    FRONTEND_TIMEOUT = _settings.api.frontend_timeout
    NCBI_RATE_LIMIT_DELAY = _settings.api.ncbi_rate_limit_delay
    MAX_CONCURRENT_REQUESTS = _settings.api.max_concurrent_requests

    # LLM config
    if _settings.llm.provider:
        LLM_PROVIDER = _settings.llm.provider
    if _settings.llm.model:
        LLM_MODEL = _settings.llm.model

    # RAG settings
    RAG_SUMMARY_PROVIDER = _settings.rag.summary_provider or RAG_SUMMARY_PROVIDER
    RAG_SUMMARY_MODEL = _settings.rag.summary_model or RAG_SUMMARY_MODEL
    RAG_SUMMARY_LENGTH = _settings.rag.summary_length.value
    RAG_SUMMARY_QUALITY = _settings.rag.summary_quality.value
    RAG_RERANK_METHOD = _settings.rag.rerank_method.value
    RAG_USE_SUMMARY_CACHE = _settings.rag.use_cache
    RAG_MAX_SUMMARY_KEY_POINTS = _settings.rag.max_summary_key_points
    RAG_TOP_K_CHUNKS = _settings.rag.top_k_chunks

    # Cache settings
    CACHE_VALIDITY_HOURS = _settings.cache.validity_hours
    MAX_CACHE_SIZE = _settings.cache.max_size

    # Retrieval settings
    USE_FULLTEXT = _settings.retrieval.use_fulltext
    if _settings.retrieval.ncbi_api_key:
        NCBI_API_KEY = _settings.retrieval.ncbi_api_key
    if _settings.retrieval.email:
        EMAIL = _settings.retrieval.email

    # Security / environment
    ENVIRONMENT = _settings.environment.value
    CORS_ORIGINS = _settings.security.cors_origins
    ENABLE_REQUEST_ID = _settings.security.enable_request_id

    # Rate limiting
    ENABLE_RATE_LIMITING = _settings.rate_limit.enabled
    RATE_LIMIT_PER_MINUTE = _settings.rate_limit.requests_per_minute

    # Logging
    LOG_LEVEL = _settings.logging.level.value
except Exception:
    # Fail gracefully; fall back to env-based values defined above
    pass

