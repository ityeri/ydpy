"""Format parsing from a real captured player response."""

import json
import pathlib

from ydpy.extract import extract_formats_from_player_response
from ydpy.streams import Format, StreamingProtocol

FIXTURE = pathlib.Path(__file__).parent / 'fixtures' / 'player_response.json'
DURATION_MS = 597_000  # Big Buck Bunny


def _player_response() -> dict:
    return json.loads(FIXTURE.read_text(encoding='utf-8'))


def test_extract_basic_counts():
    pr = _player_response()
    formats = extract_formats_from_player_response(pr, client='visionos',
                                                   duration_ms=DURATION_MS)
    assert formats, 'expected at least a few formats'
    assert all(fmt.client == 'visionos' for fmt in formats)
    assert any(fmt.is_audio for fmt in formats)
    assert any(fmt.is_video for fmt in formats)


def test_video_format_fields():
    pr = _player_response()
    formats = extract_formats_from_player_response(pr, client='visionos',
                                                   duration_ms=DURATION_MS)
    video = next(f for f in formats if f.is_video and f.height)
    assert video.mime_type and video.mime_type.startswith('video/')
    assert video.width and video.height
    assert video.itag > 0
    assert video.filesize is None or video.filesize > 0


def test_hls_manifest_entry_appended():
    pr = _player_response()
    formats = extract_formats_from_player_response(pr, client='visionos',
                                                   duration_ms=DURATION_MS)
    hls = [f for f in formats if f.protocol is StreamingProtocol.HLS]
    assert hls, 'fixture carries an hlsManifestUrl'
    assert hls[0].itag == 0 and hls[0].quality_label == 'hls'


def test_damaged_flag():
    pr = _player_response()
    streaming = pr['streamingData']
    raw = dict(streaming['adaptiveFormats'][0])
    raw['url'] = raw.get('url') or 'https://rr.example/stream'
    raw['approxDurationMs'] = 100_000  # far below half the video length
    streaming['adaptiveFormats'] = [raw]
    formats = extract_formats_from_player_response(pr, client='visionos',
                                                   duration_ms=DURATION_MS)
    assert formats[0].is_damaged


def test_url_less_format_skipped():
    raw = {'itag': 18, 'mimeType': 'video/mp4; codecs="avc1.42E01E,mp4a.40.2"'}
    pr = {'videoDetails': {'videoId': 'x'}, 'streamingData': {'adaptiveFormats': [raw]}}
    assert extract_formats_from_player_response(pr, client='web', duration_ms=None) == ()


def test_with_n_and_with_pot():
    fmt = Format(itag=1, client='web', url='https://rr.example/s?n=abc')
    assert 'n=solved' in fmt.with_n('solved').url
    assert 'pot=tok' in fmt.with_pot('tok').url
    assert fmt.url == 'https://rr.example/s?n=abc'  # original untouched
