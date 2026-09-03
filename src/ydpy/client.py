"""Innertube client definitions and the client-selection strategy."""

from __future__ import annotations

from dataclasses import dataclass

from ydpy.request.utils import BROWSER_USER_AGENT

__all__ = [
    'Client',
    'CLIENTS',
    'DEFAULT_CLIENT_NAMES',
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
    # Pot-free fallbacks: anon player API still serves full direct urls to
    # these (live-verified 2026-09). Older TVHTML5 beats the current one, which
    # only hands out a 360p url anonymously.
    Client(
        name='tv_downgraded',
        client_name='TVHTML5',
        client_version='5.20260707',
        client_id=7,
        user_agent='Mozilla/5.0 (ChromiumStylePlatform) Cobalt/Version',
        require_js_player=False,
    ),
    Client(
        name='mweb',
        client_name='MWEB',
        client_version='2.20260708.05.00',
        client_id=2,
        user_agent=(
            'Mozilla/5.0 (iPad; CPU OS 16_7_10 like Mac OS X) AppleWebKit/605.1.15 '
            '(KHTML, like Gecko) Version/16.6 Mobile/15E148 Safari/604.1,gzip(gfe)'
        ),
        require_js_player=False,
    ),
    Client(
        name='android_vr',
        client_name='ANDROID_VR',
        client_version='1.65.10',
        client_id=28,
        user_agent=(
            'com.google.android.apps.youtube.vr.oculus/1.65.10 '
            '(Linux; U; Android 12L; eureka-user Build/SQ3A.220605.009.A1) gzip'
        ),
        device_make='Oculus',
        device_model='Quest 3',
        os_name='Android',
        os_version='12L',
        require_js_player=False,
    ),
)

CLIENTS: dict[str, Client] = {client.name: client for client in _CLIENT_DEFS}

# Ordered fallback chain: first client whose playable formats come back wins.
DEFAULT_CLIENT_NAMES: tuple[str, ...] = ('visionos', 'tv_downgraded', 'mweb', 'android_vr')


def get_default_clients(*, js_available: bool) -> tuple[str, ...]:
    """Primary + fallback clients (web needs POT, so it is not in the list)."""
    return DEFAULT_CLIENT_NAMES


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
