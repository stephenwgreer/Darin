"""Tests for ContinuousRecorder buffer configuration.

Regression guard for BUG-2026-02-06-002 (buffer size hardcoded to 3 minutes)
plus the DAR2-24 capture format: 16 kHz int16, 100 ms chunks, (1600, 2) shape.
"""

import config
from audio.recorder import ContinuousRecorder


def test_config_audio_constants() -> None:
    """The capture pipeline contract: 16 kHz, 100 ms chunks, 5 min buffer."""
    assert config.SAMPLE_RATE == 16000
    assert config.CHUNK_SECONDS == 0.1
    assert isinstance(config.CHUNK_SECONDS, float)
    assert config.BUFFER_MINUTES == 5
    assert config.DEEPGRAM_SAMPLE_RATE == 16000
    assert config.DEEPGRAM_MODEL == "nova-3"


def test_recorder_uses_config_buffer_minutes() -> None:
    recorder = ContinuousRecorder(buffer_minutes=config.BUFFER_MINUTES)
    assert recorder.buffer_minutes == config.BUFFER_MINUTES


def test_recorder_buffer_chunks_calculation() -> None:
    """buffer_chunks = buffer_minutes * 60 / chunk_seconds."""
    recorder = ContinuousRecorder(buffer_minutes=5, chunk_seconds=0.1)
    assert recorder.buffer_chunks == 3000


def test_recorder_chunk_frames_is_100ms_at_16khz() -> None:
    recorder = ContinuousRecorder()
    assert recorder.sample_rate == 16000
    assert recorder.chunk_seconds == 0.1
    assert recorder.chunk_frames == 1600


def test_recorder_does_not_resolve_devices_at_init() -> None:
    """Devices must be resolved fresh in start_recording(), not __init__."""
    recorder = ContinuousRecorder()
    assert not recorder.is_recording
    assert recorder.sources_active == {"me": False, "them": False}


def test_regression_buffer_not_hardcoded_to_3() -> None:
    """Config must be 5 minutes and the recorder must use it, not hardcode 3."""
    assert config.BUFFER_MINUTES == 5
    recorder = ContinuousRecorder(buffer_minutes=config.BUFFER_MINUTES)
    assert recorder.buffer_minutes == 5
    assert recorder.buffer_minutes != 3
