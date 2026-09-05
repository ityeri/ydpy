<h1 align="center">ydpy</h1>

<div align="center">
  <div align="left" style="width: fit-content">
    <b>Youtube</b><br>
    <b>Download</b><br>
    <b>PYthon</b><br>
  </div>
</div>

<p align="center">
  Fast, lightweight, simple, with rich-bot-detection-avoidance youtube download library written in python
</p>

<p align="center">
  <a href="LICENSE"><img src="https://img.shields.io/badge/License-MIT-yellow.svg" alt="License: MIT"></a>
</p>

---

- Rich support for Sync and async APIs
- Carries over yt-dlp's bot-bypass knowledge
  (multi-client innertube, JS challenge solving, PO token policy) (but this is not a fork, code is cleen-room)
- Fetches the playable stream list of a single video
- Downloads an individual stream as-is: no remuxing, no ffmpeg, no filename magic
- python >= 3.11


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


## What is the difference between pytube and yt-dlp
Neither supports async. It can be circumvented by using `asyncio.to_thread`, etc.,
but it causes an unexpected event loop blocking occasionally and inefficient.

for yt-dlp,
Basically, yt-dlp is a CLI tool, so the library is just a shell invoking it internally.
Because of that, yt-dlp has a lot of convenience features
like auto video and audio synthesizing or playlist downloading.

But from the perspective of library, this means yt-dlp has many unexpected behaviors.
And because yt-dlp is a CLI tool, configurations should also fit a CLI
