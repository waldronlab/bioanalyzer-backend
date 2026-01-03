from dataclasses import dataclass, asdict
from typing import Optional, Dict

# ===============================
# 🔬 Model Configuration
# ===============================
@dataclass
class ModelConfig:
    """Configuration for the microbial signature model"""
    
    # Model architecture
    hidden_size: int = 768
    num_hidden_layers: int = 6
    num_attention_heads: int = 12
    intermediate_size: int = 3072
    hidden_dropout_prob: float = 0.1
    attention_probs_dropout_prob: float = 0.1
    max_position_embeddings: int = 512
    
    # Vocabulary and tokenization
    vocab_size: int = 50257  # GPT-2 vocabulary size
    pad_token_id: int = 0
    
    # Task-specific settings
    num_sequencing_types: int = 4
    num_body_sites: int = 10
    
    # Training settings
    batch_size: int = 32
    learning_rate: float = 5e-5
    weight_decay: float = 0.01
    warmup_steps: int = 1000
    max_steps: int = 100000
    gradient_accumulation_steps: int = 1
    max_grad_norm: float = 1.0
    
    # Regularization
    dropout: float = 0.1
    
    # Optimization
    optimizer: str = "adamw"
    scheduler: str = "linear"
    
    # Hardware
    device: str = "cuda"  # or "cpu"
    fp16: bool = False
    
    # Logging and checkpointing
    logging_steps: int = 100
    save_steps: int = 1000
    eval_steps: int = 1000
    
    def __post_init__(self):
        """Validate configuration after initialization"""
        assert self.hidden_size % self.num_attention_heads == 0, \
            "Hidden size must be divisible by number of attention heads"
        assert self.max_position_embeddings <= 512, \
            "Position embeddings limited to 512 for efficiency"


# ===============================
# ⚙️ Service / Runtime Configuration
# ===============================
@dataclass
class ServiceConfig:
    """Configuration for backend, frontend, and API communication"""

    # Backend API settings
    backend_port: int = 8000
    backend_host: str = "0.0.0.0"

    # Frontend app settings
    frontend_base_url: str = "http://localhost:8000"
    analysis_timeout_ms: int = 60000  # 60s (default for frontend)
    retry_attempts: int = 3

    # External APIs
    ncbi_api_url: str = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils"
    ncbi_api_timeout: int = 60
    ncbi_api_key: Optional[str] = None

    # Unified QA model API (Google Gemini / Vertex / etc.)
    unifiedqa_model: str = "google/unifiedqa-v2-t5-large"
    unifiedqa_api_key: Optional[str] = None
    unifiedqa_timeout: int = 60

    # Security / SSL
    verify_ssl: bool = True

    # Logging
    log_level: str = "INFO"

    def to_dict(self) -> Dict:
        return asdict(self)


# ===============================
# 🧩 Runtime Config Helper
# ===============================
def get_runtime_config() -> Dict:
    """Combine model + service configuration for API endpoint."""
    model_cfg = ModelConfig()
    service_cfg = ServiceConfig()
    return {
        "model": model_cfg.__dict__,
        "frontend": {
            "base_url": service_cfg.frontend_base_url,
            "timeout": service_cfg.analysis_timeout_ms,
        },
        "backend": {
            "port": service_cfg.backend_port,
            "host": service_cfg.backend_host,
        },
        "external": {
            "ncbi_api_url": service_cfg.ncbi_api_url,
            "ncbi_api_timeout": service_cfg.ncbi_api_timeout,
        },
    }
