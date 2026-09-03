"""Innertube client definitions and the client-selection strategy."""

from __future__ import annotations

from dataclasses import dataclass

from ydpy.request.utils import BROWSER_USER_AGENT

__all__ = [
    'Client',
    'CLIENTS',
    'get_default_clients',
    'innertube_headers',
]


@dataclass(frozen=True, slots=True)
class Client:
    """Static definition of one innertube client."""

    name: str
    client_name: str          # innertube 'clientName'
    client_version: str
    client_id: int            # INNERTUBE_CONTEXT_CLIENT_NAME
    user_agent: str | None = None
    device_make: str | None = None
    device_model: str | None = None
    os_name: str | None = None
    os_version: str | None = None
    require_js_player: bool = False  # True when formats need n/sig JS challenge solving


# Client versions are volatile on YouTube's side; bump them when a client
# starts misbehaving. This is the "web 2.20260708.00.00" generation.
_CLIENT_DEFS: tuple[Client, ...] = (
    Client(
        name='web',
        client_name='WEB',
        client_version='2.20260708.00.00',
        client_id=1,
        require_js_player=True,
    ),
    Client(
        name='visionos',
        client_name='VISIONOS',
        client_version='1.02',
        client_id=101,
        user_agent=(
            'Mozilla/5.0 (Macintosh; Intel Mac OS X 15_7_3) AppleWebKit/605.1.15 '
            '(KHTML, like Gecko) Version/26.0 Safari/605.1.15'
        ),
        device_make='Apple',
        device_model='RealityDevice17,1',
        os_name='visionOS',
        os_version='26.5.23O471',
        require_js_player=False,
    ),
)

CLIENTS: dict[str, Client] = {client.name: client for client in _CLIENT_DEFS}


def get_default_clients(*, js_available: bool) -> tuple[str, ...]:
    """VisionOS+web when a JS runtime exists, visionOS alone otherwise."""
    return ('visionos', 'web') if js_available else ('visionos',)


def innertube_headers(client: Client) -> dict[str, str]:
    """Request headers identifying an innertube client."""
    headers = {
        'X-YouTube-Client-Name': str(client.client_id),
        'X-YouTube-Client-Version': client.client_version,
    }
    if client.user_agent:
        headers['User-Agent'] = client.user_agent
    else:
        headers['User-Agent'] = BROWSER_USER_AGENT
    return headers
