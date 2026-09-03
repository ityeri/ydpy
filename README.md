# ydpy

Low-level, YouTube-only stream fetching/downloading library.

- Fetches the playable stream list of a single video (no playlist expansion, ever)
- Downloads an individual stream as-is: no remuxing, no ffmpeg, no filename magic
- Carries the bot-bypass knowledge over from yt-dlp (multi-client innertube, n/sig JS
  challenge solving via a real JS runtime, PO token policy) with a clean-room codebase
- Sync + async APIs, sink-based output (file path / file-like / memory buffer)
- Python >= 3.11, deps: httpx + yarl

> Under active development — see [docs/SPEC.md](docs/SPEC.md) for the full spec and milestones.
