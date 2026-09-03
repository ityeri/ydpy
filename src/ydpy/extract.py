"""Orchestration: a video id to a parsed, playable list of streams."""

from __future__ import annotations

from typing import Any, Sequence

import dataclasses

import httpx

from ydpy.client import CLIENTS, DEFAULT_CLIENT_NAMES
from ydpy.exceptions import ExtractionException
from ydpy.request.player import aget_player, get_player
from ydpy.request.webpage import aget_watch_page, get_watch_page
from ydpy.streams import Format, VideoData

__all__ = [
    'extract_video_data',
    'aextract_video_data',
    'extract_formats_from_player_response',
]

_VISIONOS = CLIENTS['visionos']


def extract_formats_from_player_response(
    player_response: dict[str, Any],
    *,
    client: str,
    duration_ms: int | None,
) -> tuple[Format, ...]:
    """Parse url-bearing formats out of a player response, flagging damaged ones."""
    streaming_data = player_response.get('streamingData') or {}
    raw_formats = (streaming_data.get('formats') or []) + (streaming_data.get('adaptiveFormats') or [])
    formats: list[Format] = []
    for raw in raw_formats:
        if not raw.get('url'):
            # Url-less formats (web watch page, M4 territory) are not playable yet.
            continue
        fmt = Format.from_json(raw, client=client)
        if duration_ms and fmt.approx_duration_ms and fmt.approx_duration_ms < duration_ms // 2:
            fmt = _flag_damaged(fmt)
        formats.append(fmt)
    return tuple(formats)


def _flag_damaged(fmt: Format) -> Format:
    """Return a copy flagged as possibly damaged (suspiciously short)."""
    return dataclasses.replace(fmt, is_damaged=True)


def _watch_credentials(
    video_id: str,
    api_key: str | None,
    visitor_data: str | None,
    http_client: httpx.Client | None,
) -> tuple[str | None, str | None]:
    """Backfill api key/visitor data from the watch page ytcfg when missing."""
    if api_key is not None and visitor_data is not None:
        return api_key, visitor_data
    page = get_watch_page(video_id, client=http_client)
    return (api_key if api_key is not None else page.ytcfg.get('INNERTUBE_API_KEY'),
            visitor_data if visitor_data is not None else page.ytcfg.get('VISITOR_DATA'))


async def _awatch_credentials(
    video_id: str,
    api_key: str | None,
    visitor_data: str | None,
    async_client: httpx.AsyncClient | None,
) -> tuple[str | None, str | None]:
    """Async twin of _watch_credentials."""
    if api_key is not None and visitor_data is not None:
        return api_key, visitor_data
    page = await aget_watch_page(video_id, async_client=async_client)
    return (api_key if api_key is not None else page.ytcfg.get('INNERTUBE_API_KEY'),
            visitor_data if visitor_data is not None else page.ytcfg.get('VISITOR_DATA'))


def extract_video_data(
    video_id: str,
    *,
    client_names: Sequence[str] | None = None,
    api_key: str | None = None,
    visitor_data: str | None = None,
    http_client: httpx.Client | None = None,
) -> VideoData:
    """Fetch playable streams, walking the client fallback chain on failure."""
    api_key, visitor_data = _watch_credentials(video_id, api_key, visitor_data, http_client)
    failures: list[str] = []
    for client_name in client_names or DEFAULT_CLIENT_NAMES:
        try:
            return _extract_from_client(client_name, video_id, api_key, visitor_data, http_client)
        except ExtractionException as e:
            failures.append(f'{client_name}: {e}')
    raise ExtractionException('; '.join(failures) or 'no playable formats from any client')


def _extract_from_client(
    client_name: str,
    video_id: str,
    api_key: str | None,
    visitor_data: str | None,
    http_client: httpx.Client | None,
) -> VideoData:
    """Fetch and parse playable streams from a single client."""
    client = CLIENTS[client_name]
    player_response = get_player(client, video_id, api_key=api_key,
                                 visitor_data=visitor_data, http_client=http_client)
    details = player_response.get('videoDetails') or {}
    duration_ms = _duration_ms(details)
    formats = extract_formats_from_player_response(
        player_response, client=client_name, duration_ms=duration_ms)
    if not formats:
        raise ExtractionException('no url-bearing playable formats')
    return VideoData(
        video_id=video_id,
        title=details.get('title'),
        duration_ms=duration_ms,
        client=client_name,
        formats=formats,
    )


def _duration_ms(details: dict[str, Any]) -> int | None:
    """videoDetails.lengthSeconds arrives as a string; normalize to ms."""
    try:
        return int(details.get('lengthSeconds') or 0) * 1000
    except (TypeError, ValueError):
        return None


async def aextract_video_data(
    video_id: str,
    *,
    client_names: Sequence[str] | None = None,
    api_key: str | None = None,
    visitor_data: str | None = None,
    async_client: httpx.AsyncClient | None = None,
) -> VideoData:
    """Async twin of extract_video_data."""
    api_key, visitor_data = await _awatch_credentials(video_id, api_key, visitor_data, async_client)
    failures: list[str] = []
    for client_name in client_names or DEFAULT_CLIENT_NAMES:
        try:
            return await _aextract_from_client(
                client_name, video_id, api_key, visitor_data, async_client)
        except ExtractionException as e:
            failures.append(f'{client_name}: {e}')
    raise ExtractionException('; '.join(failures))


async def _aextract_from_client(
    client_name: str,
    video_id: str,
    api_key: str | None,
    visitor_data: str | None,
    async_client: httpx.AsyncClient | None,
) -> VideoData:
    """Async twin of _extract_from_client."""
    client = CLIENTS[client_name]
    player_response = await aget_player(client, video_id, api_key=api_key,
                                        visitor_data=visitor_data, async_client=async_client)
    details = player_response.get('videoDetails') or {}
    duration_ms = _duration_ms(details)
    formats = extract_formats_from_player_response(
        player_response, client=client_name, duration_ms=duration_ms)
    if not formats:
        raise ExtractionException('no url-bearing playable formats')
    return VideoData(
        video_id=video_id,
        title=details.get('title'),
        duration_ms=duration_ms,
        client=client_name,
        formats=formats,
    )
