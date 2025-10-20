"""
Conversation model for managing chat interactions
"""

import torch
import torch.nn as nn
from typing import Dict, Optional, List
from .attention_model import MicrobialSignatureModel
from app.utils.conversation_memory import ConversationMemory

class ConversationalBugSigModel(nn.Module):
    def __init__(self, base_model: MicrobialSignatureModel, config):
        super().__init__()
        self.base_model = base_model
        self.config = config
        self.memory = ConversationMemory()
        
        # Additional layers for conversation
        self.context_encoder = nn.Linear(config.hidden_size, config.hidden_size)
        self.query_encoder = nn.Linear(config.hidden_size, config.hidden_size)
        self.response_decoder = nn.Linear(config.hidden_size * 2, config.vocab_size)
        
        # Knowledge embedding for BugSigDB-specific information
        self.knowledge_embeddings = nn.Embedding(
            config.knowledge_base_size,  # Size of your knowledge base
            config.hidden_size
        )
        
    def encode_context(self, context_ids: torch.Tensor, attention_mask: Optional[torch.Tensor] = None):
        """Encode conversation context"""
        context_outputs = self.base_model(
            input_ids=context_ids,
            attention_mask=attention_mask
        )
        context_hidden = context_outputs['hidden_states']
        return self.context_encoder(context_hidden)
    
    def encode_query(self, query_ids: torch.Tensor, attention_mask: Optional[torch.Tensor] = None):
        """Encode user query"""
        query_outputs = self.base_model(
            input_ids=query_ids,
            attention_mask=attention_mask
        )
        query_hidden = query_outputs['hidden_states']
        return self.query_encoder(query_hidden)
    
    def generate_response(
        self,
        query_ids: torch.Tensor,
        context_ids: Optional[torch.Tensor] = None,
        knowledge_ids: Optional[torch.Tensor] = None,
        max_length: int = 100,
        temperature: float = 0.7,
        top_p: float = 0.9,
    ) -> Dict:
        """Generate a response given a query and optional context"""
        # Encode query
        query_encoded = self.encode_query(query_ids)
        
        # Encode context if provided
        if context_ids is not None:
            context_encoded = self.encode_context(context_ids)
            combined_encoding = torch.cat([query_encoded, context_encoded], dim=-1)
        else:
            combined_encoding = query_encoded
        
        # Add knowledge embeddings if provided
        if knowledge_ids is not None:
            knowledge_embedded = self.knowledge_embeddings(knowledge_ids)
            combined_encoding = combined_encoding + knowledge_embedded
        
        # Generate response token by token
        response_ids = []
        current_token = torch.tensor([[self.config.start_token_id]], device=query_ids.device)
        
        for _ in range(max_length):
            # Get next token probabilities
            logits = self.response_decoder(combined_encoding)
            
            # Apply temperature and top-p sampling
            logits = logits / temperature
            probs = torch.softmax(logits[:, -1], dim=-1)
            
            # Top-p (nucleus) sampling
            sorted_probs, sorted_indices = torch.sort(probs, descending=True)
            cumsum_probs = torch.cumsum(sorted_probs, dim=-1)
            sorted_indices_to_remove = cumsum_probs > top_p
            sorted_indices_to_remove[..., 1:] = sorted_indices_to_remove[..., :-1].clone()
            sorted_indices_to_remove[..., 0] = 0
            
            indices_to_remove = sorted_indices_to_remove.scatter(1, sorted_indices, sorted_indices_to_remove)
            probs[indices_to_remove] = 0
            probs = probs / probs.sum(dim=-1, keepdim=True)
            
            # Sample next token
            next_token = torch.multinomial(probs, num_samples=1)
            response_ids.append(next_token.item())
            
            # Break if end token is generated
            if next_token.item() == self.config.end_token_id:
                break
            
            # Update current token for next iteration
            current_token = next_token
        
        return {
            'response_ids': torch.tensor(response_ids),
            'attention_weights': None  # Could add attention visualization later
        }
    
    def save_conversation(self, filepath: str):
        """Save conversation history"""
        self.memory.save_to_file(filepath)
    
    def load_conversation(self, filepath: str):
        """Load conversation history"""
        self.memory.load_from_file(filepath)
    
    def add_to_conversation(self, message: str, role: str = 'user'):
        """Add a message to the conversation history"""
        self.memory.add_message(role=role, content=message) 