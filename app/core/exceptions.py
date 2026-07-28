import logging
from typing import Any

from fastapi import Request
from fastapi.responses import JSONResponse

from app.utils.credential_masking import mask_exception_message

logger = logging.getLogger(__name__)


def log_masked_exception(exc: Exception, message: str, *, level: str = "error") -> None:
    """Log an exception with credential-masked details."""
    getattr(logger, level)("%s: %s", message, mask_exception_message(exc))


async def generic_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """Catch-all handler: log (masked) and return the standard 500 contract."""
    log_masked_exception(exc, f"Unhandled error on {request.method} {request.url.path}")
    return JSONResponse(status_code=500, content={"detail": "Internal server error"})


def register_exception_handlers(app: Any) -> None:
    """Attach the global handler to a FastAPI app instance. Call once at startup."""
    app.add_exception_handler(Exception, generic_exception_handler)