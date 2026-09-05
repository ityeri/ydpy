"""Shared plumbing for the ydpy downloader subpackage."""

from __future__ import annotations

import io
import os
from dataclasses import dataclass
from typing import BinaryIO, Callable, TypeAlias

from ydpy.request.utils import BROWSER_USER_AGENT

__all__ = [
    'Sink',
    'Target',
    'DownloadOptions',
    'DownloadProgress',
    'DownloadResult',
    'STREAM_HEADERS',
    'open_target',
]

# Commonly-used writable-bytes targets. Structural at runtime: anything with a
# write(data: bytes) method works, even when it is not in this union.
Sink: TypeAlias = BinaryIO | io.BufferedIOBase | io.RawIOBase

# What a download accepts: a local path or a sink to write into.
Target: TypeAlias = str | os.PathLike[str] | Sink


@dataclass(frozen=True, slots=True)
class DownloadOptions:
    """Tuning knobs for one download call."""

    retries: int = 5
    timeout: float = 30.0
    initial_block_size: int = 256 * 1024
    throttled_rate_limit: int | None = None
    verify_tls: bool = True
    http2: bool = False
    proxy: str | None = None
    progress: Callable[['DownloadProgress'], None] | None = None


@dataclass(frozen=True, slots=True)
class DownloadProgress:
    """Periodic progress report handed to the progress callback."""

    downloaded: int
    total: int | None
    speed_bps: float | None
    elapsed_seconds: float


@dataclass(frozen=True, slots=True)
class DownloadResult:
    """Outcome of a successful download."""

    bytes_written: int
    elapsed_seconds: float
    url: str


# Stream fetches disable compression so Content-Length stays reliable.
STREAM_HEADERS = {'User-Agent': BROWSER_USER_AGENT, 'Accept-Encoding': 'identity'}


def open_target(target: Target) -> tuple[Sink, bool]:
    """Return (sink, should_close); path targets are opened for writing."""
    if isinstance(target, (str, bytes, os.PathLike)):
        opened = open(target, 'wb')
        return opened, True
    if hasattr(target, 'write'):
        return target, False
    raise TypeError(f'Download target must be a path or a file-like object, got {type(target)!r}')
