import torch
import tiktoken
from typing import List, Dict, Union
import logging
import re

logger = logging.getLogger(__name__)

class AdvancedTextProcessor:
    def __init__(self, model_name: str = "cl100k_base"):
        try:
            self.tokenizer = tiktoken.get_encoding(model_name)
            self.tokenizer_available = True
        except Exception as e:
            logger.warning(f"Failed to load tiktoken model '{model_name}': {e}")
            logger.info("Falling back to basic text processing without tokenization")
            self.tokenizer = None
            self.tokenizer_available = False
    
        # Add special tokens
        self.bos_token_id = 1
        self.eos_token_id = 2
        self.pad_token_id = 0
        self.sep_token_id = 3
    
    def encode_text(self, text: str) -> torch.Tensor:
        """Encode text using tiktoken for better compatibility with modern LLMs"""
        if not self.tokenizer_available:
            # Fallback: return simple character-based encoding
            return torch.tensor([ord(c) for c in text[:100]], dtype=torch.long)
    
        # Add BOS token at start
        tokens = [self.bos_token_id] + self.tokenizer.encode(text)
        return torch.tensor(tokens, dtype=torch.long)

    def decode_tokens(self, tokens: Union[torch.Tensor, List[int]]) -> str:
        """Decode tokens back to text"""
        if not self.tokenizer_available:
            # Fallback: return simple character-based decoding
            try:
                if isinstance(tokens, torch.Tensor):
                    tokens = tokens.tolist()
                return ''.join([chr(int(t)) for t in tokens if 32 <= int(t) <= 126])
            except:
                return "Error decoding response (fallback mode)"
    
        try:
            # Convert tensor to list if needed
            if isinstance(tokens, torch.Tensor):
                if tokens.dim() > 1:  # If tensor has multiple dimensions
                    tokens = tokens.squeeze().tolist()  # Remove extra dimensions
                else:
                    tokens = tokens.tolist()
            elif isinstance(tokens, list) and isinstance(tokens[0], list):
                tokens = tokens[0]  # Take first sequence if list of lists
        
            # Ensure we have a flat list of integers
            if not isinstance(tokens, list):
                tokens = [int(tokens)]
        
            # Filter out special tokens
            tokens = [t for t in tokens if t not in [self.bos_token_id, self.eos_token_id, self.pad_token_id, self.sep_token_id]]
        
            # Convert to integers if needed
            tokens = [int(t) for t in tokens]
        
            return self.tokenizer.decode(tokens)
        except Exception as e:
            logger.error(f"Error decoding tokens: {str(e)}")
            logger.debug(f"Token type: {type(tokens)}")
            logger.debug(f"Token content: {tokens}")
            return "Error decoding response"

    def batch_encode(self, texts: List[str], max_length: int = 512, pad: bool = True) -> torch.Tensor:
        """Batch encode texts with optional padding"""
        if not self.tokenizer_available:
            # Fallback: simple character-based encoding
            encoded = []
            for text in texts:
                tokens = [ord(c) for c in text[:max_length]]
                encoded.append(tokens)
        
            if pad:
                max_len = max(len(x) for x in encoded)
                encoded = [x + [0] * (max_len - len(x)) for x in encoded]
            return torch.tensor(encoded, dtype=torch.long)
    
        encoded = []
        for text in texts:
            # Add BOS token and encode
            tokens = [self.bos_token_id] + self.tokenizer.encode(text)
            # Truncate if needed
            if len(tokens) > max_length:
                tokens = tokens[:max_length]
            encoded.append(tokens)
    
        if pad:
            max_len = max(len(x) for x in encoded)
            encoded = [x + [self.pad_token_id] * (max_len - len(x)) for x in encoded]
        return torch.tensor(encoded, dtype=torch.long)

    def create_attention_mask(self, encoded_texts: torch.Tensor) -> torch.Tensor:
        """Create attention mask for padded sequences"""
        if not self.tokenizer_available:
            # Fallback: assume no padding in fallback mode
            return torch.ones_like(encoded_texts, dtype=torch.float)
    
        return (encoded_texts != self.pad_token_id).float()

    @staticmethod
    def clean_scientific_text(text: str) -> str:
        """Clean scientific text by handling common patterns in academic papers"""
        # Remove reference citations
        text = re.sub(r'\[\d+(?:,\s*\d+)*\]', '', text)
        
        # Remove figure/table references
        text = re.sub(r'(Fig\.|Figure|Table)\s*\d+[A-Za-z]?', '', text)
        
        # Remove URLs
        text = re.sub(r'http[s]?://(?:[a-zA-Z]|[0-9]|[$-_@.&+]|[!*\\(\\),]|(?:%[0-9a-fA-F][0-9a-fA-F]))+', '', text)
        
        # Normalize whitespace
        text = ' '.join(text.split())
        
        return text

    def process_text(self, text: str, max_length: int = 2000) -> str:
        """
        Prepare text for analysis: clean, optionally tokenize/truncate, and return as string.
        Uses tiktoken if available; fallbacks to basic processing.
        """
        # Clean the text first
        cleaned = self.clean_scientific_text(text)
        
        if self.tokenizer_available:
            # Tokenize, truncate to max_length tokens, detokenize back to string
            tokens = self.tokenizer.encode(cleaned)
            if len(tokens) > max_length:
                tokens = tokens[:max_length]
                logger.info(f"Truncated text to {max_length} tokens for analysis.")
            return self.tokenizer.decode(tokens)
        else:
            # Fallback: simple truncation by characters (rough token estimate)
            if len(cleaned) > max_length * 4:  # Avg ~4 chars/token
                cleaned = cleaned[:max_length * 4] + "..."
            return cleaned