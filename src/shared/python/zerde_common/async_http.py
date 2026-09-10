"""Cancellable DNS and HTTP using public HTTPX, HTTPCore and dnspython APIs.

Use the returned client as an async context manager, inside an asyncio.timeout
covering the entire request. This module bounds network I/O, not synchronous CPU work.

Public extension contracts:
https://dnspython.readthedocs.io/en/latest/async-resolver-class.html
https://www.encode.io/httpcore/network-backends/
https://www.python-httpx.org/advanced/transports/
"""

import asyncio
import ipaddress
import time
from contextlib import contextmanager

import dns.asyncresolver
import dns.exception
import httpcore
import httpx


async def _system_resolve(host: str, timeout: float) -> list[str]:
    # Uses the OS resolver configuration (/etc/resolv.conf on Lambda), never a hardcoded public resolver.
    resolver = dns.asyncresolver.Resolver()

    async def query(kind):
        try:
            answer = await resolver.resolve(host, kind, lifetime=timeout, search=False)
            return [str(record.address) for record in answer]
        except dns.exception.DNSException:
            return []

    async with asyncio.timeout(timeout):
        answers = await asyncio.gather(query("A"), query("AAAA"))
    return list(dict.fromkeys(address for group in answers for address in group))


class _DNSBackend(httpcore.AsyncNetworkBackend):
    def __init__(self, resolver=None, backend=None):
        self._resolve = resolver or _system_resolve
        self._backend = backend or httpcore.AnyIOBackend()

    async def connect_tcp(self, host, port, timeout=None, local_address=None, socket_options=None):
        seconds = timeout if timeout is not None else 3
        if seconds <= 0:
            raise httpcore.ConnectTimeout("Connection deadline exhausted")
        expires = time.monotonic() + seconds
        try:
            async with asyncio.timeout(seconds):
                try:
                    addresses = [str(ipaddress.ip_address(host))]
                except ValueError:
                    addresses = await self._resolve(host, seconds)
                if not addresses:
                    raise httpcore.ConnectError("DNS returned no usable address")
                for address in addresses:
                    # Passing an IP to AnyIO avoids its threaded loop.getaddrinfo path.
                    address = str(ipaddress.ip_address(address))
                    remaining = expires - time.monotonic()
                    if remaining <= 0:
                        raise httpcore.ConnectTimeout("Connection deadline exhausted")
                    try:
                        return await self._backend.connect_tcp(
                            address, port, timeout=remaining, local_address=local_address, socket_options=socket_options
                        )
                    except (httpcore.ConnectError, httpcore.ConnectTimeout):
                        continue
                raise httpcore.ConnectError("No resolved address connected")
        except TimeoutError:
            raise httpcore.ConnectTimeout("DNS or TCP deadline exhausted") from None

    async def connect_unix_socket(self, *args, **kwargs):
        raise httpcore.UnsupportedProtocol("Unix sockets are not enabled for this HTTP client")

    async def sleep(self, seconds):
        await asyncio.sleep(seconds)


@contextmanager
def _http_errors():
    """Translate public HTTPCore errors without exposing URL or credentials."""
    try:
        yield
    except httpcore.TimeoutException:
        raise httpx.TimeoutException("HTTP network timeout") from None
    except (httpcore.NetworkError, httpcore.ProtocolError, httpcore.ProxyError):
        raise httpx.TransportError("HTTP network transport failed") from None
    except httpcore.UnsupportedProtocol:
        raise httpx.UnsupportedProtocol("Unsupported HTTP transport") from None


class _ResponseStream(httpx.AsyncByteStream):
    def __init__(self, response):
        self._response = response

    async def __aiter__(self):
        with _http_errors():
            async for chunk in self._response.aiter_stream():
                yield chunk

    async def aclose(self):
        with _http_errors():
            await self._response.aclose()


class _DNSTransport(httpx.AsyncBaseTransport):
    def __init__(self, *, resolver=None, network_backend=None, max_connections=5):
        self._pool = httpcore.AsyncConnectionPool(
            network_backend=_DNSBackend(resolver, network_backend),
            max_connections=max_connections,
            max_keepalive_connections=0,
            retries=0,
        )

    async def handle_async_request(self, request):
        # The pool retains the original host for HTTP Host, TLS SNI and certificate verification.
        core_request = httpcore.Request(
            method=request.method,
            url=httpcore.URL(
                scheme=request.url.raw_scheme,
                host=request.url.raw_host,
                port=request.url.port,
                target=request.url.raw_path,
            ),
            headers=request.headers.raw,
            content=request.stream,
            extensions=request.extensions,
        )
        with _http_errors():
            response = await self._pool.handle_async_request(core_request)
        return httpx.Response(
            response.status, headers=response.headers, stream=_ResponseStream(response), extensions=response.extensions
        )

    async def aclose(self):
        with _http_errors():
            await self._pool.aclose()


def bounded_async_client(
    *,
    timeout: float,
    connect_timeout: float = 3,
    max_connections: int = 5,
    follow_redirects: bool = False,
    max_redirects: int = 5,
    resolver=None,
    network_backend=None,
    transport=None,
) -> httpx.AsyncClient:
    """Create a fresh, caller-owned client; injected transports/backends are for tests.

    No environment proxy or implicit request retry is enabled. DNS resolution,
    connection, and streaming reads are async and cancellable. The caller must
    provide an outer asyncio.timeout to bound the complete multi-read request.
    """
    if timeout <= 0 or connect_timeout <= 0 or max_connections < 1:
        raise ValueError("HTTP timeout and connection limits must be positive")
    if transport is not None and (resolver is not None or network_backend is not None):
        raise ValueError("Inject either a transport or a DNS/network backend, not both")
    return httpx.AsyncClient(
        timeout=httpx.Timeout(timeout, connect=min(timeout, connect_timeout)),
        transport=transport
        or _DNSTransport(resolver=resolver, network_backend=network_backend, max_connections=max_connections),
        follow_redirects=follow_redirects,
        max_redirects=max_redirects,
        trust_env=False,
    )
