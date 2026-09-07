"""Network primitives copied/adapted from nanobot's web-tool security path.

Keeps ClearAct self-contained while providing SSRF checks, DNS pinning and safe redirects.
"""

from __future__ import annotations

import asyncio
import ipaddress
import socket
from contextlib import suppress
from urllib.parse import urljoin, urlparse
from urllib.request import getproxies

import httpx

MAX_REDIRECTS = 5
_BLOCKED_NETWORKS = (
    ipaddress.ip_network("0.0.0.0/8"),
    ipaddress.ip_network("10.0.0.0/8"),
    ipaddress.ip_network("100.64.0.0/10"),
    ipaddress.ip_network("127.0.0.0/8"),
    ipaddress.ip_network("169.254.0.0/16"),
    ipaddress.ip_network("172.16.0.0/12"),
    ipaddress.ip_network("192.168.0.0/16"),
    ipaddress.ip_network("::1/128"),
    ipaddress.ip_network("fc00::/7"),
    ipaddress.ip_network("fe80::/10"),
)


class UnsafeURLRequestError(httpx.RequestError):
    """Request rejected because its target is internal or unsafe."""


def _normalise(address: ipaddress.IPv4Address | ipaddress.IPv6Address):
    return address.ipv4_mapped if isinstance(address, ipaddress.IPv6Address) and address.ipv4_mapped else address


def _loopback_allowed(hostname: str, addresses: list[ipaddress.IPv4Address | ipaddress.IPv6Address]) -> bool:
    if not addresses or not all(_normalise(address).is_loopback for address in addresses):
        return False
    if hostname.rstrip(".").lower() == "localhost":
        return True
    with suppress(ValueError):
        return ipaddress.ip_address(hostname).is_loopback
    return False


def resolve_url_target(url: str, *, allow_loopback: bool = False) -> tuple[bool, str, tuple[str, ...]]:
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"}:
        return False, f"Only http/https allowed, got '{parsed.scheme or 'none'}'", ()
    if not parsed.netloc or not parsed.hostname:
        return False, "Missing domain", ()
    try:
        infos = socket.getaddrinfo(parsed.hostname, None, socket.AF_UNSPEC, socket.SOCK_STREAM)
    except socket.gaierror:
        return False, f"Cannot resolve hostname: {parsed.hostname}", ()
    addresses = []
    for info in infos:
        with suppress(ValueError):
            addresses.append(ipaddress.ip_address(info[4][0]))
    if allow_loopback and _loopback_allowed(parsed.hostname, addresses):
        return True, "", tuple(dict.fromkeys(str(_normalise(address)) for address in addresses))
    for address in addresses:
        if any(_normalise(address) in network for network in _BLOCKED_NETWORKS):
            return False, f"Blocked: {parsed.hostname} resolves to private/internal address {address}", ()
    return True, "", tuple(dict.fromkeys(str(_normalise(address)) for address in addresses))


class PinnedDNSAsyncTransport(httpx.AsyncBaseTransport):
    """Validate and pin each request DNS resolution, preventing DNS rebinding."""

    _lock = asyncio.Lock()

    def __init__(self, *, allow_loopback: bool = False):
        self.allow_loopback = allow_loopback
        self.inner = httpx.AsyncHTTPTransport()

    async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
        url = str(request.url)
        ok, error, addresses = resolve_url_target(url, allow_loopback=self.allow_loopback)
        if not ok:
            raise UnsafeURLRequestError(error, request=request)
        hostname = request.url.host.rstrip(".").lower()
        original = socket.getaddrinfo

        def pinned(host, port, family=0, type=0, proto=0, flags=0):  # noqa: A002
            if str(host).rstrip(".").lower() != hostname:
                return original(host, port, family, type, proto, flags)
            infos = []
            for value in addresses:
                address = ipaddress.ip_address(value)
                address_family = socket.AF_INET6 if address.version == 6 else socket.AF_INET
                if family not in (0, socket.AF_UNSPEC, address_family):
                    continue
                sockaddr = (value, port or 0, 0, 0) if address_family == socket.AF_INET6 else (value, port or 0)
                infos.append((address_family, type or socket.SOCK_STREAM, proto, "", sockaddr))
            return infos

        async with self._lock:
            socket.getaddrinfo = pinned
            try:
                return await self.inner.handle_async_request(request)
            finally:
                socket.getaddrinfo = original

    async def aclose(self) -> None:
        await self.inner.aclose()


def client_kwargs(*, timeout: float, allow_loopback: bool) -> dict:
    """Match nanobot's use of explicit or environment proxy settings with a safe direct transport."""
    mounts: dict[str, httpx.AsyncBaseTransport | None] = {}
    proxies = getproxies()
    for scheme in ("http", "https", "all"):
        proxy = proxies.get(scheme)
        if proxy:
            if "://" not in proxy:
                proxy = f"http://{proxy}"
            mounts[f"{scheme}://"] = httpx.AsyncHTTPTransport(proxy=httpx.Proxy(proxy))
    if mounts:
        no_proxy = proxies.get("no", "")
        if no_proxy != "*":
            for host in no_proxy.split(","):
                host = host.strip()
                if host:
                    mounts[f"all://*{host}"] = None
        return {
            "timeout": timeout,
            "transport": PinnedDNSAsyncTransport(allow_loopback=allow_loopback),
            "mounts": mounts,
        }
    return {
        "timeout": timeout,
        "transport": PinnedDNSAsyncTransport(allow_loopback=allow_loopback),
    }


async def get_with_safe_redirects(
    client: httpx.AsyncClient, url: str, headers: dict[str, str], *, allow_loopback: bool = False
):
    """Validate every redirect before requesting it, as nanobot does."""
    current = url
    for _ in range(MAX_REDIRECTS + 1):
        response = await client.get(current, headers=headers, follow_redirects=False)
        if not 300 <= response.status_code < 400 or not response.headers.get("location"):
            return response
        next_url = urljoin(str(response.url), response.headers["location"])
        ok, error, _ = resolve_url_target(next_url, allow_loopback=allow_loopback)
        if not ok:
            await response.aclose()
            raise UnsafeURLRequestError(f"Redirect blocked: {error}", request=response.request)
        await response.aclose()
        current = next_url
    raise UnsafeURLRequestError(f"Too many redirects: exceeded limit of {MAX_REDIRECTS}")
