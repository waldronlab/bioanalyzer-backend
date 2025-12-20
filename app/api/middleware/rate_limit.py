"""
Rate limiting middleware for API endpoints.
"""
import time
from typing import Dict, Optional
from collections import defaultdict
from fastapi import Request, HTTPException, status
from starlette.middleware.base import BaseHTTPMiddleware
import logging

logger = logging.getLogger(__name__)

# In-memory rate limit store (use Redis in production)
_rate_limit_store: Dict[str, list] = defaultdict(list)


class RateLimitMiddleware(BaseHTTPMiddleware):
    """
    Rate limiting middleware to prevent abuse.
    
    Uses sliding window algorithm for rate limiting.
    """
    
    def __init__(
        self,
        app,
        requests_per_minute: int = 60,
        enabled: bool = True
    ):
        """
        Initialize rate limiting middleware.
        
        Args:
            app: FastAPI application
            requests_per_minute: Maximum requests per minute per IP
            enabled: Enable/disable rate limiting
        """
        super().__init__(app)
        self.requests_per_minute = requests_per_minute
        self.enabled = enabled
    
    async def dispatch(self, request: Request, call_next):
        """Process request with rate limiting."""
        if not self.enabled:
            return await call_next(request)
        
        # Skip rate limiting for health checks and docs
        if request.url.path in ["/health", "/docs", "/redoc", "/openapi.json"]:
            return await call_next(request)
        
        # Get client IP
        client_ip = self._get_client_ip(request)
        
        # Check rate limit
        if not self._check_rate_limit(client_ip):
            logger.warning(f"Rate limit exceeded for IP: {client_ip}")
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail=f"Rate limit exceeded. Maximum {self.requests_per_minute} requests per minute."
            )
        
        # Process request
        response = await call_next(request)
        
        # Add rate limit headers
        response.headers["X-RateLimit-Limit"] = str(self.requests_per_minute)
        response.headers["X-RateLimit-Remaining"] = str(
            self._get_remaining_requests(client_ip)
        )
        
        return response
    
    def _get_client_ip(self, request: Request) -> str:
        """Extract client IP address from request."""
        # Check for forwarded IP (behind proxy)
        forwarded_for = request.headers.get("X-Forwarded-For")
        if forwarded_for:
            return forwarded_for.split(",")[0].strip()
        
        real_ip = request.headers.get("X-Real-IP")
        if real_ip:
            return real_ip
        
        return request.client.host if request.client else "unknown"
    
    def _check_rate_limit(self, client_ip: str) -> bool:
        """Check if client IP is within rate limit."""
        current_time = time.time()
        window_start = current_time - 60  # 1 minute window
        
        # Clean old entries
        requests = _rate_limit_store[client_ip]
        _rate_limit_store[client_ip] = [
            req_time for req_time in requests if req_time > window_start
        ]
        
        # Check limit
        if len(_rate_limit_store[client_ip]) >= self.requests_per_minute:
            return False
        
        # Add current request
        _rate_limit_store[client_ip].append(current_time)
        return True
    
    def _get_remaining_requests(self, client_ip: str) -> int:
        """Get remaining requests for client IP."""
        current_time = time.time()
        window_start = current_time - 60
        
        requests = _rate_limit_store[client_ip]
        valid_requests = [
            req_time for req_time in requests if req_time > window_start
        ]
        
        return max(0, self.requests_per_minute - len(valid_requests))

