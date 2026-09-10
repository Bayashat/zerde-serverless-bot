"""Real HTTPX/HTTPCore contracts with synthetic DNS and network streams only."""

import asyncio
import socket
import ssl
import time

import dns.asyncresolver
import dns.message
import dns.rrset
import httpcore
import httpx
import pytest
from zerde_common import async_http


class RecordingStream(httpcore.AsyncMockStream):
    def __init__(self, response=b"HTTP/1.1 200 OK\r\nContent-Length: 2\r\n\r\nOK"):
        super().__init__([response])
        self.hostname = None
        self.verified = None
        self.written = []
        self.closed = False

    async def start_tls(self, ssl_context, server_hostname=None, timeout=None):
        self.hostname = server_hostname
        self.verified = ssl_context.check_hostname and ssl_context.verify_mode == ssl.CERT_REQUIRED
        return self

    async def write(self, buffer, timeout=None):
        self.written.append(buffer)
        await super().write(buffer, timeout)

    async def aclose(self):
        self.closed = True
        await super().aclose()


class RecordingBackend(httpcore.AsyncNetworkBackend):
    def __init__(self, streams):
        self.streams = list(streams)
        self.calls = []

    async def connect_tcp(self, host, port, timeout=None, local_address=None, socket_options=None):
        self.calls.append((host, port))
        return self.streams.pop(0)


async def synthetic_resolve(host, timeout):
    return ["192.0.2.1"]


def test_dns_resolves_to_ip_but_tls_verifies_original_hostname_and_http_host(monkeypatch):
    monkeypatch.setenv("HTTPS_PROXY", "http://should-not-be-used.invalid:9999")
    monkeypatch.setenv("ALL_PROXY", "http://should-not-be-used.invalid:9999")
    stream = RecordingStream()
    backend = RecordingBackend([stream])

    async def run():
        async with async_http.bounded_async_client(
            timeout=1, resolver=synthetic_resolve, network_backend=backend
        ) as client:
            response = await client.post("https://original.example:8443/path?q=1", json={"synthetic": True})
            assert response.text == "OK"

    asyncio.run(run())
    assert backend.calls == [("192.0.2.1", 8443)]
    assert stream.hostname == "original.example" and stream.verified
    assert b"Host: original.example:8443" in b"".join(stream.written)
    assert stream.closed


def test_cancelled_dns_has_no_default_executor_shutdown_delay_or_tcp_attempt():
    cancelled = []
    backend = RecordingBackend([])

    async def slow_resolve(host, timeout):
        try:
            await asyncio.sleep(60)
        finally:
            cancelled.append(True)

    async def run():
        loop = asyncio.get_running_loop()

        async def forbidden(*args, **kwargs):
            raise AssertionError("Threaded OS getaddrinfo must not be used")

        loop.getaddrinfo = forbidden
        async with async_http.bounded_async_client(
            timeout=1, connect_timeout=0.03, resolver=slow_resolve, network_backend=backend
        ) as client:
            with pytest.raises(httpx.TimeoutException):
                await client.get("https://slow.invalid")
        assert loop._default_executor is None  # No resolver thread for asyncio.run() to join.

    started = time.monotonic()
    asyncio.run(run())
    assert cancelled == [True] and backend.calls == [] and time.monotonic() - started < 0.7


@pytest.mark.parametrize("answer", [True, False])
def test_actual_async_dns_uses_udp_and_cancels_without_threaded_resolution(monkeypatch, answer):
    real_resolver = dns.asyncresolver.Resolver
    stream = RecordingStream()
    backend = RecordingBackend([stream])
    calls = []

    class DNSProtocol(asyncio.DatagramProtocol):
        def connection_made(self, transport):
            self.transport = transport

        def datagram_received(self, data, address):
            calls.append(data)
            if not answer:
                return
            query = dns.message.from_wire(data)
            response = dns.message.make_response(query)
            if query.question[0].rdtype == dns.rdatatype.A:
                response.answer.append(dns.rrset.from_text(query.question[0].name, 60, "IN", "A", "192.0.2.1"))
            self.transport.sendto(response.to_wire(), address)

    async def run():
        loop = asyncio.get_running_loop()
        transport, _ = await loop.create_datagram_endpoint(
            DNSProtocol, local_addr=("127.0.0.1", 0), family=socket.AF_INET
        )
        resolver = real_resolver(configure=False)
        resolver.nameservers = ["127.0.0.1"]
        resolver.port = transport.get_extra_info("sockname")[1]
        # Production constructs Resolver() with OS defaults; the test routes only its DNS socket to localhost.
        monkeypatch.setattr(async_http.dns.asyncresolver, "Resolver", lambda: resolver)

        async def forbidden(*args, **kwargs):
            raise AssertionError("Threaded OS getaddrinfo must not be used")

        monkeypatch.setattr(loop, "getaddrinfo", forbidden)
        try:
            async with async_http.bounded_async_client(
                timeout=1, connect_timeout=0.08, network_backend=backend
            ) as client:
                if answer:
                    assert (await client.get("https://synthetic.invalid")).text == "OK"
                else:
                    with pytest.raises(httpx.TimeoutException):
                        await client.get("https://synthetic.invalid")
            assert loop._default_executor is None
        finally:
            transport.close()

    asyncio.run(run())
    assert calls
    assert len(backend.calls) == int(answer)


def test_response_stream_cancellation_closes_the_underlying_connection():
    class SlowBody(RecordingStream):
        def __init__(self):
            super().__init__()
            self.reads = 0
            self.cancelled = False

        async def read(self, max_bytes, timeout=None):
            self.reads += 1
            if self.reads == 1:
                return b"HTTP/1.1 200 OK\r\nContent-Length: 100\r\n\r\nfirst"
            try:
                await asyncio.sleep(60)
            finally:
                self.cancelled = True

    stream = SlowBody()
    backend = RecordingBackend([stream])

    async def run():
        with pytest.raises(TimeoutError):
            async with asyncio.timeout(0.03):
                async with async_http.bounded_async_client(
                    timeout=1, resolver=synthetic_resolve, network_backend=backend
                ) as client:
                    await client.get("https://synthetic.invalid")

    asyncio.run(run())
    assert stream.cancelled and stream.closed


def test_no_implicit_retry_after_tcp_failure():
    class FailedBackend(RecordingBackend):
        async def connect_tcp(self, host, port, **kwargs):
            self.calls.append((host, port))
            raise httpcore.ConnectError("synthetic failure")

    backend = FailedBackend([])

    async def run():
        async with async_http.bounded_async_client(
            timeout=1, resolver=synthetic_resolve, network_backend=backend
        ) as client:
            with pytest.raises(httpx.TransportError):
                await client.post("https://synthetic.invalid", json={"synthetic": True})

    asyncio.run(run())
    assert len(backend.calls) == 1


@pytest.mark.parametrize("follow", [False, True])
def test_redirects_are_disabled_by_default_and_explicit_redirect_keeps_each_hostname(follow):
    first = RecordingStream(b"HTTP/1.1 302 Found\r\nLocation: https://second.example/\r\nContent-Length: 0\r\n\r\n")
    second = RecordingStream()
    backend = RecordingBackend([first, second])

    async def run():
        async with async_http.bounded_async_client(
            timeout=1, resolver=synthetic_resolve, network_backend=backend, follow_redirects=follow
        ) as client:
            response = await client.get("https://first.example/")
            assert response.status_code == (200 if follow else 302)

    asyncio.run(run())
    assert first.hostname == "first.example"
    assert second.hostname == ("second.example" if follow else None)


def test_literal_ip_does_not_call_dns_resolver():
    called = []

    async def forbidden(*args):
        called.append(True)
        raise AssertionError("IP literal must not resolve")

    stream = RecordingStream()
    backend = RecordingBackend([stream])

    async def run():
        async with async_http.bounded_async_client(timeout=1, resolver=forbidden, network_backend=backend) as client:
            await client.get("https://192.0.2.1")

    asyncio.run(run())
    assert called == [] and backend.calls == [("192.0.2.1", 443)]


def test_incompatible_test_injection_is_rejected():
    with pytest.raises(ValueError, match="either"):
        async_http.bounded_async_client(
            timeout=1, resolver=synthetic_resolve, transport=httpx.MockTransport(lambda r: None)
        )


def test_default_tcp_backend_uses_literal_ip_without_threaded_dns(monkeypatch):
    async def run():
        async def handler(reader, writer):
            try:
                await reader.readuntil(b"\r\n\r\n")
                writer.write(b"HTTP/1.1 200 OK\r\nContent-Length: 2\r\nConnection: close\r\n\r\nOK")
                await writer.drain()
            finally:
                writer.close()
                await writer.wait_closed()

        server = await asyncio.start_server(handler, "127.0.0.1", 0)
        port = server.sockets[0].getsockname()[1]
        loop = asyncio.get_running_loop()

        async def forbidden(*args, **kwargs):
            raise AssertionError("Default TCP backend must not call threaded DNS for an IP")

        monkeypatch.setattr(loop, "getaddrinfo", forbidden)

        async def local_resolve(host, timeout):
            assert host == "synthetic.invalid"
            return ["127.0.0.1"]

        try:
            async with async_http.bounded_async_client(timeout=1, resolver=local_resolve) as client:
                assert (await client.get(f"http://synthetic.invalid:{port}")).text == "OK"
            assert loop._default_executor is None
        finally:
            server.close()
            await server.wait_closed()

    asyncio.run(run())
