"""Guard against SSRF when fetching user-supplied URLs (e.g. /api/v1/analyze-url).

Best-effort: resolves the hostname and rejects private/loopback/link-local/
reserved addresses before the caller fetches it. Does not protect against
DNS rebinding between this check and the actual request, but blocks the
common case of pointing the scraper at internal services or cloud metadata
endpoints (e.g. 169.254.169.254).
"""

import ipaddress
import socket
from urllib.parse import urlparse


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
