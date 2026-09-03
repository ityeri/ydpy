"""Live probe: per-client player response results for one video.

Usage (from repo root):  uv run python scripts/probe.py YE7VzlLtp-4
"""

from __future__ import annotations

import sys
from typing import Any

from ydpy.client import CLIENTS
from ydpy.request.player import get_player
from ydpy.request.webpage import get_watch_page


def _fmt_counts(streaming: dict[str, Any]) -> str:
    """One-line streamingData census."""
    formats = streaming.get('formats') or []
    adaptive = streaming.get('adaptiveFormats') or []
    n_formats = sum('n=' in (f.get('url') or '') for f in formats + adaptive)
    ciphered = sum(1 for f in formats + adaptive if not f.get('url') and f.get('signatureCipher'))
    return (f'formats={len(formats)} adaptive={len(adaptive)} '
            f'hls={bool(streaming.get("hlsManifestUrl"))} dash={bool(streaming.get("dashManifestUrl"))} '
            f'n_urls={n_formats} ciphered={ciphered}')


def _validate(pr: dict[str, Any], video_id: str) -> str | None:
    """Return an error description when the player response is unusable."""
    playability = pr.get('playabilityStatus') or {}
    if playability.get('status') != 'OK':
        return f'not playable ({playability.get("reason") or playability.get("status")})'
    if (pr.get('videoDetails') or {}).get('videoId') != video_id:
        return 'response for another video'
    return None


def _summarize(pr: dict[str, Any], label: str, video_id: str) -> None:
    """Validate then print a one-line summary of a player response."""
    problem = _validate(pr, video_id)
    if problem:
        print(f' [{label}] INVALID: {problem}')
        return
    details = pr.get('videoDetails') or {}
    print(f' [{label}] OK title={details.get("title")!r}')
    print(f'        {_fmt_counts(pr.get("streamingData") or {})}')
    for fmt in ((pr.get('streamingData') or {}).get('adaptiveFormats') or [])[:2]:
        url = fmt.get('url') or ''
        print(f'        - itag {fmt.get("itag")} {fmt.get("mimeType")} '
              f'{fmt.get("qualityLabel") or fmt.get("quality")} | {url[:80]}...')


def main():
    if len(sys.argv) != 2:
        print('usage: uv run python scripts/probe.py <video_id>')
        sys.exit(2)
    video_id = sys.argv[1]

    page = get_watch_page(video_id)
    ytcfg = page.ytcfg
    print('== watch page ==')
    for key in ('INNERTUBE_API_KEY', 'VISITOR_DATA', 'PLAYER_JS_URL'):
        value = ytcfg.get(key)
        print(f' {key:<17}:', '<missing>' if value is None else (str(value)[:70]))
    print(' clientVersion:', ytcfg.get('INNERTUBE_CONTEXT', {}).get('client', {}).get('clientVersion'))

    print('\n== web strategies ==')
    initial_pr = page.initial_player_response
    if initial_pr is not None:
        _summarize(initial_pr, 'web: watch page initial PR', video_id)
    else:
        print(' [web: initial PR] absent on page')
    try:
        api_pr = get_player(CLIENTS['web'], video_id, api_key=ytcfg.get('INNERTUBE_API_KEY'),
                            visitor_data=ytcfg.get('VISITOR_DATA'))
        _summarize(api_pr, 'web: player API direct', video_id)
    except Exception as e:
        print(f' [web: player API direct] FAIL: {type(e).__name__}: {e}')

    print('\n== visionos ==')
    try:
        api_pr = get_player(CLIENTS['visionos'], video_id, api_key=ytcfg.get('INNERTUBE_API_KEY'),
                            visitor_data=ytcfg.get('VISITOR_DATA'))
        _summarize(api_pr, 'visionos: player API', video_id)
    except Exception as e:
        print(f' [visionos: player API] FAIL: {type(e).__name__}: {e}')


if __name__ == '__main__':
    main()
