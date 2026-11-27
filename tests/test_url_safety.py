"""SSRF guard: every redirect hop of a user-supplied URL must be public.

DNS is faked via socket.getaddrinfo so no test touches the network.
"""

import socket

import pytest

from app.services import web_scraper
from app.services.image_processor import ImageProcessorService
from app.utils import url_safety
from app.utils.url_safety import (
    UnsafeURLError,
    assert_public_url,
    safe_aiohttp_get,
    safe_requests_get,
)

FAKE_DNS = {
    "public.example": "93.184.216.34",
    "other-public.example": "93.184.216.35",
    "metadata.internal": "169.254.169.254",
    "intranet.internal": "10.0.0.5",
}


@pytest.fixture(autouse=True)
def fake_dns(monkeypatch):
    def fake_getaddrinfo(host, *_args, **_kwargs):
        if host not in FAKE_DNS:
            raise socket.gaierror(f"unknown host {host}")
        return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", (FAKE_DNS[host], 0))]

    monkeypatch.setattr(url_safety.socket, "getaddrinfo", fake_getaddrinfo)


class _FakeAiohttpResponse:
    def __init__(self, status, location=None, body=b""):
        self.status = status
        self.headers = {"Location": location} if location else {}
        self.body = body
        self.released = False

    def release(self):
        self.released = True

    def raise_for_status(self):
        if self.status >= 400:
            raise RuntimeError(f"HTTP {self.status}")

    async def read(self):
        return self.body


class _FakeAiohttpSession:
    """Serves canned responses by URL and records every URL actually requested."""

    def __init__(self, routes):
        self.routes = routes
        self.requested = []
        self.kwargs_seen = []

    async def get(self, url, **kwargs):
        self.requested.append(url)
        self.kwargs_seen.append(kwargs)
        return self.routes[url]


class _FakeRequestsResponse:
    def __init__(self, status_code, location=None):
        self.status_code = status_code
        self.headers = {"Location": location} if location else {}
        self.closed = False

    def close(self):
        self.closed = True


# --------------------------------------------------------------------------- #
# assert_public_url (existing behavior, pinned)
# --------------------------------------------------------------------------- #


def test_assert_public_url_accepts_public_host():
    assert_public_url("https://public.example/page")


@pytest.mark.parametrize(
    "url",
    [
        "http://metadata.internal/latest/meta-data/",
        "http://intranet.internal/admin",
        "ftp://public.example/file",
    ],
)
def test_assert_public_url_rejects_internal_or_bad_scheme(url):
    with pytest.raises(UnsafeURLError):
        assert_public_url(url)


# --------------------------------------------------------------------------- #
# safe_aiohttp_get
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_aiohttp_redirect_to_internal_is_blocked_before_request():
    session = _FakeAiohttpSession(
        {
            "https://public.example/a": _FakeAiohttpResponse(
                302, "http://metadata.internal/latest/meta-data/"
            ),
        }
    )
    with pytest.raises(UnsafeURLError):
        async with safe_aiohttp_get(session, "https://public.example/a"):
            pass
    # The internal address was never fetched.
    assert session.requested == ["https://public.example/a"]
    assert session.routes["https://public.example/a"].released


@pytest.mark.asyncio
async def test_aiohttp_public_redirect_chain_is_followed():
    final = _FakeAiohttpResponse(200, body=b"ok")
    session = _FakeAiohttpSession(
        {
            "https://public.example/a": _FakeAiohttpResponse(
                301, "https://other-public.example/b"
            ),
            # Relative Location resolves against the current hop.
            "https://other-public.example/b": _FakeAiohttpResponse(307, "/c"),
            "https://other-public.example/c": final,
        }
    )
    async with safe_aiohttp_get(session, "https://public.example/a", timeout=5) as r:
        assert r is final
        assert await r.read() == b"ok"
    assert final.released
    assert session.requested == [
        "https://public.example/a",
        "https://other-public.example/b",
        "https://other-public.example/c",
    ]
    # Client-side redirect following is always off; caller kwargs pass through.
    assert all(k["allow_redirects"] is False for k in session.kwargs_seen)
    assert all(k["timeout"] == 5 for k in session.kwargs_seen)


@pytest.mark.asyncio
async def test_aiohttp_non_redirect_status_is_returned_as_is():
    not_found = _FakeAiohttpResponse(404)
    session = _FakeAiohttpSession({"https://public.example/x": not_found})
    async with safe_aiohttp_get(session, "https://public.example/x") as r:
        assert r.status == 404


@pytest.mark.asyncio
async def test_aiohttp_too_many_redirects():
    session = _FakeAiohttpSession(
        {"https://public.example/loop": _FakeAiohttpResponse(302, "/loop")}
    )
    with pytest.raises(UnsafeURLError, match="Too many redirects"):
        async with safe_aiohttp_get(
            session, "https://public.example/loop", max_redirects=3
        ):
            pass
    assert len(session.requested) == 4


@pytest.mark.asyncio
async def test_image_processor_does_not_fetch_redirected_internal_image(tmp_path):
    processor = ImageProcessorService(cache_dir=str(tmp_path))
    session = _FakeAiohttpSession(
        {
            "https://public.example/img.png": _FakeAiohttpResponse(
                302, "http://intranet.internal/secret.png"
            ),
        }
    )
    result = await processor._download_image(
        "https://public.example/img.png", session=session
    )
    assert result is None
    assert session.requested == ["https://public.example/img.png"]


@pytest.mark.asyncio
async def test_web_scraper_page_fetch_refuses_redirect_to_internal(
    monkeypatch, tmp_path
):
    session = _FakeAiohttpSession(
        {
            "https://public.example/paper": _FakeAiohttpResponse(
                302, "http://metadata.internal/latest/meta-data/"
            ),
        }
    )

    class _SessionCM:
        def __init__(self, *args, **kwargs):
            pass

        async def __aenter__(self):
            return session

        async def __aexit__(self, *exc):
            return False

    monkeypatch.setattr(web_scraper.aiohttp, "ClientSession", _SessionCM)
    scraper = web_scraper.WebScraperService(download_dir=str(tmp_path))
    with pytest.raises(RuntimeError, match="non-public address"):
        await scraper._fetch_html("https://public.example/paper")
    assert session.requested == ["https://public.example/paper"]


# --------------------------------------------------------------------------- #
# safe_requests_get
# --------------------------------------------------------------------------- #


def test_requests_redirect_to_internal_is_blocked(monkeypatch):
    requested = []
    first = _FakeRequestsResponse(302, "http://intranet.internal/admin")

    def fake_get(url, **kwargs):
        requested.append(url)
        assert kwargs["allow_redirects"] is False
        return first

    monkeypatch.setattr(url_safety.requests, "get", fake_get)
    with pytest.raises(UnsafeURLError):
        safe_requests_get("https://public.example/img.png", timeout=10)
    assert requested == ["https://public.example/img.png"]
    assert first.closed


def test_requests_public_redirect_is_followed(monkeypatch):
    final = _FakeRequestsResponse(200)
    routes = {
        "https://public.example/img.png": _FakeRequestsResponse(
            303, "https://other-public.example/img.png"
        ),
        "https://other-public.example/img.png": final,
    }
    monkeypatch.setattr(url_safety.requests, "get", lambda url, **kw: routes[url])
    assert safe_requests_get("https://public.example/img.png", timeout=10) is final


def test_requests_initial_internal_url_is_blocked(monkeypatch):
    def fail_get(*_a, **_k):
        raise AssertionError("internal URL must not be requested")

    monkeypatch.setattr(url_safety.requests, "get", fail_get)
    with pytest.raises(UnsafeURLError):
        safe_requests_get("http://metadata.internal/latest/meta-data/")
