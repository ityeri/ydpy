from __future__ import annotations

import dataclasses
import re
from dataclasses import dataclass
from typing import Any, Sequence

import httpx
from yarl import URL

from ydpy.streams import Format, StreamingProtocol
from ydpy.client import CLIENTS, DEFAULT_CLIENT_NAMES
from ydpy.exceptions import ExtractionException, InvalidVideoIdentifierException
from ydpy.request.player import get_player, aget_player
from ydpy.request.webpage import get_watch_page, aget_watch_page

_VISIONOS = CLIENTS['visionos']


def _get_duration_ms(details: dict[str, Any]) -> int | None:
    """videoDetails.lengthSeconds arrives as a string; normalize to ms."""
    try:
        return int(details.get('lengthSeconds') or 0) * 1000
    except (TypeError, ValueError):
        return None


def _get_manifest_formats(streaming_data: dict[str, Any], *, client: str) -> list[Format]:
    """HLS/DASH master playlist entries for live and manifest-only streams."""
    entries: list[Format] = []
    for protocol_name, key in (('hls', 'hlsManifestUrl'), ('dash', 'dashManifestUrl')):
        manifest_url = streaming_data.get(key)
        if manifest_url:
            entries.append(Format(
                itag=0,
                client=client,
                url=manifest_url,
                protocol=StreamingProtocol(protocol_name),
                quality_label=protocol_name
            ))
    return entries


def _get_watch_credentials(
        video_id: str,
        api_key: str | None,
        visitor_data: str | None,
        http_client: httpx.Client | None
) -> tuple[str | None, str | None]:
    """Backfill api key/visitor data from the watch page ytcfg when missing."""
    if api_key is not None and visitor_data is not None:
        return api_key, visitor_data
    page = get_watch_page(video_id, client=http_client)
    return (api_key if api_key is not None else page.ytcfg.get('INNERTUBE_API_KEY'),
            visitor_data if visitor_data is not None else page.ytcfg.get('VISITOR_DATA'))


async def _aget_watch_credentials(
        video_id: str,
        api_key: str | None,
        visitor_data: str | None,
        async_client: httpx.AsyncClient | None
) -> tuple[str | None, str | None]:
    """Async twin of _watch_credentials."""
    if api_key is not None and visitor_data is not None:
        return api_key, visitor_data
    page = await aget_watch_page(video_id, async_client=async_client)
    return (api_key if api_key is not None else page.ytcfg.get('INNERTUBE_API_KEY'),
            visitor_data if visitor_data is not None else page.ytcfg.get('VISITOR_DATA'))


_VIDEO_ID_PATTERN = re.compile(r'^[A-Za-z0-9_-]{11}$')
_KNOWN_PATH_PREFIXES = ['shorts', 'embed', 'live', 'v', 'watch', 'playlist']


def _parse_identifier(value: str) -> str | None:
    """Accept a bare video id or a youtube url; raise on anything else."""
    if _VIDEO_ID_PATTERN.fullmatch(value):
        return value
    if not value.startswith(('http://', 'https://')):
        return None

    url = URL(value)
    host = (url.host or '').lower()

    candidate: str | None = None

    if 'youtu.be' == host:
        candidate = url.path.strip('/').split('/')[0]
    elif 'youtube.com' in host or 'youtube-nocookie.com' in host:
        if url.query.get('v') is not None:
            candidate = url.query.get('v')
        else:
            segments = [s for s in url.path.split('/') if s]
            for segment in reversed(segments):
                if segment in _KNOWN_PATH_PREFIXES:
                    continue
                else:
                    candidate = segment
                    break

            if candidate is None:
                return None

    else:
        return None

    if _VIDEO_ID_PATTERN.fullmatch(candidate or ''):
        return candidate
    else:
        return None


@dataclass(frozen=True, slots=True)
class PlayableVideo:
    """Immutable snapshot of one video's playable streams."""

    video_id: str
    title: str | None
    duration_ms: int | None
    client: str
    formats: list[Format]

    @staticmethod
    def fetch(
            video_id_or_url: str,
            *,
            client_names: Sequence[str] | None = None,
            api_key: str | None = None,
            visitor_data: str | None = None,
            http_client: httpx.Client | None = None
    ) -> PlayableVideo:
        """Fetch playable streams, walking the client fallback chain on failure."""
        video_id = _parse_identifier(video_id_or_url)
        if video_id is None:
            raise InvalidVideoIdentifierException(
                f'Not a valid video id or youtube url: {video_id_or_url!r}')

        api_key, visitor_data = _get_watch_credentials(video_id, api_key, visitor_data, http_client)
        failures: list[str] = []
        for client_name in client_names or DEFAULT_CLIENT_NAMES:
            try:
                return PlayableVideo._extract_from_client(client_name, video_id, api_key, visitor_data, http_client)
            except ExtractionException as e:
                failures.append(f'{client_name}: {e}')
        raise ExtractionException('; '.join(failures) or 'no playable formats from any client')

    @staticmethod
    async def afetch(
            video_id_or_url: str,
            *,
            client_names: Sequence[str] | None = None,
            api_key: str | None = None,
            visitor_data: str | None = None,
            async_client: httpx.AsyncClient | None = None
    ) -> PlayableVideo:
        """Async twin of extract_video_data."""
        video_id = _parse_identifier(video_id_or_url)
        if video_id is None:
            raise InvalidVideoIdentifierException(
                f'Not a valid video id or youtube url: {video_id_or_url!r}')

        api_key, visitor_data = await _aget_watch_credentials(video_id, api_key, visitor_data, async_client)
        failures: list[str] = []
        for client_name in client_names or DEFAULT_CLIENT_NAMES:
            try:
                return await PlayableVideo._aextract_from_client(
                    client_name, video_id, api_key, visitor_data, async_client)
            except ExtractionException as e:
                failures.append(f'{client_name}: {e}')
        raise ExtractionException('; '.join(failures))

    @staticmethod
    def extract_formats_from_player_response(
            player_response: dict[str, Any],
            *,
            client: str,
            duration_ms: int | None
    ) -> list[Format]:
        """Parse url-bearing formats, appending HLS/DASH manifest entries when present."""
        streaming_data = player_response.get('streamingData') or {}
        raw_formats = (streaming_data.get('formats') or []) + (streaming_data.get('adaptiveFormats') or [])
        formats: list[Format] = []
        for raw in raw_formats:
            if not raw.get('url'):
                # Url-less formats (web watch page, M4 territory) are not playable yet.
                continue
            fmt = Format.from_json(raw, client=client)
            if duration_ms and fmt.approx_duration_ms and fmt.approx_duration_ms < duration_ms // 2:
                fmt = dataclasses.replace(fmt, is_damaged=True)  # Flag damaged for wired formats
            formats.append(fmt)
        formats.extend(_get_manifest_formats(streaming_data, client=client))
        return formats

    @staticmethod
    def _extract_from_client(
            client_name: str,
            video_id: str,
            api_key: str | None,
            visitor_data: str | None,
            http_client: httpx.Client | None
    ) -> PlayableVideo:
        """Fetch and parse playable streams from a single client."""
        client = CLIENTS[client_name]
        player_response = get_player(
            client, video_id, api_key=api_key, visitor_data=visitor_data, http_client=http_client
        )
        details = player_response.get('videoDetails') or {}
        duration_ms = _get_duration_ms(details)
        formats = PlayableVideo.extract_formats_from_player_response(
            player_response, client=client_name, duration_ms=duration_ms
        )

        if not formats:
            raise ExtractionException('no url-bearing playable formats')
        return PlayableVideo(
            video_id=video_id,
            title=details.get('title'),
            duration_ms=duration_ms,
            client=client_name,
            formats=formats
        )

    @staticmethod
    async def _aextract_from_client(
            client_name: str,
            video_id: str,
            api_key: str | None,
            visitor_data: str | None,
            async_client: httpx.AsyncClient | None
    ) -> PlayableVideo:
        """Async twin of _extract_from_client."""
        client = CLIENTS[client_name]
        player_response = await aget_player(
            client, video_id, api_key=api_key, visitor_data=visitor_data, async_client=async_client
        )
        details = player_response.get('videoDetails') or {}
        duration_ms = _get_duration_ms(details)
        formats = PlayableVideo.extract_formats_from_player_response(
            player_response, client=client_name, duration_ms=duration_ms
        )

        if not formats:
            raise ExtractionException('no url-bearing playable formats')
        return PlayableVideo(
            video_id=video_id,
            title=details.get('title'),
            duration_ms=duration_ms,
            client=client_name,
            formats=formats
        )
