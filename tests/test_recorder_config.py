"""
Tests for audio recorder configuration

Tests that the ContinuousRecorder uses the correct buffer size from
config.BUFFER_MINUTES instead of hardcoded values.

Regression test for BUG-2026-02-06-002: Buffer size mismatch
"""

import sys
from pathlib import Path
from unittest.mock import Mock, patch


# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

import config
from audio.recorder import ContinuousRecorder


def test_recorder_uses_config_buffer_minutes():
    """Test that ContinuousRecorder uses config.BUFFER_MINUTES when instantiated with it"""
    # Verify config has BUFFER_MINUTES set to 5
    assert config.BUFFER_MINUTES == 5

    # Create recorder with config value (as main_window.py should do)
    with patch("audio.recorder.sc.get_microphone") as mock_mic:
        mock_mic.return_value = Mock()
        recorder = ContinuousRecorder(buffer_minutes=config.BUFFER_MINUTES)

    # Verify recorder uses the config value
    assert recorder.buffer_minutes == 5
    assert recorder.buffer_minutes == config.BUFFER_MINUTES


def test_recorder_buffer_chunks_calculation():
    """Test that buffer chunks are calculated correctly based on buffer_minutes"""
    # With 5 minutes and 1-second chunks, should have 300 chunks
    with patch("audio.recorder.sc.get_microphone") as mock_mic:
        mock_mic.return_value = Mock()
        recorder = ContinuousRecorder(buffer_minutes=5, chunk_seconds=1)

    # 5 minutes * 60 seconds/minute / 1 second/chunk = 300 chunks
    expected_chunks = 5 * 60 // 1
    assert recorder.buffer_chunks == expected_chunks


def test_recorder_different_buffer_sizes():
    """Test that recorder works with different buffer sizes from config"""
    test_buffer_sizes = [3, 5, 7, 10]

    for buffer_size in test_buffer_sizes:
        with patch("audio.recorder.sc.get_microphone") as mock_mic:
            mock_mic.return_value = Mock()
            recorder = ContinuousRecorder(buffer_minutes=buffer_size)

        assert recorder.buffer_minutes == buffer_size
        # Verify buffer_chunks calculation
        expected_chunks = buffer_size * 60 // 1  # chunk_seconds defaults to 1
        assert recorder.buffer_chunks == expected_chunks


def test_regression_bug_002_buffer_not_hardcoded():
    """
    Regression test for BUG-2026-02-06-002

    Ensures that the recorder is NOT hardcoded to 3 minutes.
    This test will fail if someone reverts to hardcoding buffer_minutes=3.
    """
    # Verify config.BUFFER_MINUTES is 5 (not 3)
    assert config.BUFFER_MINUTES == 5, "Config should specify 5-minute buffer"

    # Create recorder using config (as main_window.py does)
    with patch("audio.recorder.sc.get_microphone") as mock_mic:
        mock_mic.return_value = Mock()
        recorder = ContinuousRecorder(buffer_minutes=config.BUFFER_MINUTES)

    # The bug was: recorder used 3 minutes despite config saying 5
    # This test ensures it uses config value, not hardcoded 3
    assert recorder.buffer_minutes == config.BUFFER_MINUTES, (
        "Recorder MUST use config.BUFFER_MINUTES, not hardcoded value"
    )
    assert recorder.buffer_minutes != 3, (
        "Recorder should NOT be hardcoded to 3 minutes (regression check)"
    )
    assert recorder.buffer_minutes == 5, "Recorder should use configured 5-minute buffer"


if __name__ == "__main__":
    import pytest

    # Run tests with pytest
    pytest.main([__file__, "-v"])
