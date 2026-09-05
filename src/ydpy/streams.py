"""Stream models: parsed format entries and the video-level snapshot."""

from __future__ import annotations

import dataclasses
import enum
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

import yarl

if TYPE_CHECKING:
    from ydpy.downloader.utils import Target

from ydpy.exceptions import DataParsingException

__all__ = [
    'Container',
    'VideoCodec',
    'AudioCodec',
    'StreamingProtocol',
    'Format',
    'VideoData',
]


class StreamingProtocol(str, enum.Enum):
    """How a stream is delivered: one url, or a manifest of segments."""

    HTTPS = 'https'
    HLS = 'hls'
    DASH = 'dash'


class Container(str, enum.Enum):
    """Container name as it appears in a mime type."""

    MP4 = 'mp4'
    WEBM = 'webm'

    @classmethod
    def from_mime(cls, mime_type: str | None) -> 'Container | None':
        """Derive the container from a mime type like 'video/mp4; codecs=...'."""
        if not mime_type:
            return None
        container_name = mime_type.split(';', 1)[0].split('/', 1)[-1].strip()
        for container in cls:
            if container.value == container_name:
                return container
        return None


class VideoCodec(str, enum.Enum):
    """Video codec family, derived from the leading codec identifier."""

    AVC1 = 'avc1'
    VP8 = 'vp8'
    VP9 = 'vp9'
    AV01 = 'av01'

    @classmethod
    def from_codec(cls, codec: str) -> 'VideoCodec | None':
        """Map a codec id like 'avc1.4d401f' to its family."""
        family = codec.split('.', 1)[0]
        for member in cls:
            if member.value == family:
                return member
        return None


class AudioCodec(str, enum.Enum):
    """Audio codec family, derived from the leading codec identifier."""

    MP4A = 'mp4a'
    OPUS = 'opus'
    VORBIS = 'vorbis'
    EC3 = 'ec-3'
    AC3 = 'ac-3'
    FLAC = 'flac'
    MP3 = 'mp3'

    @classmethod
    def from_codec(cls, codec: str) -> 'AudioCodec | None':
        """Map a codec id like 'mp4a.40.2' to its family."""
        family = codec.split('.', 1)[0]
        for member in cls:
            if member.value == family:
                return member
        return None


def _int_or_none(value: Any) -> int | None:
    """Coerce a JSON number-or-string to int, tolerating garbage."""
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


@dataclass(frozen=True, slots=True)
class Format:
    """One playable stream of a video. Immutable; URL tweaks return copies."""

    itag: int
    client: str
    url: str
    protocol: StreamingProtocol = StreamingProtocol.HTTPS
    mime_type: str | None = None
    codecs: str | None = None
    width: int | None = None
    height: int | None = None
    fps: int | None = None
    bitrate: int | None = None
    filesize: int | None = None
    approx_duration_ms: int | None = None
    has_drm: bool = False
    quality_label: str | None = None
    requires_pot: bool = False
    is_damaged: bool = False

    @property
    def is_video(self) -> bool:
        """True when the stream carries a video track."""
        return bool(self.mime_type and self.mime_type.startswith('video/'))

    @property
    def is_audio(self) -> bool:
        """True when the stream carries only audio."""
        return bool(self.mime_type and self.mime_type.startswith('audio/'))

    @property
    def container(self) -> Container | None:
        """Container of the stream, when recognizable."""
        return Container.from_mime(self.mime_type)

    @property
    def video_codec(self) -> VideoCodec | None:
        """Video codec family, when present in the codec list."""
        if not self.codecs or not self.is_video:
            return None
        return VideoCodec.from_codec(self.codecs.split(',', 1)[0])

    @property
    def audio_codec(self) -> AudioCodec | None:
        """Audio codec family. Progressive streams carry it after the video codec."""
        if not self.codecs:
            return None
        tokens = self.codecs.split(',')
        if self.is_audio:
            return AudioCodec.from_codec(tokens[0])
        if len(tokens) > 1:
            return AudioCodec.from_codec(tokens[1])
        return None

    @staticmethod
    def from_json(raw: dict[str, Any], *, client: str) -> 'Format':
        return Format.from_stream(raw, client=client, protocol=StreamingProtocol.HTTPS)

    @staticmethod
    def from_stream(raw: dict[str, Any], *, client: str,
                    protocol: StreamingProtocol) -> 'Format':
        """Parse one streamingData format entry into a Format."""
        try:
            mime_type = raw.get('mimeType')
            return Format(
                itag=_int_or_none(raw.get('itag')) or 0,
                client=client,
                url=raw.get('url') or '',
                protocol=protocol,
                mime_type=mime_type,
                codecs=_extract_codecs(mime_type),
                width=_int_or_none(raw.get('width')),
                height=_int_or_none(raw.get('height')),
                fps=_int_or_none(raw.get('fps')),
                bitrate=_int_or_none(raw.get('bitrate') or raw.get('averageBitrate')),
                filesize=_int_or_none(raw.get('contentLength')),
                approx_duration_ms=_int_or_none(raw.get('approxDurationMs')),
                has_drm=bool(raw.get('drmFamilies')),
                quality_label=raw.get('qualityLabel') or raw.get('quality'),
            )
        except (AttributeError, KeyError) as e:
            raise DataParsingException(f'Malformed format entry: {e}') from e

    def with_n(self, solved: str) -> 'Format':
        """Return a copy whose stream url carries the solved n value."""
        return dataclasses.replace(self, url=str(yarl.URL(self.url).update_query({'n': solved})))

    def with_pot(self, token: str) -> 'Format':
        """Return a copy whose stream url carries the given po token."""
        return dataclasses.replace(self, url=str(yarl.URL(self.url).update_query({'pot': token})))

    def download(self, target: Target, **kwargs: Any):
        """Download this stream into a path or a file-like sink (sync)."""
        if self.protocol is StreamingProtocol.HTTPS:
            from ydpy.downloader import download_stream
            return download_stream(self.url, target, **kwargs)
        if self.protocol is StreamingProtocol.HLS:
            from ydpy.downloader import download_hls
            return download_hls(self.url, target, **kwargs)
        from ydpy.downloader import download_dash
        return download_dash(self.url, target, **kwargs)

    async def adownload(self, target: Target, **kwargs: Any):
        """Download this stream into a path or a file-like sink (async)."""
        if self.protocol is StreamingProtocol.HTTPS:
            from ydpy.downloader import adownload_stream
            return await adownload_stream(self.url, target, **kwargs)
        if self.protocol is StreamingProtocol.HLS:
            from ydpy.downloader import adownload_hls
            return await adownload_hls(self.url, target, **kwargs)
        from ydpy.downloader import adownload_dash
        return await adownload_dash(self.url, target, **kwargs)


def _extract_codecs(mime_type: str | None) -> str | None:
    """Pull the codecs attribute out of 'video/mp4; codecs=\"avc1...,mp4a...\"'."""
    if not mime_type or 'codecs=' not in mime_type:
        return None
    codecs_part = mime_type.split('codecs=', 1)[1].strip()
    return codecs_part.strip('"')


@dataclass(frozen=True, slots=True)
class VideoData:
    """Immutable snapshot of one video's playable streams."""

    video_id: str
    title: str | None
    duration_ms: int | None
    client: str
    formats: tuple[Format, ...]
