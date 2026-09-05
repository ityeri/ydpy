"""ydpy — low-level YouTube stream fetching & downloading."""

# Single source of truth: dist metadata (dev stamps from CI, etc.);
# falls back to the constant when running from a source tree.
__version__ = '0.1.0'
try:
    from importlib.metadata import version as _package_version
    __version__ = _package_version('ydpy')
except Exception:  # pragma: no cover - source checkout without install
    pass

from ydpy.downloader import DownloadOptions, DownloadResult
from ydpy.streams import (AudioCodec, Container, Format, StreamingProtocol,
                           VideoCodec, VideoData)
from ydpy.video import Video

__all__ = [
    'Video',
    'VideoData',
    'Format',
    'StreamingProtocol',
    'DownloadOptions',
    'DownloadResult',
    'Container',
    'VideoCodec',
    'AudioCodec',
]
