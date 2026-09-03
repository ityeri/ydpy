# ydpy

Low-level, YouTube-only stream fetching/downloading library.

- Fetches the playable stream list of a single video — no playlist expansion, ever
- Downloads an individual stream as-is: no remuxing, no ffmpeg, no filename magic
- Carries over yt-dlp's bot-bypass knowledge (multi-client innertube, JS challenge
  solving, PO token policy) with a clean-room codebase
- Sync **and** async APIs, sink-based output (path / file-like / memory buffer)
- Python >= 3.11, dependencies: `httpx` + `yarl`

> Under active development — live-verified findings and the project plan are
> kept out-of-repo in the maintainer's notes.

## Install

```bash
uv add ydpy        # or: pip install ydpy
```

## Quickstart

```python
import ydpy

video = ydpy.Video("https://www.youtube.com/watch?v=YE7VzlLtp-4")

data = video.fetch()          # or: await video.afetch()
for fmt in data.formats:
    print(fmt.itag, fmt.mime_type, fmt.width, fmt.height, fmt.bitrate)

# pick the best audio stream
audio = max((f for f in data.formats if f.is_audio),
            key=lambda f: f.bitrate or 0)
audio.download("song.webm")                       # local path
audio.download(open("song.webm", "wb"))           # file-like
import io
buf = io.BytesIO()
audio.download(buf)                               # memory buffer
```

Async download:

```python
import asyncio

async def main():
    data = await ydpy.Video("...").afetch()
    fmt = next(f for f in data.formats if f.itag == 137)
    result = await fmt.adownload("video.mp4")
    print(f"{result.bytes_written} bytes")

asyncio.run(main())
```

## Format objects

`Format` is an immutable snapshot of one stream. Properties: `itag`, `mime_type`,
`container`, `video_codec`, `audio_codec`, `width`, `height`, `fps`, `bitrate`,
`filesize`, `approx_duration_ms`, `quality_label`, `has_drm`, `is_video`,
`is_audio`, `is_damaged`. URL tweaks return copies: `fmt.with_n(...)`,
`fmt.with_pot(...)`.

## Options & progress

```python
from ydpy import DownloadOptions

def progress(p):
    print(f"{p.downloaded}/{p.total} bytes at {p.speed_bps / 1e6:.1f} MB/s")

fmt.download("out.webm", options=DownloadOptions(
    retries=5,
    timeout=30.0,
    throttled_rate_limit=500_000,     # raise ThrottledDownload if sustained slower
    progress=progress,
))
```

Downloads always use `Accept-Encoding: identity` plus a `Range` header
(googlevideo throttles Range-less full fetches to ~32 KB/s) and adapt the read
buffer up to 4 MiB. Transport errors retry with resume from the last byte.

## Errors

All exceptions derive from `ydpy.exceptions.YdpyException`:
`InvalidVideoIdentifierException`, `RequestException`, `DataParsingException`,
`ExtractionException`, `DownloadException`, `ThrottledDownload`.

## Current status (2026-09)

- Primary path: anonymous `visionos` client — playable formats with direct URLs,
  no JS challenge, no PO token needed (live-verified full speed)
- Web client streams need a PO token provider (planned)
- Not included: merging, playlists, availability checks (yspy territory), login

## Dev

```bash
uv sync
uv run python scripts/probe.py <video_id>    # raw per-client probe
uv run python scripts/dl_test.py <video_id>  # download test (file + buffer)
```
