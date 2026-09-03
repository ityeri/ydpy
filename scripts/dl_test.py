"""Live download test: fetch a video's streams and save one to file + buffer.

Usage (from repo root):
  uv run python scripts/dl_test.py YE7VzlLtp-4
  uv run python scripts/dl_test.py <url> --itag 248
  uv run python scripts/dl_test.py <id> --audio --async
"""

from __future__ import annotations

import argparse
import asyncio
import io
import pathlib
import sys

from ydpy import Video
from ydpy.downloader import DownloadOptions
from ydpy.exceptions import YdpyException
from ydpy.streams import Format


def _pick_format(data, args) -> Format:
    """Pick the requested or best-suitable format."""
    formats = [f for f in data.formats if not f.has_drm]
    if args.itag:
        for fmt in formats:
            if fmt.itag == args.itag:
                return fmt
        raise SystemExit(f'no format with itag {args.itag}')
    if args.audio:
        audio = sorted((f for f in formats if f.is_audio and not f.is_damaged),
                       key=lambda f: f.bitrate or 0, reverse=True)
        if not audio:
            raise SystemExit('no audio format found')
        return audio[0]
    videos = sorted((f for f in formats if f.is_video and not f.is_damaged),
                    key=lambda f: ((f.height or 0) <= (args.max_height or 720),
                                   f.height or 0, f.bitrate or 0), reverse=True)
    if not videos:
        raise SystemExit('no video format found')
    return videos[0]


def _verify(out_file: pathlib.Path, buffer: io.BytesIO, expected: int | None) -> None:
    """File and buffer must agree byte-for-byte with the advertised size."""
    file_bytes = out_file.read_bytes()
    buffer.seek(0)
    assert file_bytes == buffer.read(), 'file and buffer contents differ!'
    if expected is not None and len(file_bytes) != expected:
        raise SystemExit(f'size mismatch: got {len(file_bytes)} expected {expected}')
    print(f'   verify: file == buffer, {len(file_bytes)} bytes '
          f'({"ok" if expected is None else "== contentLength"})')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('identifier')
    parser.add_argument('--itag', type=int, default=None)
    parser.add_argument('--audio', action='store_true')
    parser.add_argument('--max-height', type=int, default=720)
    parser.add_argument('--async', dest='use_async', action='store_true')
    parser.add_argument('--out', type=pathlib.Path,
                        default=pathlib.Path('/tmp/ydpy-dltest'))
    args = parser.parse_args()

    data = Video(args.identifier).fetch()
    print(f'video: {data.video_id} {data.title!r} ({data.duration_ms} ms, client={data.client})')
    fmt = _pick_format(data, args)
    print(f'picked: itag={fmt.itag} {fmt.mime_type} '
          f'{"x".join(str(x) for x in (fmt.width, fmt.height) if x)} '
          f'codecs={fmt.codecs} bitrate={fmt.bitrate} filesize={fmt.filesize}')
    if 'n=' in fmt.url:
        print('note: url carries n param (downloading as-is)')

    out_file = args.out / f'{data.video_id}-{fmt.itag}.bin'
    out_file.parent.mkdir(parents=True, exist_ok=True)
    buffer = io.BytesIO()
    options = DownloadOptions(progress=None)
    if args.use_async:
        asyncio.run(_async_download(fmt, out_file, buffer, options))
    else:
        result = fmt.download(out_file, options=options)
        fmt.download(buffer, options=options)
        print(f'   file : {result.bytes_written} bytes in {result.elapsed_seconds:.2f}s '
              f'({result.bytes_written / result.elapsed_seconds / 1_000_000:.2f} MB/s)')
    _verify(out_file, buffer, fmt.filesize)
    print('   PASS')


async def _async_download(fmt: Format, out_file: pathlib.Path, buffer: io.BytesIO,
                          options: DownloadOptions) -> None:
    result = await fmt.adownload(out_file, options=options)
    await fmt.adownload(buffer, options=options)
    print(f'   file : {result.bytes_written} bytes in {result.elapsed_seconds:.2f}s '
          f'({result.bytes_written / result.elapsed_seconds / 1_000_000:.2f} MB/s)')


if __name__ == '__main__':
    try:
        main()
    except YdpyException as e:
        print(f'FAIL {type(e).__name__}: {e}')
        sys.exit(1)
