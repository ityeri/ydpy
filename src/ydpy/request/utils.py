"""Shared HTTP bits: endpoint constants and JSON POST / text GET helpers."""

from __future__ import annotations

import logging
from typing import Any

import httpx
import yarl

from ydpy.exceptions import RequestException

__all__ = [
    'INNERTUBE_HOST',
    'FALLBACK_API_KEY',
    'BROWSER_USER_AGENT',
    'post_json',
    'apost_json',
    'get_text',
    'aget_text',
]

_logger = logging.getLogger(__name__)

INNERTUBE_HOST = 'https://www.youtube.com/youtubei/v1'
# The WEB client normally carries its own key inside the watch page ytcfg; this
# is only a fallback when no ytcfg could be obtained. Yep, it is the classic
# public innertube web key.
FALLBACK_API_KEY = 'AIzaSyAO_FJ2SlqU8Q4STEHLGCilw_Y9_11qcW8'
BROWSER_USER_AGENT = (
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
    '(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36'
)

_DEFAULT_TIMEOUT = httpx.Timeout(30.0, connect=15.0)


def _check_response(response: httpx.Response) -> None:
    """Raise RequestException on non-2xx; transport errors were already mapped."""
    if response.status_code >= 400:
        raise RequestException(f'HTTP {response.status_code} from {response.url}')


def post_json(
    url: yarl.URL | str,
    payload: dict[str, Any],
    *,
    headers: dict[str, str] | None = None,
    client: httpx.Client | None = None,
) -> dict[str, Any]:
    """POST JSON and return the parsed object response."""
    own_client = client is None
    if own_client:
        client = httpx.Client(timeout=_DEFAULT_TIMEOUT, follow_redirects=True)
    try:
        response = client.post(str(url), json=payload, headers=headers)
        _check_response(response)
        try:
            data = response.json()
        except ValueError:
            raise RequestException(f'Non-JSON response from {url}') from None
    except RequestException:
        raise
    except httpx.TransportError as e:
        raise RequestException(f'Request to {url} failed: {e}') from e
    finally:
        if own_client:
            client.close()
    if not isinstance(data, dict):
        raise RequestException(f'Unexpected non-object JSON from {url}')
    return data


async def apost_json(
    url: yarl.URL | str,
    payload: dict[str, Any],
    *,
    headers: dict[str, str] | None = None,
    async_client: httpx.AsyncClient | None = None,
) -> dict[str, Any]:
    """Async twin of post_json."""
    own_client = async_client is None
    if own_client:
        async_client = httpx.AsyncClient(timeout=_DEFAULT_TIMEOUT, follow_redirects=True)
    try:
        response = await async_client.post(str(url), json=payload, headers=headers)
        _check_response(response)
        try:
            data = response.json()
        except ValueError:
            raise RequestException(f'Non-JSON response from {url}') from None
    except RequestException:
        raise
    except httpx.TransportError as e:
        raise RequestException(f'Request to {url} failed: {e}') from e
    finally:
        if own_client:
            await async_client.aclose()
    if not isinstance(data, dict):
        raise RequestException(f'Unexpected non-object JSON from {url}')
    return data


def get_text(
    url: yarl.URL | str,
    *,
    headers: dict[str, str] | None = None,
    client: httpx.Client | None = None,
) -> str:
    """GET a URL and return the response body as text."""
    own_client = client is None
    if own_client:
        client = httpx.Client(timeout=_DEFAULT_TIMEOUT, follow_redirects=True)
    try:
        response = client.get(str(url), headers=headers)
        _check_response(response)
        return response.text
    except RequestException:
        raise
    except httpx.TransportError as e:
        raise RequestException(f'Request to {url} failed: {e}') from e
    finally:
        if own_client:
            client.close()


async def aget_text(
    url: yarl.URL | str,
    *,
    headers: dict[str, str] | None = None,
    async_client: httpx.AsyncClient | None = None,
) -> str:
    """Async twin of get_text."""
    own_client = async_client is None
    if own_client:
        async_client = httpx.AsyncClient(timeout=_DEFAULT_TIMEOUT, follow_redirects=True)
    try:
        response = await async_client.get(str(url), headers=headers)
        _check_response(response)
        return response.text
    except RequestException:
        raise
    except httpx.TransportError as e:
        raise RequestException(f'Request to {url} failed: {e}') from e
    finally:
        if own_client:
            await async_client.aclose()
