import re
import logging
from typing import Dict, List, Union, Tuple
import numpy as np
import torch
from transformers import AutoTokenizer, AutoModel
from app.utils.utils import config

logger = logging.getLogger(__name__)

class TextPreprocessor:
    """Class for text preprocessing and embedding generation."""
    
    def __init__(self, model_name: str = "allenai/scibert_scivocab_uncased"):
        """Initialize the preprocessor with a SciBERT model.
        
        Args:
            model_name: Name of the pretrained model to use
        """
        try:
            self.tokenizer = AutoTokenizer.from_pretrained(model_name)
            self.model = AutoModel.from_pretrained(model_name)
            self.model_available = True
            print(f"Successfully loaded model: {model_name}")
        except Exception as e:
            print(f"Warning: Failed to load model '{model_name}': {e}")
            print("Falling back to basic text processing without ML models")
            self.tokenizer = None
            self.model = None
            self.model_available = False
        
        # Move model to GPU if available
        self.device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
        if self.model_available:
            self.model = self.model.to(self.device)
        
    def clean_text(self, text: str) -> str:
        """Clean and normalize text.
        
        Args:
            text: Input text
            
        Returns:
            Cleaned text
        """
        # Convert to lowercase
        text = text.lower()
        
        # Remove special characters and extra whitespace
        text = re.sub(r'[^\w\s]', ' ', text)
        text = re.sub(r'\s+', ' ', text)
        
        # Remove URLs
        text = re.sub(r'http\S+|www\S+|https\S+', '', text)
        
        return text.strip()
        
    def combine_paper_text(self, metadata: Dict) -> str:
        """Combine different text fields from paper metadata.
        
        Args:
            metadata: Paper metadata dictionary
            
        Returns:
            Combined text
        """
        text_parts = [
            metadata.get("title", ""),
            metadata.get("abstract", ""),
            " ".join(metadata.get("mesh_terms", [])),
        ]
        
        return " ".join(text_parts)
        
    @torch.no_grad()
    def generate_embeddings(self, texts: List[str]) -> torch.Tensor:
        """Generate SciBERT embeddings for a list of texts.
        
        Args:
            texts: List of input texts
            
        Returns:
            Tensor of embeddings
        """
        if not self.model_available:
            # Fallback: return simple TF-IDF like features
            print("Warning: Using fallback embedding generation (no ML model available)")
            # Create simple feature vectors based on text length and word counts
            features = []
            for text in texts:
                words = text.split()
                feature_vector = [
                    len(text),  # text length
                    len(words),  # word count
                    len(set(words)),  # unique word count
                    sum(len(word) for word in words),  # total character count
                ]
                features.append(feature_vector)
            
            # Convert to tensor and pad to consistent size
            max_len = max(len(f) for f in features)
            padded_features = [f + [0] * (max_len - len(f)) for f in features]
            return torch.tensor(padded_features, dtype=torch.float)
        
        # Tokenize texts
        encoded = self.tokenizer(
            texts,
            padding=True,
            truncation=True,
            max_length=config.MAX_LENGTH,
            return_tensors="pt"
        )
        
        # Move inputs to device
        input_ids = encoded["input_ids"].to(self.device)
        attention_mask = encoded["attention_mask"].to(self.device)
        
        # Generate embeddings
        outputs = self.model(
            input_ids=input_ids,
            attention_mask=attention_mask
        )
        
        # Use [CLS] token embeddings as document representations
        embeddings = outputs.last_hidden_state[:, 0, :]
        
        return embeddings.cpu()
        
    def prepare_features(
        self,
        metadata: Dict,
        full_text: str = None
    ) -> Tuple[torch.Tensor, Dict]:
        """Prepare features for model input.
        
        Args:
            metadata: Paper metadata dictionary
            full_text: Optional full text content
            
        Returns:
            Tuple of (embeddings tensor, additional features dictionary)
        """
        # Combine and clean text
        text = self.combine_paper_text(metadata)
        if full_text:
            text += " " + full_text
        text = self.clean_text(text)
        
        # Generate embeddings
        embeddings = self.generate_embeddings([text])[0]
        
        # Extract additional features
        additional_features = {
            "has_full_text": 1 if full_text else 0,
            "publication_year": int(metadata.get("year", 0)) if metadata.get("year", "").isdigit() else 0,
            "is_research_article": 1 if "Journal Article" in metadata.get("publication_types", []) else 0
        }
        
        return embeddings, additional_features
        
    def prepare_batch(
        self,
        metadata_list: List[Dict],
        full_texts: List[str] = None
    ) -> Tuple[torch.Tensor, List[Dict]]:
        """Prepare a batch of papers for model input.
        
        Args:
            metadata_list: List of paper metadata dictionaries
            full_texts: Optional list of full text contents
            
        Returns:
            Tuple of (batch embeddings tensor, list of additional features dictionaries)
        """
        if full_texts is None:
            full_texts = [None] * len(metadata_list)
            
        texts = []
        additional_features_list = []
        
        for metadata, full_text in zip(metadata_list, full_texts):
            # Combine and clean text
            text = self.combine_paper_text(metadata)
            if full_text:
                text += " " + full_text
            text = self.clean_text(text)
            texts.append(text)
            
            # Extract additional features
            additional_features = {
                "has_full_text": 1 if full_text else 0,
                "publication_year": int(metadata.get("year", 0)) if metadata.get("year", "").isdigit() else 0,
                "is_research_article": 1 if "Journal Article" in metadata.get("publication_types", []) else 0
            }
            additional_features_list.append(additional_features)
            
        # Generate embeddings for the batch
        embeddings = self.generate_embeddings(texts)
        
        return embeddings, additional_features_list 