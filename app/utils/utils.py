import os
import json
import logging
import hashlib
from pathlib import Path
from typing import Dict, List, Union, Any
from dataclasses import dataclass, field

try:
    from dotenv import load_dotenv  # type: ignore
except ImportError:  # pragma: no cover - safety net for bare installs

    def load_dotenv(*args, **kwargs):  # type: ignore[no-redef]
        logger = logging.getLogger(__name__)
        logger.warning(
            "python-dotenv not installed. Install with 'pip install python-dotenv' for local development."
        )


load_dotenv()

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Resolve the project base directory once at import time.
# Inside Docker the layout is always /app/…; locally it is the repo root.
# Using an absolute base means Config never tries to create directories
# relative to whatever the current working directory happens to be, which
# was the root cause of the PermissionError seen when the container ran as
# a non-root UID that did not own /app.
# ---------------------------------------------------------------------------
_BASE_DIR = Path(os.environ.get("APP_BASE_DIR", "/app"))


@dataclass
class Config:
    """Configuration class for the project."""

    CACHE_DIR: Path = field(default_factory=lambda: _BASE_DIR / "cache")
    EMAIL: str = "your.email@example.com"
    NCBI_API_KEY: str = ""
    MAX_RETRIES: int = 3
    RETRY_DELAY: int = 1
    BATCH_SIZE: int = 32
    NUM_EPOCHS: int = 10
    LEARNING_RATE: float = 1e-4
    MODEL_DIR: Path = field(default_factory=lambda: _BASE_DIR / "models")
    DATA_DIR: Path = field(default_factory=lambda: _BASE_DIR / "data")
    MAX_LENGTH: int = 512

    def __post_init__(self):
        """Create necessary directories if they don't already exist."""
        for directory in [self.CACHE_DIR, self.MODEL_DIR, self.DATA_DIR]:
            try:
                directory.mkdir(parents=True, exist_ok=True)
            except PermissionError:
                # Directories were pre-created by the Docker build with open
                # permissions; a PermissionError here means we are in a
                # read-only or restricted environment.  Log and continue rather
                # than crashing the whole process.
                logger.warning(
                    "Could not create directory %s — it may already exist or "
                    "the process lacks write permission. Continuing anyway.",
                    directory,
                )


def create_cache_key(prefix: str, identifier: str) -> str:
    """Create cache key for storing retrieved data."""
    return f"{prefix}_{identifier}"


def save_json(data: Any, filepath: Path) -> None:
    """Save data to JSON file."""
    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def load_json(filepath: Path) -> Any:
    """Load data from JSON file."""
    with open(filepath, "r", encoding="utf-8") as f:
        return json.load(f)


def validate_pmid(pmid: str) -> bool:
    """Validate PMID format."""
    return pmid.isdigit()


def get_sequencing_types() -> List[str]:
    """Get list of sequencing types."""
    return [
        "16S rRNA",
        "Shotgun metagenomics",
        "Metatranscriptomics",
        "ITS",
        "Other amplicon",
        "Culture-based",
        "Other",
    ]


def get_body_sites() -> List[str]:
    """Get list of body sites."""
    return ["Gut", "Oral", "Skin", "Respiratory tract", "Urogenital", "Blood", "Other"]


def format_prediction_output(
    pmid: str,
    has_signature: bool,
    signature_probability: float,
    sequencing_type: str,
    metadata: Dict = None,
) -> Dict:
    """Format prediction output."""
    output = {
        "pmid": pmid,
        "has_signature": has_signature,
        "signature_probability": signature_probability,
        "sequencing_type": sequencing_type,
    }

    if metadata:
        output["metadata"] = metadata

    return output


config = Config()