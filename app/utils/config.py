import os
from pathlib import Path
from dotenv import load_dotenv
import google.generativeai as genai
import logging

# Load environment variables from .env file
# Try multiple possible locations for .env file
possible_env_paths = [
    Path(__file__).parents[1] / '.env',  # Original location
    Path('/app/.env'),  # Docker container location
    Path('.env'),  # Current directory
    Path(__file__).parents[2] / '.env',  # Project root
]

env_loaded = False
for env_path in possible_env_paths:
    if env_path.exists():
        load_dotenv(dotenv_path=env_path)
        env_loaded = True
        break

if not env_loaded:
    # Fallback: try loading from current directory
    load_dotenv()

# API Keys
NCBI_API_KEY = os.getenv('NCBI_API_KEY', '')
GEMINI_API_KEY = os.getenv('GEMINI_API_KEY', '')
EMAIL = os.getenv('EMAIL', '')

# Model Configuration
DEFAULT_MODEL = os.getenv('DEFAULT_MODEL', 'gemini')
AVAILABLE_MODELS = []

# Initialize available models
if GEMINI_API_KEY:
    AVAILABLE_MODELS.append('gemini')

def validate_gemini_key():
    """Validate Gemini API key by configuring the client."""
    if not GEMINI_API_KEY:
        return False
    try:
        genai.configure(api_key=GEMINI_API_KEY)
        return True
    except Exception as e:
        print(f"Gemini API key validation failed: {str(e)}")
        return False

def validate_env_vars():
    """Validate that required environment variables are set."""
    missing_vars = []
    
    if not NCBI_API_KEY:
        missing_vars.append('NCBI_API_KEY')
    if not EMAIL:
        missing_vars.append('EMAIL')
    if not GEMINI_API_KEY:
        missing_vars.append('GEMINI_API_KEY')
    
    # Check if at least one AI model is available
    if not AVAILABLE_MODELS:
        missing_vars.append('GEMINI_API_KEY')
    
    if missing_vars:
        print(f"Warning: The following environment variables are missing: {', '.join(missing_vars)}")
        print("Please set them in your .env file or environment.")
    
    return len(missing_vars) == 0

# Call validation when module is imported
validate_env_vars() 

def check_required_vars():
    """Check if all required environment variables are set."""
    missing_vars = []
    
    if not NCBI_API_KEY:
        missing_vars.append('NCBI_API_KEY')
    if not EMAIL:
        missing_vars.append('EMAIL')
    if not GEMINI_API_KEY:
        missing_vars.append('GEMINI_API_KEY')
    
    if missing_vars:
        print("Missing required environment variables:")
        for var in missing_vars:
            print(f"- {var}")
        return False
    
    return True 

# Performance Configuration - balanced timeouts for reliability
API_TIMEOUT = int(os.getenv("API_TIMEOUT", "30"))  # seconds - NCBI API timeout
ANALYSIS_TIMEOUT = int(os.getenv("ANALYSIS_TIMEOUT", "45"))  # seconds - total analysis timeout
GEMINI_TIMEOUT = int(os.getenv("GEMINI_TIMEOUT", "30"))  # seconds - Gemini API timeout
FRONTEND_TIMEOUT = int(os.getenv("FRONTEND_TIMEOUT", "60"))  # seconds - frontend timeout

# Cache Configuration
CACHE_VALIDITY_HOURS = int(os.getenv("CACHE_VALIDITY_HOURS", "24"))
MAX_CACHE_SIZE = int(os.getenv("MAX_CACHE_SIZE", "1000"))  # number of entries

# Rate Limiting
NCBI_RATE_LIMIT_DELAY = float(os.getenv("NCBI_RATE_LIMIT_DELAY", "0.34"))  # seconds
MAX_CONCURRENT_REQUESTS = int(os.getenv("MAX_CONCURRENT_REQUESTS", "3"))

# Retrieval configuration
USE_FULLTEXT = os.getenv('USE_FULLTEXT', '0').lower() in ('1', 'true', 'yes')

# Logging Configuration
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")
LOG_FORMAT = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
LOG_FILE_FORMAT = "%(asctime)s - %(name)s - %(levelname)s - %(funcName)s:%(lineno)d - %(message)s"

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

def setup_logging():
    """Setup comprehensive logging configuration with file rotation."""
    import logging.handlers
    
    # Create formatters
    console_formatter = logging.Formatter(LOG_FORMAT)
    file_formatter = logging.Formatter(LOG_FILE_FORMAT)
    
    # Create handlers
    console_handler = logging.StreamHandler()
    console_handler.setLevel(getattr(logging, LOG_LEVEL.upper()))
    console_handler.setFormatter(console_formatter)
    
    # Main application log handler with rotation
    main_file_handler = logging.handlers.RotatingFileHandler(
        MAIN_LOG_FILE,
        maxBytes=MAX_LOG_SIZE,
        backupCount=MAX_LOG_FILES,
        encoding='utf-8'
    )
    main_file_handler.setLevel(logging.INFO)
    main_file_handler.setFormatter(file_formatter)
    
    # Performance log handler
    perf_file_handler = logging.handlers.RotatingFileHandler(
        PERFORMANCE_LOG_FILE,
        maxBytes=MAX_LOG_SIZE,
        backupCount=MAX_LOG_FILES,
        encoding='utf-8'
    )
    perf_file_handler.setLevel(logging.INFO)
    perf_file_handler.setFormatter(file_formatter)
    
    # Error log handler
    error_file_handler = logging.handlers.RotatingFileHandler(
        ERROR_LOG_FILE,
        maxBytes=MAX_LOG_SIZE,
        backupCount=MAX_LOG_FILES,
        encoding='utf-8'
    )
    error_file_handler.setLevel(logging.ERROR)
    error_file_handler.setFormatter(file_formatter)
    
    # API log handler
    api_file_handler = logging.handlers.RotatingFileHandler(
        API_LOG_FILE,
        maxBytes=MAX_LOG_SIZE,
        backupCount=MAX_LOG_FILES,
        encoding='utf-8'
    )
    api_file_handler.setLevel(logging.INFO)
    api_file_handler.setFormatter(file_formatter)
    
    # Configure root logger
    root_logger = logging.getLogger()
    root_logger.setLevel(logging.INFO)
    
    # Remove existing handlers to avoid duplicates
    for handler in root_logger.handlers[:]:
        root_logger.removeHandler(handler)
    
    # Add all handlers
    root_logger.addHandler(console_handler)
    root_logger.addHandler(main_file_handler)
    root_logger.addHandler(perf_file_handler)
    root_logger.addHandler(error_file_handler)
    root_logger.addHandler(api_file_handler)
    
    # Set specific logger levels
    logging.getLogger('app.api.app').setLevel(logging.INFO)
    logging.getLogger('app.services.data_retrieval').setLevel(logging.INFO)
    logging.getLogger('app.services.cache_manager').setLevel(logging.INFO)
    logging.getLogger('app.models.gemini_qa').setLevel(logging.INFO)
    
    # Reduce noise from external libraries
    logging.getLogger('urllib3').setLevel(logging.WARNING)
    logging.getLogger('requests').setLevel(logging.WARNING)
    logging.getLogger('Bio').setLevel(logging.WARNING)
    
    return root_logger

# Initialize logging when module is imported
logger = setup_logging() 