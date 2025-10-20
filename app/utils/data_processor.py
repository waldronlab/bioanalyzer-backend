import torch
from torch.utils.data import Dataset, DataLoader
from typing import List, Dict, Optional
import json
import pandas as pd
from .text_processing import AdvancedTextProcessor, clean_scientific_text

class BugSigConversationDataset(Dataset):
    def __init__(
        self,
        conversations: List[Dict],
        knowledge_base: pd.DataFrame,
        text_processor: AdvancedTextProcessor,
        max_length: int = 512
    ):
        self.conversations = conversations
        self.knowledge_base = knowledge_base
        self.text_processor = text_processor
        self.max_length = max_length
        
        # Create knowledge index
        self.knowledge_index = self._create_knowledge_index()
        
    def _create_knowledge_index(self) -> Dict[str, int]:
        """Create an index mapping keywords to knowledge base entries"""
        index = {}
        for idx, row in self.knowledge_base.iterrows():
            # Index by keywords, paper titles, and other relevant fields
            keywords = set(row.get('keywords', '').lower().split())
            title_words = set(row.get('title', '').lower().split())
            for word in keywords.union(title_words):
                if word not in index:
                    index[word] = []
                index[word].append(idx)
        return index
    
    def _find_relevant_knowledge(self, query: str) -> List[int]:
        """Find relevant knowledge base entries for a query"""
        query_words = set(query.lower().split())
        relevant_indices = set()
        
        for word in query_words:
            if word in self.knowledge_index:
                relevant_indices.update(self.knowledge_index[word])
                
        return list(relevant_indices)[:5]  # Limit to top 5 most relevant entries
    
    def _prepare_conversation_input(
        self,
        query: str,
        context: Optional[str] = None,
        knowledge_indices: Optional[List[int]] = None
    ) -> Dict[str, torch.Tensor]:
        """Prepare model inputs from conversation data"""
        # Clean and encode query
        query_clean = clean_scientific_text(query)
        query_encoded = self.text_processor.encode_text(query_clean)
        
        # Pad or truncate query to max_length
        query_padded = torch.zeros(self.max_length, dtype=torch.long)
        query_len = min(len(query_encoded), self.max_length)
        query_padded[:query_len] = query_encoded[:query_len]
        query_mask = torch.zeros(self.max_length, dtype=torch.bool)
        query_mask[:query_len] = True
        
        # Prepare context if available
        if context:
            context_clean = clean_scientific_text(context)
            context_encoded = self.text_processor.encode_text(context_clean)
            context_padded = torch.zeros(self.max_length, dtype=torch.long)
            context_len = min(len(context_encoded), self.max_length)
            context_padded[:context_len] = context_encoded[:context_len]
            context_mask = torch.zeros(self.max_length, dtype=torch.bool)
            context_mask[:context_len] = True
        else:
            # Return empty tensors instead of None
            context_padded = torch.zeros(self.max_length, dtype=torch.long)
            context_mask = torch.zeros(self.max_length, dtype=torch.bool)
            
        # Prepare knowledge if available
        if knowledge_indices:
            knowledge_texts = [
                self.knowledge_base.iloc[idx]['text']
                for idx in knowledge_indices
            ]
            knowledge_clean = [clean_scientific_text(text) for text in knowledge_texts]
            knowledge_encoded = self.text_processor.batch_encode(knowledge_clean)
            # Pad each knowledge item
            knowledge_padded = torch.zeros(len(knowledge_indices), self.max_length, dtype=torch.long)
            knowledge_mask = torch.zeros(len(knowledge_indices), self.max_length, dtype=torch.bool)
            for i, k_enc in enumerate(knowledge_encoded):
                k_len = min(len(k_enc), self.max_length)
                knowledge_padded[i, :k_len] = k_enc[:k_len]
                knowledge_mask[i, :k_len] = True
        else:
            # Return empty tensors with batch dimension 1
            knowledge_padded = torch.zeros(1, self.max_length, dtype=torch.long)
            knowledge_mask = torch.zeros(1, self.max_length, dtype=torch.bool)
            
        return {
            'query_ids': query_padded,
            'query_mask': query_mask,
            'context_ids': context_padded,
            'context_mask': context_mask,
            'knowledge_ids': knowledge_padded,
            'knowledge_mask': knowledge_mask,
        }
    
    def __len__(self) -> int:
        return len(self.conversations)
    
    def __getitem__(self, idx: int) -> Dict[str, torch.Tensor]:
        conversation = self.conversations[idx]
        
        # Get query and response
        query = conversation['query']
        response = conversation['response']
        
        # Get conversation context
        context = conversation.get('context', '')
        
        # Find relevant knowledge
        knowledge_indices = self._find_relevant_knowledge(query)
        
        # Prepare inputs
        inputs = self._prepare_conversation_input(
            query=query,
            context=context,
            knowledge_indices=knowledge_indices
        )
        
        # Prepare target (response)
        response_clean = clean_scientific_text(response)
        response_encoded = self.text_processor.encode_text(response_clean)
        
        # Pad or truncate response
        response_padded = torch.zeros(self.max_length, dtype=torch.long)
        response_len = min(len(response_encoded), self.max_length)
        response_padded[:response_len] = response_encoded[:response_len]
        
        return {
            **inputs,
            'response_ids': response_padded
        }

def create_conversation_dataloaders(
    train_conversations: List[Dict],
    eval_conversations: List[Dict],
    knowledge_base: pd.DataFrame,
    batch_size: int = 32,
    max_length: int = 512
) -> tuple[DataLoader, DataLoader]:
    """Create train and evaluation dataloaders"""
    # Initialize text processor
    text_processor = AdvancedTextProcessor()
    
    # Create datasets
    train_dataset = BugSigConversationDataset(
        conversations=train_conversations,
        knowledge_base=knowledge_base,
        text_processor=text_processor,
        max_length=max_length
    )
    
    eval_dataset = BugSigConversationDataset(
        conversations=eval_conversations,
        knowledge_base=knowledge_base,
        text_processor=text_processor,
        max_length=max_length
    )
    
    # Create dataloaders
    train_dataloader = DataLoader(
        train_dataset,
        batch_size=batch_size,
        shuffle=True,
        num_workers=4
    )
    
    eval_dataloader = DataLoader(
        eval_dataset,
        batch_size=batch_size,
        shuffle=False,
        num_workers=4
    )
    
    return train_dataloader, eval_dataloader 