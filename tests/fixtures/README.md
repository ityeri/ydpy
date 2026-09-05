# Fixtures

Captured live from YouTube on 2026-09-05 (video YE7VzlLtp-4, Big Buck Bunny)
and trimmed for offline parsing tests:

| file | origin |
|---|---|
| `watch_page.html` | watch page — real `ytcfg.set({...})` (INNERTUBE_API_KEY / VISITOR_DATA / PLAYER_JS_URL) + a minimal `ytInitialPlayerResponse` wrapper |
| `player_response.json` | visionos client `youtubei/v1/player` response — adaptive formats (urls shortened to `rr.example`) + hlsManifestUrl presence |
| `hls_master.m3u8` | real visionos HLS master playlist (unaltered) |
| `hls_media.m3u8` | media playlist header + first segments (urls shortened) |

Stream urls expire quickly, so nothing in here is fetchable — parse tests never touch the network.
