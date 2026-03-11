"""Tests for ContinuousRecorder buffer configuration.

Regression guard for BUG-2026-02-06-002: buffer size was hardcoded to 3 minutes
instead of reading from config.BUFFER_MINUTES (5 minutes).
"""

from unittest.mock import Mock, patch

import config
from audio.recorder import ContinuousRecorder


def _make_recorder(**kwargs) -> ContinuousRecorder:
    with patch("audio.recorder.sc.get_microphone", return_value=Mock()):
        return ContinuousRecorder(**kwargs)


def test_recorder_uses_config_buffer_minutes() -> None:
    recorder = _make_recorder(buffer_minutes=config.BUFFER_MINUTES)
    assert recorder.buffer_minutes == config.BUFFER_MINUTES


def test_recorder_buffer_chunks_calculation() -> None:
    """buffer_chunks = buffer_minutes * 60 / chunk_seconds."""
    recorder = _make_recorder(buffer_minutes=5, chunk_seconds=1)
    assert recorder.buffer_chunks == 300


def test_regression_buffer_not_hardcoded_to_3() -> None:
    """Config must be 5 minutes and the recorder must use it, not hardcode 3."""
    assert config.BUFFER_MINUTES == 5
    recorder = _make_recorder(buffer_minutes=config.BUFFER_MINUTES)
    assert recorder.buffer_minutes == 5
    assert recorder.buffer_minutes != 3
