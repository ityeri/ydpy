"""End-to-end downloader tests against a mocked googlevideo Range server.

Regression for the tail-flush bug: the pump used to drop the final partial
block on EOF, which made the downloader re-request the same range forever
(observed in production as an endless stream of identical 206 responses).
"""

import asyncio
import io

import httpx
import pytest

from ydpy.downloader import DownloadOptions, adownload_stream, download_stream
from ydpy.exceptions import DownloadException

PAYLOAD = bytes(range(256)) * 4000  # 1,024,000 bytes


def _range_response(request: httpx.Request, payload: bytes, *, drop_after: int | None = None):
    """Serve googlevideo-style clamped 206 responses for a Range request."""
    rng = request.headers.get('range')
    if not rng or not rng.startswith('bytes='):
        return httpx.Response(200, headers={'Content-Length': str(len(payload))},
                              content=payload, request=request)
    start_text, _, end_text = rng[6:].partition('-')
    start = int(start_text)
    end = min(int(end_text) if end_text else len(payload) - 1, len(payload) - 1)
    if start >= len(payload):
        return httpx.Response(416, request=request)
    body = payload[start:end + 1]
    if drop_after is not None and start == 0:
        body = body[:drop_after]
    return httpx.Response(
        206,
        headers={
            'Content-Range': f'bytes {start}-{end}/{len(payload)}',
            'Content-Length': str(len(body))
        },
        content=body,
        request=request
    )


@pytest.fixture
def request_log():
    return []


def _make_async_client(request_log, payload=PAYLOAD, drop_after=None):
    def handler(request: httpx.Request) -> httpx.Response:
        request_log.append(request.headers.get('range'))
        return _range_response(request, payload, drop_after=drop_after)
    return httpx.AsyncClient(transport=httpx.MockTransport(handler), timeout=10.0)


def _make_sync_client(request_log, payload=PAYLOAD):
    def handler(request: httpx.Request) -> httpx.Response:
        request_log.append(request.headers.get('range'))
        return _range_response(request, payload)
    return httpx.Client(transport=httpx.MockTransport(handler), timeout=10.0)


# ---------------------------------------------------------------- async ---

async def test_single_chunk_clamped_206_completes(request_log):
    """The production bug: one 206 (range end clamped to the file size) used
    to loop forever because the trailing partial block was dropped."""
    client = _make_async_client(request_log)
    buf = io.BytesIO()
    result = await adownload_stream('https://cdn.example/v', buf, async_client=client)
    assert result.bytes_written == len(PAYLOAD)
    assert buf.getvalue() == PAYLOAD
    assert len(request_log) == 1


async def test_multi_chunk_requests_join_cleanly(request_log):
    client = _make_async_client(request_log)
    buf = io.BytesIO()
    options = DownloadOptions(chunk_size=400_000)
    result = await adownload_stream('https://cdn.example/v', buf,
                                    async_client=client, options=options)
    assert result.bytes_written == len(PAYLOAD)
    assert buf.getvalue() == PAYLOAD
    assert len(request_log) == 3  # 0-399999, 400000-799999, 800000-...


async def test_mid_body_drop_resumes_without_loop(request_log):
    client = _make_async_client(request_log, drop_after=len(PAYLOAD) // 2)
    buf = io.BytesIO()
    options = DownloadOptions(chunk_size=len(PAYLOAD) + 1)
    result = await adownload_stream('https://cdn.example/v', buf,
                                    async_client=client, options=options)
    assert result.bytes_written == len(PAYLOAD)
    assert buf.getvalue() == PAYLOAD
    assert len(request_log) == 2


async def test_200_full_response_falls_back_to_single_read(request_log):
    def handler(request: httpx.Request) -> httpx.Response:
        request_log.append('200')
        return httpx.Response(200, content=PAYLOAD, request=request)
    client = httpx.AsyncClient(transport=httpx.MockTransport(handler), timeout=10.0)
    buf = io.BytesIO()
    result = await adownload_stream('https://cdn.example/v', buf, async_client=client)
    assert result.bytes_written == len(PAYLOAD)
    assert buf.getvalue() == PAYLOAD
    assert request_log == ['200']


async def test_zero_progress_raises_instead_of_looping(request_log):
    """Server keeps answering 206 with an empty body: the guard must abort."""
    def handler(request: httpx.Request) -> httpx.Response:
        request_log.append(request.headers.get('range'))
        return httpx.Response(
            206,
            headers={'Content-Range': f'bytes 0-{len(PAYLOAD) - 1}/{len(PAYLOAD)}'},
            content=b'',
            request=request
        )
    client = httpx.AsyncClient(transport=httpx.MockTransport(handler), timeout=10.0)
    buf = io.BytesIO()
    with pytest.raises(DownloadException, match='No download progress'):
        await adownload_stream('https://cdn.example/v', buf, async_client=client)
    assert len(request_log) == 3


# ----------------------------------------------------------------- sync ---

def test_sync_single_chunk_clamped_206_completes(request_log):
    client = _make_sync_client(request_log)
    buf = io.BytesIO()
    result = download_stream('https://cdn.example/v', buf, client=client)
    assert result.bytes_written == len(PAYLOAD)
    assert buf.getvalue() == PAYLOAD
    assert len(request_log) == 1


def test_sync_zero_progress_raises(request_log):
    def handler(request: httpx.Request) -> httpx.Response:
        request_log.append(request.headers.get('range'))
        return httpx.Response(
            206,
            headers={'Content-Range': f'bytes 0-{len(PAYLOAD) - 1}/{len(PAYLOAD)}'},
            content=b'',
            request=request
        )
    client = httpx.Client(transport=httpx.MockTransport(handler), timeout=10.0)
    with pytest.raises(DownloadException, match='No download progress'):
        download_stream('https://cdn.example/v', io.BytesIO(), client=client)
    assert len(request_log) == 3
