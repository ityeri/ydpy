"""PlayableVideo snapshot semantics and identifier parsing (offline)."""

import dataclasses

import pytest

from ydpy.exceptions import InvalidVideoIdentifierException
from ydpy.playable_video import PlayableVideo, _parse_identifier

VALID = [
    ('YE7VzlLtp-4', 'YE7VzlLtp-4'),
    ('https://www.youtube.com/watch?v=YE7VzlLtp-4', 'YE7VzlLtp-4'),
    ('https://youtu.be/YE7VzlLtp-4', 'YE7VzlLtp-4'),
    ('https://www.youtube.com/shorts/BGQWPY4IigY', 'BGQWPY4IigY'),
    ('https://www.youtube.com/embed/YE7VzlLtp-4', 'YE7VzlLtp-4'),
    ('https://www.youtube.com/live/YE7VzlLtp-4', 'YE7VzlLtp-4'),
    ('https://music.youtube.com/watch?v=YE7VzlLtp-4', 'YE7VzlLtp-4'),
    ('http://www.youtube.com/watch?v=YE7VzlLtp-4&t=1s', 'YE7VzlLtp-4')
]

INVALID = [
    'YE7VzlLtp-',
    'YE7VzlLtp-4!',
    'https://www.youtube.com/playlist?list=PL1234567890',
    'https://vimeo.com/123456',
    'not a url at all',
    ''
]


@pytest.mark.parametrize(('value', 'expected_id'), VALID)
def test_parse_identifier_valid(value, expected_id):
    assert _parse_identifier(value) == expected_id


@pytest.mark.parametrize('value', INVALID)
def test_parse_identifier_invalid(value):
    assert _parse_identifier(value) is None


@pytest.mark.parametrize('value', INVALID)
def test_fetch_rejects_invalid_before_any_network(value):
    # parse happens first, so invalid input never touches the network
    with pytest.raises(InvalidVideoIdentifierException):
        PlayableVideo.fetch(value)


def test_snapshot_is_frozen_with_mutable_formats_collection():
    video = PlayableVideo(video_id='YE7VzlLtp-4', title='t', duration_ms=597_000,
                          client='visionos', formats=[])
    with pytest.raises(dataclasses.FrozenInstanceError):
        video.video_id = 'other'
    video.formats.append('fmt')  # collection contents stay mutable by design
    assert len(video.formats) == 1
