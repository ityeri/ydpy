"""Segmented downloader: media driven by a manifest (HLS now, DASH scaffolded).

HLS and DASH are one domain: a manifest describes ordered byte sources
(segments), and downloading means fetching each in order into the sink.
"""

from __future__ import annotations

import asyncio
import re
import time
from dataclasses import dataclass
from typing import Any

import httpx
import yarl

from ydpy.downloader.utils import (
    DownloadOptions,
    DownloadProgress,
    DownloadResult,
    STREAM_HEADERS,
    Sink,
    Target,
    open_target,
)
from ydpy.exceptions import DataParsingException, DownloadException
from ydpy.request.utils import BROWSER_USER_AGENT, aget_text, get_text

__all__ = [
    'HlsVariant',
    'HlsMediaPlaylist',
    'parse_hls_master',
    'parse_hls_media',
    'download_hls',
    'adownload_hls',
    'download_dash',
    'adownload_dash',
]

_STREAM_INF_RE = re.compile(r'^#EXT-X-STREAM-INF:(.*)$')
_SEGMENT_HEADERS = {**STREAM_HEADERS, 'Range': 'bytes=0-'}


@dataclass(frozen=True, slots=True)
class HlsVariant:
    """One #EXT-X-STREAM-INF rendition of an HLS master playlist."""

    uri: str
    bandwidth: int | None = None
    width: int | None = None
    height: int | None = None
    codecs: str | None = None


@dataclass(frozen=True, slots=True)
class HlsMediaPlaylist:
    """Segment list of one HLS media playlist."""

    segment_urls: tuple[str, ...]
    endlist: bool = True


def _resolve(base_url: str, uri: str) -> str:
    """Join a possibly-relative playlist uri against the manifest url."""
    if uri.startswith(('http://', 'https://')):
        return uri
    return str(yarl.URL(base_url).join(yarl.URL(uri)))


def _parse_attrs(attr_text: str) -> dict[str, str]:
    """Parse the comma-separated KEY=VALUE list of an HLS tag."""
    attrs: dict[str, str] = {}
    for part in attr_text.split(','):
        if '=' not in part:
            continue
        key, _, value = part.partition('=')
        attrs[key.strip()] = value.strip().strip('"')
    return attrs


def parse_hls_master(text: str, base_url: str) -> tuple[HlsVariant, ...]:
    """Extract the video renditions from a master playlist."""
    variants: list[HlsVariant] = []
    pending: dict[str, str] | None = None
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith('#'):
            stream_inf = _STREAM_INF_RE.match(line)
            if stream_inf:
                pending = _parse_attrs(stream_inf.group(1))
            continue
        if pending is not None:
            attrs = pending
            pending = None
            width = height = None
            if resolution := attrs.get('RESOLUTION'):
                try:
                    width_text, _, height_text = resolution.partition('x')
                    width, height = int(width_text), int(height_text)
                except ValueError:
                    width = height = None
            variants.append(HlsVariant(
                uri=_resolve(base_url, line),
                bandwidth=_to_int(attrs.get('BANDWIDTH')),
                width=width,
                height=height,
                codecs=attrs.get('CODECS'),
            ))
    return tuple(variants)


def parse_hls_media(text: str, base_url: str) -> HlsMediaPlaylist:
    """Extract the segment urls from a media playlist."""
    segment_urls: list[str] = []
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        if line.startswith('#'):
            if line.startswith('#EXT-X-KEY'):
                # YouTube VOD playlists are not AES-encrypted; refuse the unknown.
                raise DataParsingException('Encrypted HLS (EXT-X-KEY) is not supported')
            continue
        segment_urls.append(_resolve(base_url, line))
    if not segment_urls:
        raise DataParsingException('Media playlist contains no segments')
    return HlsMediaPlaylist(segment_urls=tuple(segment_urls), endlist='#EXT-X-ENDLIST' in text)


def _to_int(value: str | None) -> int | None:
    """Parse an attribute int, ignoring garbage."""
    if value is None:
        return None
    try:
        return int(value)
    except ValueError:
        return None


def _pick_variant(variants: tuple[HlsVariant, ...]) -> HlsVariant:
    """Highest resolution, then bandwidth. Explicit > implicit preference."""
    return max(variants, key=lambda v: ((v.height or 0), (v.width or 0), v.bandwidth or 0))


def download_hls(
    master_url: str,
    target: Target,
    *,
    options: DownloadOptions | None = None,
    client: httpx.Client | None = None,
) -> DownloadResult:
    """Fetch an HLS master playlist and download its best rendition (sync)."""
    options = options or DownloadOptions()
    own_client = client is None
    if own_client:
        client = httpx.Client(timeout=options.timeout, verify=options.verify_tls,
                              http2=options.http2, proxy=options.proxy, follow_redirects=True)
    try:
        start_time = time.monotonic()
        master_text = get_text(master_url, headers=_SEGMENT_HEADERS, client=client)
        variants = parse_hls_master(master_text, master_url)
        if variants:
            media_url = _pick_variant(variants).uri
        else:
            # Some playlists are already media playlists (no renditions).
            media_url = master_url
        media_text = get_text(media_url, headers=_SEGMENT_HEADERS, client=client)
        playlist = parse_hls_media(media_text, media_url)
        if not playlist.endlist:
            raise DownloadException(
                'Live HLS playlists (no ENDLIST) are not supported; only VOD/post-live')
        return _download_segments(playlist.segment_urls, target, options, client, start_time)
    finally:
        if own_client:
            client.close()


def _download_segments(
    segment_urls: tuple[str, ...],
    target: Target,
    options: DownloadOptions,
    client: httpx.Client,
    start_time: float,
) -> DownloadResult:
    """Fetch every segment in order and concatenate it into the target."""
    sink, should_close = open_target(target)
    try:
        total_written = 0
        for index, segment_url in enumerate(segment_urls):
            body = _fetch_segment(segment_url, options, client, index)
            if not body:
                raise DownloadException(f'Empty segment {index} of {len(segment_urls)}')
            sink.write(body)
            total_written += len(body)
            if options.progress:
                elapsed = time.monotonic() - start_time
                options.progress(DownloadProgress(
                    downloaded=total_written, total=None,
                    speed_bps=total_written / elapsed if elapsed else None,
                    elapsed_seconds=elapsed))
        return DownloadResult(bytes_written=total_written,
                              elapsed_seconds=time.monotonic() - start_time, url=segment_urls[0])
    finally:
        if should_close:
            sink.close()


def _fetch_segment(segment_url: str, options: DownloadOptions,
                   client: httpx.Client, index: int) -> bytes:
    """GET one segment with retries; range request keeps the CDN honest."""
    for attempt in range(options.retries + 1):
        try:
            response = client.get(segment_url, headers=_SEGMENT_HEADERS)
            if response.status_code == 416:
                # Range on a fully-served slice means the server wants the body.
                response = client.get(segment_url,
                                      headers={'User-Agent': BROWSER_USER_AGENT})
            if response.status_code >= 400:
                raise DownloadException(f'HTTP {response.status_code} for segment {index}')
            return response.content
        except (httpx.TransportError, httpx.TimeoutException) as e:
            if attempt == options.retries:
                raise DownloadException(f'Segment {index} failed after retries: {e}') from e
            time.sleep(min(0.5 * (2 ** attempt), 5.0))


async def adownload_hls(
    master_url: str,
    target: Target,
    *,
    options: DownloadOptions | None = None,
    async_client: httpx.AsyncClient | None = None,
) -> DownloadResult:
    """Async twin of download_hls."""
    options = options or DownloadOptions()
    own_client = async_client is None
    if own_client:
        async_client = httpx.AsyncClient(timeout=options.timeout, verify=options.verify_tls,
                                         http2=options.http2, proxy=options.proxy,
                                         follow_redirects=True)
    try:
        start_time = time.monotonic()
        master_text = await aget_text(master_url, headers=_SEGMENT_HEADERS,
                                      async_client=async_client)
        variants = parse_hls_master(master_text, master_url)
        media_url = _pick_variant(variants).uri if variants else master_url
        media_text = await aget_text(media_url, headers=_SEGMENT_HEADERS,
                                     async_client=async_client)
        playlist = parse_hls_media(media_text, media_url)
        if not playlist.endlist:
            raise DownloadException(
                'Live HLS playlists (no ENDLIST) are not supported; only VOD/post-live')
        return await _adownload_segments(playlist.segment_urls, target, options,
                                         async_client, start_time)
    finally:
        if own_client:
            await async_client.aclose()


async def _adownload_segments(
    segment_urls: tuple[str, ...],
    target: Target,
    options: DownloadOptions,
    async_client: httpx.AsyncClient,
    start_time: float,
) -> DownloadResult:
    """Async twin of _download_segments."""
    sink, should_close = open_target(target)
    try:
        total_written = 0
        for index, segment_url in enumerate(segment_urls):
            body = await _afetch_segment(segment_url, options, async_client, index)
            if not body:
                raise DownloadException(f'Empty segment {index} of {len(segment_urls)}')
            sink.write(body)
            total_written += len(body)
            if options.progress:
                elapsed = time.monotonic() - start_time
                options.progress(DownloadProgress(
                    downloaded=total_written, total=None,
                    speed_bps=total_written / elapsed if elapsed else None,
                    elapsed_seconds=elapsed))
        return DownloadResult(bytes_written=total_written,
                              elapsed_seconds=time.monotonic() - start_time, url=segment_urls[0])
    finally:
        if should_close:
            sink.close()


async def _afetch_segment(segment_url: str, options: DownloadOptions,
                          async_client: httpx.AsyncClient, index: int) -> bytes:
    """Async twin of _fetch_segment."""
    for attempt in range(options.retries + 1):
        try:
            response = await async_client.get(segment_url, headers=_SEGMENT_HEADERS)
            if response.status_code == 416:
                response = await async_client.get(
                    segment_url, headers={'User-Agent': BROWSER_USER_AGENT})
            if response.status_code >= 400:
                raise DownloadException(f'HTTP {response.status_code} for segment {index}')
            return response.content
        except (httpx.TransportError, httpx.TimeoutException) as e:
            if attempt == options.retries:
                raise DownloadException(f'Segment {index} failed after retries: {e}') from e
            await asyncio.sleep(min(0.5 * (2 ** attempt), 5.0))


def download_dash(mpd_url: str, target: str | Any, **kwargs: Any) -> DownloadResult:
    """DASH download placeholder: no live MPD shape in the client set yet."""
    raise DownloadException(
        f'DASH manifests are not supported yet (got {mpd_url}); '
        'no client in the current set serves a dashManifestUrl to validate against')


async def adownload_dash(mpd_url: str, target: str | Any, **kwargs: Any) -> DownloadResult:
    """Async twin of download_dash."""
    raise DownloadException(
        f'DASH manifests are not supported yet (got {mpd_url}); '
        'no client in the current set serves a dashManifestUrl to validate against')
