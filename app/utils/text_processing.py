import torch
import tiktoken
from typing import List, Union
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

        self.bos_token_id = 1
        self.eos_token_id = 2
        self.pad_token_id = 0
        self.sep_token_id = 3

    def encode_text(self, text: str) -> torch.Tensor:
        if not self.tokenizer_available:
            return torch.tensor([ord(c) for c in text[:100]], dtype=torch.long)

        tokens = [self.bos_token_id] + self.tokenizer.encode(text)
        return torch.tensor(tokens, dtype=torch.long)

    def decode_tokens(self, tokens: Union[torch.Tensor, List[int]]) -> str:
        if not self.tokenizer_available:
            try:
                if isinstance(tokens, torch.Tensor):
                    tokens = tokens.tolist()
                return "".join(chr(int(t)) for t in tokens if 32 <= int(t) <= 126)
            except Exception:
                return "Error decoding response (fallback mode)"

        try:
            if isinstance(tokens, torch.Tensor):
                tokens = tokens.squeeze().tolist()
            if isinstance(tokens, list) and tokens and isinstance(tokens[0], list):
                tokens = tokens[0]

            tokens = [
                int(t)
                for t in tokens
                if t
                not in {
                    self.bos_token_id,
                    self.eos_token_id,
                    self.pad_token_id,
                    self.sep_token_id,
                }
            ]
            return self.tokenizer.decode(tokens)
        except Exception as e:
            logger.error(f"Error decoding tokens: {e}")
            return "Error decoding response"

    def batch_encode(
        self, texts: List[str], max_length: int = 512, pad: bool = True
    ) -> torch.Tensor:
        """
        Batch encode texts.

        NOTE:
        Even when pad=False, we still internally pad to the longest
        sequence in the batch to return a valid tensor.
        """
        encoded = []

        if not self.tokenizer_available:
            for text in texts:
                tokens = [ord(c) for c in text[:max_length]]
                encoded.append(tokens)
        else:
            for text in texts:
                tokens = [self.bos_token_id] + self.tokenizer.encode(text)
                if len(tokens) > max_length:
                    tokens = tokens[:max_length]
                encoded.append(tokens)

        # 🔑 CRITICAL FIX: ensure rectangular tensor
        max_len = max(len(seq) for seq in encoded)

        if pad:
            pad_id = self.pad_token_id
        else:
            # minimal padding to make tensor valid
            pad_id = self.pad_token_id

        encoded = [seq + [pad_id] * (max_len - len(seq)) for seq in encoded]

        return torch.tensor(encoded, dtype=torch.long)

    def create_attention_mask(self, encoded_texts: torch.Tensor) -> torch.Tensor:
        if not self.tokenizer_available:
            return torch.ones_like(encoded_texts, dtype=torch.float)

        return (encoded_texts != self.pad_token_id).float()

    @staticmethod
    def clean_scientific_text(text: str) -> str:
        text = re.sub(r"\[\d+(?:,\s*\d+)*\]", "", text)
        text = re.sub(r"(Fig\.|Figure|Table)\s*\d+[A-Za-z]?", "", text)
        text = re.sub(
            r"http[s]?://(?:[a-zA-Z]|[0-9]|[$-_@.&+]|[!*\\(\\),]|(?:%[0-9a-fA-F][0-9a-fA-F]))+",
            "",
            text,
        )
        return " ".join(text.split())

    def process_text(self, text: str, max_length: int = 2000) -> str:
        cleaned = self.clean_scientific_text(text)

        if self.tokenizer_available:
            tokens = self.tokenizer.encode(cleaned)
            if len(tokens) > max_length:
                tokens = tokens[:max_length]
                logger.info(f"Truncated text to {max_length} tokens for analysis.")
            return self.tokenizer.decode(tokens)

        if len(cleaned) > max_length * 4:
            return cleaned[: max_length * 4] + "..."
        return cleaned
