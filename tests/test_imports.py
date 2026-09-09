"""Import-order matrix in fresh interpreters + module attribute access.

Regression for the client <-> request.player partial-initialization cycle and
the playable_video -> package-root import: every import order must work and
the public module surface (ydpy.request.player, ydpy.downloader, ...) must
stay reachable as plain attributes after `import ydpy`.
"""

import subprocess
import sys

import pytest

IMPORT_CODES = [
    'import ydpy',
    'import ydpy.client',
    'import ydpy.constants',
    'import ydpy.request',
    'import ydpy.request.player',
    'import ydpy.request.utils',
    'import ydpy.request.webpage',
    'import ydpy.downloader',
    'import ydpy.downloader.http_downloader',
    'import ydpy.downloader.segment_downloader',
    'import ydpy.playable_video',
    'import ydpy.streams',
    'from ydpy.playable_video import PlayableVideo',
    'from ydpy.client import CLIENTS; import ydpy.request.player'
]


@pytest.mark.parametrize('code', IMPORT_CODES)
def test_fresh_interpreter_import(code):
    result = subprocess.run([sys.executable, '-c', code],
                            capture_output=True, text=True, timeout=60)
    assert result.returncode == 0, f'{code!r} failed: {result.stderr[-500:]}'


def test_module_attribute_access_after_import_ydpy():
    import ydpy
    assert ydpy.PlayableVideo
    assert ydpy.Format
    assert ydpy.request.player.get_player
    assert ydpy.request.webpage.get_watch_page
    assert ydpy.request.utils.BROWSER_USER_AGENT
    assert ydpy.downloader.download_stream
    assert ydpy.client.CLIENTS
    assert ydpy.exceptions.YdpyException
