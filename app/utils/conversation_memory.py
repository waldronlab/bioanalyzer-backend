from typing import List, Dict, Optional
from dataclasses import dataclass
from datetime import datetime
import json

@dataclass
class Message:
    role: str  # 'user' or 'assistant'
    content: str
    timestamp: str = None
    
    def __post_init__(self):
        if self.timestamp is None:
            self.timestamp = datetime.now().isoformat()

class ConversationMemory:
    def __init__(self, max_history: int = 100):
        self.messages: List[Message] = []
        self.max_history = max_history
    
    def add_message(self, role: str, content: str):
        """Add a new message to the conversation history"""
        message = Message(role=role, content=content)
        self.messages.append(message)
        
        # Trim history if it exceeds max_history
        if len(self.messages) > self.max_history:
            self.messages = self.messages[-self.max_history:]
    
    def get_conversation_history(self, last_n: Optional[int] = None) -> List[Dict]:
        """Get the conversation history as a list of dictionaries"""
        history = self.messages[-last_n:] if last_n else self.messages
        return [{"role": msg.role, "content": msg.content, "timestamp": msg.timestamp} 
                for msg in history]
    
    def get_formatted_context(self, max_tokens: int = 1024) -> str:
        """Get conversation history formatted as context for the model"""
        context = []
        for msg in self.messages:
            context.append(f"{msg.role.upper()}: {msg.content}")
        return "\n".join(context[-max_tokens:])
    
    def save_to_file(self, filepath: str):
        """Save conversation history to a file"""
        with open(filepath, 'w') as f:
            json.dump(self.get_conversation_history(), f, indent=2)
    
    def load_from_file(self, filepath: str):
        """Load conversation history from a file"""
        with open(filepath, 'r') as f:
            data = json.load(f)
            self.messages = [Message(**msg) for msg in data]
            
    def clear(self):
        """Clear the conversation history"""
        self.messages = [] 