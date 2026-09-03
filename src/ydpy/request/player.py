"""Innertube player endpoint."""

from __future__ import annotations

from typing import Any

import httpx
import yarl

from ydpy.client import Client, innertube_headers
from ydpy.exceptions import ExtractionException
from ydpy.request.utils import FALLBACK_API_KEY, INNERTUBE_HOST, apost_json, post_json

__all__ = [
    'get_player',
    'aget_player',
    'build_player_payload',
]

_PLAYER_URL = yarl.URL(f'{INNERTUBE_HOST}/player')


def build_player_payload(
    client: Client,
    video_id: str,
    *,
    visitor_data: str | None = None,
) -> dict[str, Any]:
    """Build the innertube player POST body for a client definition."""
    client_context: dict[str, Any] = {
        'clientName': client.client_name,
        'clientVersion': client.client_version,
    }
    if client.user_agent:
        client_context['userAgent'] = client.user_agent
    if client.device_make:
        client_context['deviceMake'] = client.device_make
    if client.device_model:
        client_context['deviceModel'] = client.device_model
    if client.os_name:
        client_context['osName'] = client.os_name
    if client.os_version:
        client_context['osVersion'] = client.os_version
    if visitor_data:
        client_context['visitorData'] = visitor_data
    return {
        'context': {'client': client_context},
        'videoId': video_id,
        'contentCheckOk': True,
        'racyCheckOk': True,
    }


def _validate_player_response(data: dict[str, Any], client: Client, video_id: str) -> None:
    """Raise ExtractionException when the response is not a usable player response."""
    playability = data.get('playabilityStatus') or {}
    if playability.get('status') != 'OK':
        reason = playability.get('reason') or playability.get('status')
        raise ExtractionException(f'video not playable ({reason})')
    details = data.get('videoDetails') or {}
    if details.get('videoId') != video_id:
        # Some videos serve the player response of a *different* video. Sneaky.
        raise ExtractionException(
            f'player response for another video ({details.get("videoId")!r})')


def get_player(
    client: Client,
    video_id: str,
    *,
    api_key: str | None = None,
    visitor_data: str | None = None,
    http_client: httpx.Client | None = None,
) -> dict[str, Any]:
    """Request the innertube player endpoint for a client (sync)."""
    url = _PLAYER_URL.with_query({'key': api_key or FALLBACK_API_KEY, 'prettyPrint': 'false'})
    payload = build_player_payload(client, video_id, visitor_data=visitor_data)
    data = post_json(url, payload, headers=innertube_headers(client), client=http_client)
    _validate_player_response(data, client, video_id)
    return data


async def aget_player(
    client: Client,
    video_id: str,
    *,
    api_key: str | None = None,
    visitor_data: str | None = None,
    async_client: httpx.AsyncClient | None = None,
) -> dict[str, Any]:
    """Request the innertube player endpoint for a client (async)."""
    url = _PLAYER_URL.with_query({'key': api_key or FALLBACK_API_KEY, 'prettyPrint': 'false'})
    payload = build_player_payload(client, video_id, visitor_data=visitor_data)
    data = await apost_json(url, payload, headers=innertube_headers(client), async_client=async_client)
    _validate_player_response(data, client, video_id)
    return data
