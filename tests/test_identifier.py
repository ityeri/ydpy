"""Video identifier/url parsing tests (no network)."""

import pytest

from ydpy import Video
from ydpy.exceptions import InvalidVideoIdentifierException

VALID_URLS = [
    ('https://www.youtube.com/watch?v=YE7VzlLtp-4', 'YE7VzlLtp-4'),
    ('https://youtu.be/YE7VzlLtp-4', 'YE7VzlLtp-4'),
    ('https://www.youtube.com/shorts/BGQWPY4IigY', 'BGQWPY4IigY'),
    ('https://www.youtube.com/embed/YE7VzlLtp-4', 'YE7VzlLtp-4'),
    ('https://www.youtube.com/live/YE7VzlLtp-4', 'YE7VzlLtp-4'),
    ('https://music.youtube.com/watch?v=YE7VzlLtp-4', 'YE7VzlLtp-4'),
    ('http://www.youtube.com/watch?v=YE7VzlLtp-4&t=1s', 'YE7VzlLtp-4'),
]

INVALID = [
    'YE7VzlLtp-',                # too short
    'YE7VzlLtp-4!',              # bad charset
    'https://www.youtube.com/playlist?list=PL1234567890',
    'https://vimeo.com/123456',
    'not a url at all',
    '',
]


@pytest.mark.parametrize(('value', 'expected_id'), VALID_URLS)
def test_valid_urls(value, expected_id):
    assert Video(value).video_id == expected_id


@pytest.mark.parametrize('value', INVALID)
def test_invalid_identifiers(value):
    with pytest.raises(InvalidVideoIdentifierException):
        Video(value)


def test_bare_id():
    assert Video('YE7VzlLtp-4').video_id == 'YE7VzlLtp-4'


def test_error_mentions_input():
    with pytest.raises(InvalidVideoIdentifierException, match='not a url'):
        Video('not a url at all')
