"""Downloader shared utils tests (no network)."""

import io

import pytest

from ydpy.downloader.utils import open_target


def test_best_block_size_bounds():
    from ydpy.downloader.http_downloader import MAX_BLOCK_SIZE, best_block_size

    assert best_block_size(0.0001, 1024 * 1024) <= MAX_BLOCK_SIZE
    assert 1 <= best_block_size(5.0, 1024)
    # fast rate grows the block, slow rate shrinks it
    fast = best_block_size(0.001, 1024 * 1024)
    slow = best_block_size(10.0, 1024 * 1024)
    assert fast >= slow


def test_open_target_path(tmp_path):
    target = tmp_path / 'out.bin'
    sink, should_close = open_target(target)
    assert should_close is True
    sink.write(b'hello')
    sink.close()
    assert target.read_bytes() == b'hello'


def test_open_target_buffer_passthrough():
    buffer = io.BytesIO()
    sink, should_close = open_target(buffer)
    assert should_close is False
    assert sink is buffer


def test_open_target_rejects_garbage():
    with pytest.raises(TypeError):
        open_target(12345)
