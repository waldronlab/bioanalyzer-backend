import os
import json
import logging
import hashlib
from pathlib import Path
from typing import Dict, List, Union, Any
from dotenv import load_dotenv
from dataclasses import dataclass

# Load environment variables
load_dotenv()

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

@dataclass
class Config:
    """Configuration class for the project."""
    CACHE_DIR: Path = Path("cache")
    EMAIL: str = "your.email@example.com"  # Replace with your email for NCBI
    NCBI_API_KEY: str = ""  # Optional: Add your NCBI API key here
    MAX_RETRIES: int = 3
    RETRY_DELAY: int = 1
    BATCH_SIZE: int = 32
    NUM_EPOCHS: int = 10
    LEARNING_RATE: float = 1e-4
    MODEL_DIR = Path('models')
    DATA_DIR = Path('data')
    
    # Model parameters
    MAX_LENGTH = 512
    
    def __post_init__(self):
        """Create necessary directories."""
        for directory in [self.CACHE_DIR, self.MODEL_DIR, self.DATA_DIR]:
            directory.mkdir(exist_ok=True)

def create_cache_key(prefix: str, identifier: str) -> str:
    """Create a cache key for storing retrieved data.
    
    Args:
        prefix: Type of data being cached
        identifier: Unique identifier (e.g., PMID)
        
    Returns:
        Cache key string
    """
    return f"{prefix}_{identifier}"

def save_json(data: Any, filepath: Path) -> None:
    """Save data to JSON file.
    
    Args:
        data: Data to save
        filepath: Path to save to
    """
    with open(filepath, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

def load_json(filepath: Path) -> Any:
    """Load data from JSON file.
    
    Args:
        filepath: Path to load from
        
    Returns:
        Loaded data
    """
    with open(filepath, 'r', encoding='utf-8') as f:
        return json.load(f)

def validate_pmid(pmid: str) -> bool:
    """Validate PMID format.
    
    Args:
        pmid: PubMed ID to validate
    
    Returns:
        True if valid, False otherwise
    """
    return pmid.isdigit()

def get_sequencing_types() -> List[str]:
    """Get list of sequencing types.
    
    Returns:
        List of sequencing type strings
    """
    return [
        "16S rRNA",
        "Shotgun metagenomics",
        "Metatranscriptomics",
        "ITS",
        "Other amplicon",
        "Culture-based",
        "Other"
    ]

def get_body_sites() -> List[str]:
    """Get list of body sites.
    
    Returns:
        List of body site strings
    """
    return [
        "Gut",
        "Oral",
        "Skin",
        "Respiratory tract",
        "Urogenital",
        "Blood",
        "Other"
    ]

def format_prediction_output(
    pmid: str,
    has_signature: bool,
    signature_probability: float,
    sequencing_type: str,
    metadata: Dict = None
) -> Dict:
    """Format prediction output.
    
    Args:
        pmid: PubMed ID
        has_signature: Whether paper has microbial signatures
        signature_probability: Confidence in signature prediction
        sequencing_type: Predicted sequencing type
        metadata: Additional metadata
        
    Returns:
        Formatted prediction dictionary
    """
    output = {
        "pmid": pmid,
        "has_signature": has_signature,
        "signature_probability": signature_probability,
        "sequencing_type": sequencing_type
    }
    
    if metadata:
        output["metadata"] = metadata
        
    return output

# Initialize configuration
config = Config() 