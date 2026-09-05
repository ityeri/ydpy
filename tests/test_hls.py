"""HLS manifest parsing (offline fixtures, no network)."""

import pathlib

import pytest

from ydpy.downloader.segment_downloader import (
    parse_hls_master,
    parse_hls_media,
    _pick_variant,
)
from ydpy.exceptions import DataParsingException

HERE = pathlib.Path(__file__).parent / 'fixtures'


def test_master_parse():
    text = (HERE / 'hls_master.m3u8').read_text(encoding='utf-8')
    variants = parse_hls_master(text, 'https://manifest.example/index.m3u8')
    assert variants
    assert all(v.uri.startswith('http') for v in variants)
    assert any(v.height for v in variants)


def test_pick_variant_prefers_resolution():
    text = (HERE / 'hls_master.m3u8').read_text(encoding='utf-8')
    variants = parse_hls_master(text, 'https://manifest.example/index.m3u8')
    best = _pick_variant(variants)
    assert best.height == max(v.height or 0 for v in variants)


def test_media_parse_segments_and_endlist():
    text = (HERE / 'hls_media.m3u8').read_text(encoding='utf-8')
    playlist = parse_hls_media(text, 'https://manifest.example/playlist/index.m3u8')
    assert len(playlist.segment_urls) == 4
    assert playlist.endlist


def test_media_relative_url_resolution():
    text = '#EXTM3U\n#EXTINF:3.0,\n../seg-1.ts\n#EXT-X-ENDLIST\n'
    playlist = parse_hls_media(text, 'https://host.example/a/b/playlist.m3u8')
    assert playlist.segment_urls[0] == 'https://host.example/a/seg-1.ts'


def test_media_rejects_encryption():
    text = '#EXTM3U\n#EXT-X-KEY:METHOD=AES-128,URI="key.bin"\nseg.ts\n'
    with pytest.raises(DataParsingException):
        parse_hls_media(text, 'https://host.example/p.m3u8')


def test_media_rejects_empty():
    with pytest.raises(DataParsingException):
        parse_hls_media('#EXTM3U\n#EXT-X-ENDLIST\n', 'https://host.example/p.m3u8')
