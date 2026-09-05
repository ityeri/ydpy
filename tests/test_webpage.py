"""Watch page ytcfg / initial player response extraction."""

import json
import pathlib

from ydpy.request.webpage import (
    extract_initial_player_response,
    extract_ytcfg,
)

FIXTURE = pathlib.Path(__file__).parent / 'fixtures' / 'watch_page.html'
VIDEO_ID = 'YE7VzlLtp-4'


def _html() -> str:
    return FIXTURE.read_text(encoding='utf-8')


def test_ytcfg_extraction():
    ytcfg = extract_ytcfg(_html())
    assert ytcfg, 'ytcfg should not be empty'
    assert ytcfg['INNERTUBE_API_KEY']
    assert ytcfg['VISITOR_DATA']
    assert ytcfg['PLAYER_JS_URL'].startswith('/s/player/')


def test_initial_player_response_extraction():
    pr = extract_initial_player_response(_html())
    assert pr is not None
    assert pr['videoDetails']['videoId'] == VIDEO_ID


def test_garbage_html():
    assert extract_ytcfg('<html>nothing here</html>') == {}
    assert extract_initial_player_response('<html>nothing here</html>') is None


def test_balanced_json_survives_strings_with_braces():
    html = '<script>ytcfg.set({"a": {"b": "} not a close {"}, "c": 1});</script>'
    assert extract_ytcfg(html)['a']['b'] == '} not a close {'
