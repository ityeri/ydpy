<h1 align="center">ydpy</h1>

<div align="center">
  <b><code>Youtube </code></b><br>
  <b><code>Download</code></b><br>
  <b><code>PYthon  </code></b><br>
</div>

<br>

<p align="center">
  Clean-room, low-level YouTube download library: multi-client bot-bypass, fast streams, sync &amp; async
</p>

<p align="center">
  <a href="LICENSE"><img src="https://img.shields.io/badge/License-MIT-yellow.svg" alt="License: MIT"></a>
  <img src="https://img.shields.io/badge/python-3.10%2B-blue" alt="Python: 3.10+">
  <img src="https://img.shields.io/pypi/v/ydpy" alt="PyPI version">
</p>

---

- Clean-room reimplementation of yt-dlp's YouTube bot-bypass knowledge — not a fork
- Multi-client innertube requests (visionos / tv / mweb / android_vr) with real visitor data
- Fetches the playable stream list of a single video, nothing else: no playlist expansion, no merging, no post-processing
- Downloads an individual stream as-is into a path or any buffer — no ffmpeg, no filename magic
- Sync and async APIs (async is the same name prefixed with `a`)
- python >= 3.10

## Install

Using uv & pip
```bash
pip install ydpy # or: uv add ydpy
```
Using pyproject.toml
```toml
[project]
dependencies = [
    "ydpy"
]
```

## Quickstart

```python
import ydpy

video = ydpy.Video("https://www.youtube.com/watch?v=YE7VzlLtp-4")

data = video.fetch()          # or: await video.afetch()
for fmt in data.formats:
    print(fmt.itag, fmt.mime_type, fmt.width, fmt.height, fmt.bitrate)

# pick the best audio stream
audio = max(
    (f for f in data.formats if f.is_audio),
    key=lambda f: f.bitrate or 0
)

audio.download("song.webm")                       # local path
audio.download(open("song.webm", "wb"))           # or file-like

import io
buf = io.BytesIO()
audio.download(buf)                               # or memory buffer
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

## Options & progress

You can specify the progress logic and throttle limit or etc. like below:

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

## How it avoids bot detection & why it is fast

Every request to YouTube is shaped like an official app, not a scraper:

- requests go to the innertube API pretending to be one of several real
  clients (visionos / an old smart-tv app / mweb / an android-vr app), each
  with its own device headers and body context;
- the visitor data used for anonymous playback is taken from the actual watch
  page first, because keyless anonymous API calls are answered with
  "Sign in to confirm you're not a bot";
- if one client gets rejected, the next client in the chain is tried, and
  transient bot gates are retried;
- clients that require the newest attestation (web + PO tokens) are simply
  not used — JS challenge solving and PO token minting are **out of scope**,
  and no client in the chain needs them.

Speed is mostly a side effect of not being throttled:

- googlevideo throttles Range-less full-file fetches to ~32 KB/s, so every
  download always sends a `Range` header (measured 2026-09);
- googlevideo also throttles long-lived single connections, so downloads are
  pulled as sequential 10 MiB range chunks — the same trick yt-dlp uses;
- compression is disabled (`Accept-Encoding: identity`) so `Content-Length`
  stays reliable and no decode CPU is wasted;
- one httpx client is reused for the whole download (keep-alive, no repeated
  TLS handshakes) and reads adapt to the measured throughput;
- failed transfers resume from the last byte instead of restarting.

## Benchmarks

Same video, same stream url, same resulting file size — wall time from start
to finish (extraction included where applicable). Measured 2026-09-05 from a
datacenter VM; numbers vary with network and region.

| format | yt-dlp CLI | ydpy |
|---|---|---|
| audio itag 251 (9.7 MB) | 2.71s (~3.6 MB/s) | **1.37s (~7.1 MB/s)** |
| video itag 136 (75 MB, 720p) | 4.26s (~17.6 MB/s) | **~3.3s transfer (19–28 MB/s sustained)** |

Before the chunked-range fix the 75 MB video crawled at 0.3 MB/s — exactly the
long-connection throttle this library is built to avoid.

## Format at a glance

```python
best_video = max(
    (f for f in data.formats if f.is_video and not f.is_damaged),
    key=lambda f: (f.height or 0, f.bitrate or 0),
)

best_video.itag          # 137 — stable identifier
best_video.mime_type     # 'video/mp4; codecs="avc1.64001f, mp4a.40.2"'
best_video.width, best_video.height, best_video.fps
best_video.bitrate       # bps
best_video.filesize      # bytes, when the player response knows it
best_video.has_drm       # True → skip it
best_video.protocol      # ydpy.StreamingProtocol.HTTPS / HLS / DASH
best_video.download("clip.mp4")
```

`Format` is a frozen dataclass — every stream is just data you can inspect,
filter, and hand to `download()` / `adownload()`.

## Why not just use yt-dlp or pytube as a library?

Neither supports async. You can wrap them with `asyncio.to_thread`, but a
CLI-shaped library occasionally blocks the event loop and is inefficient.

yt-dlp is fundamentally a CLI tool, so its "library" mode is a shell
invocation wearing a trench coat. Conveniences that are great for a CLI
become surprising side effects for a library:

- a video url that belongs to a playlist downloads **the whole playlist**
  unless you remember the `noplaylist` flag;
- it merges audio/video with ffmpeg, re-encodes when asked, and applies its
  own filename rules — control flow you cannot turn off;
- configuration is either shell arguments or a CLI-flavored options dict;

```python
import yt_dlp  # the CLI-args shaped library API

ydl_opts = {
    "format": "bestaudio/best",
    "outtmpl": "song.%(ext)s",
    "quiet": True,
    "noplaylist": True,        # or it silently downloads the playlist
    "postprocessors": [{"key": "FFmpegExtractAudio"}],
}
with yt_dlp.YoutubeDL(ydl_opts) as ydl:
    info = ydl.extract_info(url, download=False)
```

ydpy takes the opposite route: `Video(url).fetch()` returns playable streams
and nothing else happens. No downloads you did not ask for, no merging, no
filesystem conventions — the stream is yours to save to a path, a buffer, or
hand to whatever comes next.
