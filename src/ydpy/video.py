"""User-facing entry point: a single YouTube video."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

import httpx
import yarl

from ydpy.exceptions import InvalidVideoIdentifierException
from ydpy.streams import VideoData

__all__ = ['Video']

_VIDEO_ID_PATTERN = re.compile(r'^[A-Za-z0-9_-]{11}$')
_KNOWN_PATH_PREFIXES = ('shorts', 'embed', 'live', 'v', 'watch', 'playlist')


@dataclass(frozen=True, slots=True)
class Video:
    """A single YouTube video, identified by id or url. No network on init."""

    video_id: str

    def __post_init__(self):
        parsed = _parse_identifier(self.video_id)
        object.__setattr__(self, 'video_id', parsed)

    def fetch(
        self,
        *,
        api_key: str | None = None,
        visitor_data: str | None = None,
        http_client: httpx.Client | None = None,
    ) -> VideoData:
        """Fetch the playable streams of this video (sync)."""
        from ydpy.extract import extract_video_data
        return extract_video_data(self.video_id, api_key=api_key,
                                  visitor_data=visitor_data, http_client=http_client)

    async def afetch(
        self,
        *,
        api_key: str | None = None,
        visitor_data: str | None = None,
        async_client: httpx.AsyncClient | None = None,
    ) -> VideoData:
        """Fetch the playable streams of this video (async)."""
        from ydpy.extract import aextract_video_data
        return await aextract_video_data(self.video_id, api_key=api_key,
                                         visitor_data=visitor_data, async_client=async_client)


def _parse_identifier(value: str) -> str:
    """Accept a bare video id or a youtube url; raise on anything else."""
    if _VIDEO_ID_PATTERN.fullmatch(value):
        return value
    if not value.startswith(('http://', 'https://')):
        raise InvalidVideoIdentifierException(
            f'Not a video id or youtube url: {value!r}')
    url = yarl.URL(value)
    host = (url.host or '').lower()
    if 'youtu.be' == host:
        candidate = url.path.strip('/').split('/')[0]
    elif 'youtube.com' in host or 'youtube-nocookie.com' in host:
        candidate = url.query.get('v') or _path_candidate(url)
    else:
        raise InvalidVideoIdentifierException(f'Not a youtube url: {value!r}')
    if not _VIDEO_ID_PATTERN.fullmatch(candidate or ''):
        raise InvalidVideoIdentifierException(
            f'Could not find a video id in {value!r}')
    return candidate


def _path_candidate(url: yarl.URL) -> str | None:
    """Last path segment, skipping known prefix segments like /shorts/."""
    segments = [s for s in url.path.split('/') if s]
    for segment in reversed(segments):
        if segment in _KNOWN_PATH_PREFIXES:
            continue
        return segment
    return None
