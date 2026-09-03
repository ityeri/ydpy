"""Watch page fetch plus ytcfg / initial player response extraction."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any

import httpx
import yarl

from ydpy.request.utils import BROWSER_USER_AGENT, aget_text, get_text

__all__ = [
    'WatchPageData',
    'get_watch_page',
    'aget_watch_page',
    'extract_ytcfg',
    'extract_initial_player_response',
]

_WATCH_URL = yarl.URL('https://www.youtube.com/watch')
_PAGE_HEADERS = {
    'User-Agent': BROWSER_USER_AGENT,
    'Accept-Language': 'en-US,en;q=0.9',
}


@dataclass(frozen=True, slots=True)
class WatchPageData:
    """Minimal data pulled out of a watch page HTML."""

    ytcfg: dict[str, Any]
    initial_player_response: dict[str, Any] | None


def _extract_balanced_object(text: str, start: int) -> dict[str, Any] | None:
    """Scan from an opening brace to its match, honoring JS strings and escapes."""
    depth = 0
    in_string = False
    escaped = False
    for index in range(start, len(text)):
        char = text[index]
        if in_string:
            if escaped:
                escaped = False
            elif char == '\\':
                escaped = True
            elif char == '"':
                in_string = False
            continue
        if char == '"':
            in_string = True
        elif char == '{':
            depth += 1
        elif char == '}':
            depth -= 1
            if depth == 0:
                try:
                    return json.loads(text[start:index + 1])
                except json.JSONDecodeError:
                    return None
    return None


def extract_ytcfg(html: str) -> dict[str, Any]:
    """Parse the first ytcfg.set({...}) blob of the page into a dict."""
    marker = re.search(r'ytcfg\.set\s*\(\s*(\{)', html)
    if marker is None:
        return {}
    return _extract_balanced_object(html, marker.start(1)) or {}


def extract_initial_player_response(html: str) -> dict[str, Any] | None:
    """Extract ytInitialPlayerResponse JSON when the page embeds one."""
    marker = html.find('ytInitialPlayerResponse')
    if marker == -1:
        return None
    brace = html.find('{', marker)
    if brace == -1:
        return None
    return _extract_balanced_object(html, brace)


def get_watch_page(
    video_id: str,
    *,
    language: str = 'en',
    region: str = 'US',
    client: httpx.Client | None = None,
) -> WatchPageData:
    """Fetch the watch page and extract its ytcfg and initial player response."""
    url = _WATCH_URL.with_query({'v': video_id, 'hl': language, 'gl': region})
    html = get_text(url, headers=_PAGE_HEADERS, client=client)
    return WatchPageData(
        ytcfg=extract_ytcfg(html),
        initial_player_response=extract_initial_player_response(html),
    )


async def aget_watch_page(
    video_id: str,
    *,
    language: str = 'en',
    region: str = 'US',
    async_client: httpx.AsyncClient | None = None,
) -> WatchPageData:
    """Async twin of get_watch_page."""
    url = _WATCH_URL.with_query({'v': video_id, 'hl': language, 'gl': region})
    html = await aget_text(url, headers=_PAGE_HEADERS, async_client=async_client)
    return WatchPageData(
        ytcfg=extract_ytcfg(html),
        initial_player_response=extract_initial_player_response(html),
    )
