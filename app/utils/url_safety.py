"""Guard against SSRF when fetching user-supplied URLs (e.g. /api/v1/analyze-url).

Best-effort: resolves the hostname and rejects private/loopback/link-local/
reserved addresses before the caller fetches it. Does not protect against
DNS rebinding between this check and the actual request, but blocks the
common case of pointing the scraper at internal services or cloud metadata
endpoints (e.g. 169.254.169.254).

Fetch user-supplied URLs through ``safe_aiohttp_get`` / ``safe_requests_get``,
not a plain ``get``: HTTP clients follow redirects by default, so checking only
the first URL lets a public page redirect the fetch to an internal address.
"""

import ipaddress
import socket
from contextlib import asynccontextmanager
from typing import Any, AsyncIterator, Optional
from urllib.parse import urljoin, urlparse

import aiohttp
import requests

_REDIRECT_STATUSES = frozenset({301, 302, 303, 307, 308})

# Same limit aiohttp applies by default, so legitimate redirect chains that
# worked before still work.
MAX_REDIRECTS = 10


class UnsafeURLError(ValueError):
    """Raised when a URL resolves to a disallowed (private/internal) address."""


def assert_public_url(url: str) -> None:
    """Raise UnsafeURLError if url isn't a public http(s) URL.

    Checks the URL scheme and resolves the hostname, rejecting any URL whose
    host or any resolved IP is private, loopback, link-local, or otherwise
    not globally routable.
    """
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https"):
        raise UnsafeURLError(f"Unsupported URL scheme: {parsed.scheme!r}")
    if not parsed.hostname:
        raise UnsafeURLError("URL has no hostname")

    try:
        addr_info = socket.getaddrinfo(parsed.hostname, None)
    except socket.gaierror as e:
        raise UnsafeURLError(f"Could not resolve host {parsed.hostname!r}: {e}")

    for *_rest, sockaddr in addr_info:
        ip = ipaddress.ip_address(sockaddr[0])
        if (
            ip.is_private
            or ip.is_loopback
            or ip.is_link_local
            or ip.is_multicast
            or ip.is_reserved
            or ip.is_unspecified
        ):
            raise UnsafeURLError(
                f"Host {parsed.hostname!r} resolves to a non-public address ({ip})"
            )


def _redirect_target(
    current_url: str, status: int, location: Optional[str]
) -> Optional[str]:
    """Return the absolute next-hop URL if this response is a redirect, else None."""
    if status in _REDIRECT_STATUSES and location:
        return urljoin(current_url, location)
    return None


@asynccontextmanager
async def safe_aiohttp_get(
    session: aiohttp.ClientSession,
    url: str,
    *,
    max_redirects: int = MAX_REDIRECTS,
    **kwargs: Any,
) -> AsyncIterator[aiohttp.ClientResponse]:
    """Drop-in for ``async with session.get(url, ...)`` that is SSRF-safe across redirects.

    Redirects are followed manually so every hop is checked with
    ``assert_public_url``. Raises ``UnsafeURLError`` if any hop is non-public
    or the chain exceeds ``max_redirects``.
    """
    current = url
    for _ in range(max_redirects + 1):
        assert_public_url(current)
        response = await session.get(current, allow_redirects=False, **kwargs)
        next_url = _redirect_target(
            current, response.status, response.headers.get("Location")
        )
        if next_url is None:
            try:
                yield response
            finally:
                response.release()
            return
        response.release()
        current = next_url
    raise UnsafeURLError(f"Too many redirects (more than {max_redirects})")


def safe_requests_get(
    url: str,
    *,
    timeout: float,
    max_redirects: int = MAX_REDIRECTS,
    **kwargs: Any,
) -> requests.Response:
    """Drop-in for ``requests.get(url, ...)`` that is SSRF-safe across redirects.

    Same contract as ``safe_aiohttp_get``, for synchronous callers.
    ``timeout`` is required and applies to each hop.
    """
    current = url
    for _ in range(max_redirects + 1):
        assert_public_url(current)
        response = requests.get(
            current, allow_redirects=False, timeout=timeout, **kwargs
        )
        next_url = _redirect_target(
            current, response.status_code, response.headers.get("Location")
        )
        if next_url is None:
            return response
        response.close()
        current = next_url
    raise UnsafeURLError(f"Too many redirects (more than {max_redirects})")
