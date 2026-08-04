"""
Rate limiting middleware for API endpoints.
"""

import time
from typing import Dict, Optional
from collections import defaultdict
from fastapi import Request, status
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware
import logging

logger = logging.getLogger(__name__)

# In-memory rate limit store (use Redis in production)
_rate_limit_store: Dict[str, list] = defaultdict(list)

# Tracks when the store was last swept for fully-stale IP entries, so the
# sweep only runs periodically instead of on every single request.
_last_sweep_time: float = 0.0
_SWEEP_INTERVAL_SECONDS = 60


def _sweep_stale_ips(window_seconds: int = 60) -> None:
    """Remove client IPs whose request timestamps have all aged out of the window.

    Without this, `_rate_limit_store` accumulates one key per distinct IP
    forever: normal per-request pruning only trims each IP's timestamp list,
    it never deletes the (now-empty) key itself. This sweep is throttled to
    run at most once every `_SWEEP_INTERVAL_SECONDS` so it doesn't add
    per-request overhead.
    """
    global _last_sweep_time
    now = time.time()
    if now - _last_sweep_time < _SWEEP_INTERVAL_SECONDS:
        return
    _last_sweep_time = now

    window_start = now - window_seconds
    stale_ips = [
        ip
        for ip, timestamps in _rate_limit_store.items()
        if not [t for t in timestamps if t > window_start]
    ]
    for ip in stale_ips:
        del _rate_limit_store[ip]


class RateLimitMiddleware(BaseHTTPMiddleware):
    """
    Rate limiting middleware to prevent abuse.

    Uses sliding window algorithm for rate limiting.
    """

    def __init__(self, app, requests_per_minute: int = 60, enabled: bool = True):
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
            # Return the response directly rather than `raise HTTPException`:
            # this middleware sits outside Starlette's ExceptionMiddleware
            # layer (which is what normally turns a raised HTTPException into
            # a same-status JSON response), so an exception raised here
            # instead propagates all the way to the app's catch-all
            # `Exception` handler and gets flattened into a generic 500 -
            # silently discarding the real 429 status code the caller needs
            # to tell "back off and retry" apart from a genuine server error.
            return JSONResponse(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                content={
                    "detail": f"Rate limit exceeded. Maximum {self.requests_per_minute} requests per minute."
                },
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

        # Periodically sweep out IPs that have aged out entirely so the
        # store doesn't grow by one key per distinct IP forever.
        _sweep_stale_ips()

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
        valid_requests = [req_time for req_time in requests if req_time > window_start]

        return max(0, self.requests_per_minute - len(valid_requests))
