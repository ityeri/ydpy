"""Continuous HTTP downloader: one stream url, whole body, single connection."""

from __future__ import annotations

import asyncio
import time
from typing import Any

import httpx

from ydpy.downloader.utils import (
    DownloadOptions,
    DownloadProgress,
    DownloadResult,
    Sink,
    STREAM_HEADERS,
    open_target,
)
from ydpy.exceptions import DownloadException, ThrottledDownload

__all__ = [
    'best_block_size',
    'download_stream',
    'adownload_stream',
]

MAX_BLOCK_SIZE = 4 * 1024 * 1024  # adaptive buffering never exceeds 4 MiB
_RAW_CHUNK_SIZE = 64 * 1024       # pull size from the socket before buffering up


def best_block_size(elapsed_time: float, bytes_read: int) -> int:
    """Adapt the read size to the measured throughput, capped at 4 MiB."""
    new_min = max(bytes_read / 2.0, 1.0)
    new_max = min(max(bytes_read * 2.0, 1.0), MAX_BLOCK_SIZE)
    if elapsed_time < 0.001:
        return int(new_max)
    rate = bytes_read / elapsed_time
    if rate > new_max:
        return int(new_max)
    if rate < new_min:
        return int(new_min)
    return int(rate)


def _is_resettable(sink: Any) -> bool:
    """Buffers and real files can be rewound; raw streams cannot."""
    return hasattr(sink, 'seek') and hasattr(sink, 'truncate')


def _reset_sink(sink: Any) -> None:
    """Rewind a resettable sink to zero length."""
    sink.seek(0)
    sink.truncate(0)


def download_stream(
    url: str,
    target: str | Sink,
    *,
    options: DownloadOptions | None = None,
    client: httpx.Client | None = None,
) -> DownloadResult:
    """Download a stream url into target with retry/resume (sync)."""
    options = options or DownloadOptions()
    sink, should_close = open_target(target)
    own_client = client is None
    if own_client:
        client = httpx.Client(timeout=options.timeout, verify=options.verify_tls,
                              http2=options.http2, proxy=options.proxy, follow_redirects=True)
    headers = dict(STREAM_HEADERS)
    start_time = time.monotonic()
    downloaded = 0
    total: int | None = None
    try:
        attempt = 0
        while True:
            try:
                range_headers = dict(headers)
                # googlevideo throttles Range-less full fetches hard (measured
                # 2026-09: ~32 KB/s vs full speed with a Range header), so always range.
                range_headers['Range'] = f'bytes={downloaded}-'
                with client.stream('GET', url, headers=range_headers) as response:
                    if response.status_code == 416:
                        raise DownloadException('Server rejected the resume range (416)')
                    if response.status_code >= 400:
                        raise DownloadException(f'HTTP {response.status_code} while downloading')
                    content_range = response.headers.get('content-range')
                    if downloaded > 0 and not _range_honored(content_range, downloaded):
                        if not _is_resettable(sink):
                            raise DownloadException(
                                'Server ignored Range and the target cannot be rewound')
                        _reset_sink(sink)
                        downloaded = 0
                    total = _content_length(response.headers, downloaded, content_range)
                    downloaded = _pump(response, sink, downloaded, total, options, start_time)
                    if total is not None and downloaded < total:
                        raise DownloadException(
                            f'Connection closed early: got {downloaded} of {total} bytes')
                    break
            except (httpx.TransportError, httpx.TimeoutException) as e:
                attempt += 1
                if attempt > options.retries:
                    raise DownloadException(f'Download failed after {options.retries} retries: {e}') from e
                time.sleep(min(0.5 * (2 ** attempt), 10.0))
            except ThrottledDownload:
                raise
        return DownloadResult(bytes_written=downloaded,
                              elapsed_seconds=time.monotonic() - start_time, url=url)
    finally:
        if should_close:
            sink.close()
        if own_client:
            client.close()


def _pump(response: httpx.Response, sink: Sink, downloaded: int, total: int | None,
          options: DownloadOptions, start_time: float) -> int:
    """Read the body in adaptive blocks, writing each block to the sink."""
    chunks = response.iter_bytes(_RAW_CHUNK_SIZE)
    block_size = options.initial_block_size
    window_start = time.monotonic()
    window_bytes = 0
    while True:
        # Accumulate raw chunks until one adaptive block is filled (or EOF).
        block = bytearray()
        while len(block) < block_size:
            try:
                piece = next(chunks)
            except StopIteration:
                break
            block += piece
        if not block:
            return downloaded
        block_start = time.monotonic()
        sink.write(bytes(block))
        downloaded += len(block)
        window_bytes += len(block)
        now = time.monotonic()
        block_elapsed = now - block_start
        block_size = best_block_size(block_elapsed, len(block))
        if options.throttled_rate_limit and window_bytes >= 1024 * 1024:
            window_elapsed = now - window_start
            if window_elapsed >= 3.0:
                window_speed = window_bytes / window_elapsed
                if window_speed < options.throttled_rate_limit:
                    # A full 3s window below the limit: assume CDN throttling.
                    raise ThrottledDownload(
                        f'Speed {window_speed:.0f} B/s stayed under '
                        f'{options.throttled_rate_limit} B/s for 3 seconds')
                window_start = now
                window_bytes = 0
        if options.progress:
            total_elapsed = now - start_time
            speed = downloaded / total_elapsed if total_elapsed else None
            options.progress(DownloadProgress(downloaded=downloaded, total=total,
                                              speed_bps=speed, elapsed_seconds=total_elapsed))
        if total is not None and downloaded >= total:
            return downloaded


def _range_honored(content_range: str | None, requested_start: int) -> bool:
    """True when the server answered our Range with the matching start."""
    if not content_range or not content_range.startswith('bytes '):
        return False
    try:
        return int(content_range.split(' ', 1)[1].split('-', 1)[0]) == requested_start
    except (ValueError, IndexError):
        return False


def _content_length(headers: httpx.Headers, offset: int, content_range: str | None) -> int | None:
    """Total expected size: Range response length plus the offset already written."""
    if content_range:
        try:
            total = int(content_range.rsplit('/', 1)[1])
            return offset + max(total - offset, 0)
        except (ValueError, IndexError):
            pass
    content_length = headers.get('content-length')
    if content_length is not None:
        try:
            return offset + int(content_length)
        except ValueError:
            return None
    return None


async def adownload_stream(
    url: str,
    target: str | Sink,
    *,
    options: DownloadOptions | None = None,
    async_client: httpx.AsyncClient | None = None,
) -> DownloadResult:
    """Download a stream url into target with retry/resume (async)."""
    options = options or DownloadOptions()
    sink, should_close = open_target(target)
    own_client = async_client is None
    if own_client:
        async_client = httpx.AsyncClient(timeout=options.timeout, verify=options.verify_tls,
                                         http2=options.http2, proxy=options.proxy, follow_redirects=True)
    headers = dict(STREAM_HEADERS)
    start_time = time.monotonic()
    downloaded = 0
    total: int | None = None
    try:
        attempt = 0
        while True:
            try:
                range_headers = dict(headers)
                # googlevideo throttles Range-less full fetches hard (measured
                # 2026-09: ~32 KB/s vs full speed with a Range header), so always range.
                range_headers['Range'] = f'bytes={downloaded}-'
                async with async_client.stream('GET', url, headers=range_headers) as response:
                    if response.status_code == 416:
                        raise DownloadException('Server rejected the resume range (416)')
                    if response.status_code >= 400:
                        raise DownloadException(f'HTTP {response.status_code} while downloading')
                    content_range = response.headers.get('content-range')
                    if downloaded > 0 and not _range_honored(content_range, downloaded):
                        if not _is_resettable(sink):
                            raise DownloadException(
                                'Server ignored Range and the target cannot be rewound')
                        _reset_sink(sink)
                        downloaded = 0
                    total = _content_length(response.headers, downloaded, content_range)
                    downloaded = await _apump(response, sink, downloaded, total, options, start_time)
                    if total is not None and downloaded < total:
                        raise DownloadException(
                            f'Connection closed early: got {downloaded} of {total} bytes')
                    break
            except (httpx.TransportError, httpx.TimeoutException) as e:
                attempt += 1
                if attempt > options.retries:
                    raise DownloadException(f'Download failed after {options.retries} retries: {e}') from e
                await asyncio.sleep(min(0.5 * (2 ** attempt), 10.0))
            except ThrottledDownload:
                raise
        return DownloadResult(bytes_written=downloaded,
                              elapsed_seconds=time.monotonic() - start_time, url=url)
    finally:
        if should_close:
            sink.close()
        if own_client:
            await async_client.aclose()


async def _apump(response: httpx.AsyncResponse, sink: Sink, downloaded: int, total: int | None,
                 options: DownloadOptions, start_time: float) -> int:
    """Async twin of _pump."""
    chunks = response.aiter_bytes(_RAW_CHUNK_SIZE)
    block_size = options.initial_block_size
    window_start = time.monotonic()
    window_bytes = 0
    while True:
        block = bytearray()
        while len(block) < block_size:
            try:
                piece = await chunks.__anext__()
            except StopAsyncIteration:
                break
            block += piece
        if not block:
            return downloaded
        block_start = time.monotonic()
        sink.write(bytes(block))
        downloaded += len(block)
        window_bytes += len(block)
        now = time.monotonic()
        block_elapsed = now - block_start
        block_size = best_block_size(block_elapsed, len(block))
        if options.throttled_rate_limit and window_bytes >= 1024 * 1024:
            window_elapsed = now - window_start
            if window_elapsed >= 3.0:
                window_speed = window_bytes / window_elapsed
                if window_speed < options.throttled_rate_limit:
                    # A full 3s window below the limit: assume CDN throttling.
                    raise ThrottledDownload(
                        f'Speed {window_speed:.0f} B/s stayed under '
                        f'{options.throttled_rate_limit} B/s for 3 seconds')
                window_start = now
                window_bytes = 0
        if options.progress:
            total_elapsed = now - start_time
            speed = downloaded / total_elapsed if total_elapsed else None
            options.progress(DownloadProgress(downloaded=downloaded, total=total,
                                              speed_bps=speed, elapsed_seconds=total_elapsed))
        if total is not None and downloaded >= total:
            return downloaded
