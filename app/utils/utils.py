import json
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List

try:
    from dotenv import load_dotenv  # type: ignore
except ImportError:  # pragma: no cover - safety net for bare installs

    def load_dotenv(*args, **kwargs):  # type: ignore[no-redef]
        logger = logging.getLogger(__name__)
        logger.warning("python-dotenv not installed. Install with 'pip install python-dotenv' for local development.")


load_dotenv()

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)


@dataclass
class Config:
    """Configuration class for the project."""

    CACHE_DIR: Path = Path("cache")
    EMAIL: str = "your.email@example.com"
    NCBI_API_KEY: str = ""
    MAX_RETRIES: int = 3
    RETRY_DELAY: int = 1
    BATCH_SIZE: int = 32
    NUM_EPOCHS: int = 10
    LEARNING_RATE: float = 1e-4
    MODEL_DIR = Path("models")
    DATA_DIR = Path("data")
    MAX_LENGTH = 512

    def __post_init__(self):
        """Create necessary directories."""
        for directory in [self.CACHE_DIR, self.MODEL_DIR, self.DATA_DIR]:
            directory.mkdir(exist_ok=True)


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
    pmid: str, has_signature: bool, signature_probability: float, sequencing_type: str, metadata: Dict = None
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
