"""
Simple UserManager stub for testing purposes.
"""

class UserManager:
    """Basic user session management for testing."""
    
    def __init__(self):
        self.sessions = {}
    
    def start_session(self, name: str):
        """Start a new user session."""
        session = UserSession(name)
        self.sessions[name] = session
        return session
    
    def get_session(self, name: str):
        """Get an existing session."""
        return self.sessions.get(name)
    
    def cleanup_session(self, name: str):
        """Clean up a user session."""
        if name in self.sessions:
            del self.sessions[name]
            return True
        return False


class UserSession:
    """Simple user session representation."""
    
    def __init__(self, name: str):
        self.name = name
        self.created_at = None
        self.last_activity = None
    
    def to_dict(self):
        """Convert session to dictionary."""
        return {
            "name": self.name,
            "created_at": self.created_at,
            "last_activity": self.last_activity
        } 