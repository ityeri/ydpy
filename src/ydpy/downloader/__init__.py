"""Downloaders: continuous single-url (http) and segmented manifest (hls/dash)."""

from ydpy.downloader.http_downloader import adownload_stream, download_stream
from ydpy.downloader.segment_downloader import (
    adownload_dash,
    adownload_hls,
    download_dash,
    download_hls,
)
from ydpy.downloader.utils import DownloadOptions, DownloadProgress, DownloadResult, Sink

__all__ = [
    'download_stream',
    'adownload_stream',
    'download_hls',
    'adownload_hls',
    'download_dash',
    'adownload_dash',
    'DownloadOptions',
    'DownloadProgress',
    'DownloadResult',
    'Sink',
]
