"""Tests for ContinuousRecorder consumer registration API (DAR2-24).

Tests the add_chunk_consumer / remove_chunk_consumer fan-out pattern
that replaces the single-slot _on_chunk callback.
"""

import threading
from unittest.mock import Mock, patch

import numpy as np
import pytest

from audio.recorder import ContinuousRecorder


@pytest.fixture
def recorder():
    """Create a ContinuousRecorder with mocked soundcard."""
    with patch("audio.recorder.sc.get_microphone") as mock_mic:
        mock_mic.return_value = Mock()
        rec = ContinuousRecorder(buffer_minutes=1)
    return rec


class TestConsumerRegistration:
    """Test add/remove consumer API."""

    def test_add_chunk_consumer(self, recorder):
        """Test registering a consumer."""
        callback = Mock()
        recorder.add_chunk_consumer(callback)
        assert callback in recorder._chunk_consumers

    def test_remove_chunk_consumer(self, recorder):
        """Test unregistering a consumer."""
        callback = Mock()
        recorder.add_chunk_consumer(callback)
        recorder.remove_chunk_consumer(callback)
        assert callback not in recorder._chunk_consumers

    def test_duplicate_registration_ignored(self, recorder):
        """Test adding same consumer twice is a no-op."""
        callback = Mock()
        recorder.add_chunk_consumer(callback)
        recorder.add_chunk_consumer(callback)
        assert recorder._chunk_consumers.count(callback) == 1

    def test_remove_nonexistent_consumer_noop(self, recorder):
        """Test removing a consumer that was never added does not raise."""
        callback = Mock()
        recorder.remove_chunk_consumer(callback)  # should not raise

    def test_on_chunk_constructor_param_registers_consumer(self):
        """Test on_chunk constructor param registers as a consumer."""
        callback = Mock()
        with patch("audio.recorder.sc.get_microphone") as mock_mic:
            mock_mic.return_value = Mock()
            rec = ContinuousRecorder(buffer_minutes=1, on_chunk=callback)
        assert callback in rec._chunk_consumers


class TestChunkFanout:
    """Test that chunks are delivered to all registered consumers."""

    def test_single_consumer_receives_chunks(self, recorder):
        """Test a single consumer receives audio chunks."""
        callback = Mock()
        recorder.add_chunk_consumer(callback)

        chunk = np.zeros((48000, 2), dtype=np.float32)
        recorder._deliver_to_consumers(chunk)

        callback.assert_called_once()
        delivered = callback.call_args[0][0]
        np.testing.assert_array_equal(delivered, chunk)

    def test_multiple_consumers_receive_same_chunk(self, recorder):
        """Test all consumers receive the same chunk."""
        cb1 = Mock()
        cb2 = Mock()
        cb3 = Mock()
        recorder.add_chunk_consumer(cb1)
        recorder.add_chunk_consumer(cb2)
        recorder.add_chunk_consumer(cb3)

        chunk = np.ones((48000, 2), dtype=np.float32) * 0.5
        recorder._deliver_to_consumers(chunk)

        for cb in [cb1, cb2, cb3]:
            cb.assert_called_once()
            np.testing.assert_array_equal(cb.call_args[0][0], chunk)

    def test_no_consumers_no_error(self, recorder):
        """Test delivering with no consumers does not raise."""
        chunk = np.zeros((48000, 2), dtype=np.float32)
        recorder._deliver_to_consumers(chunk)  # should not raise


class TestConsumerErrorIsolation:
    """Test that a failing consumer does not break others."""

    def test_failing_consumer_does_not_block_others(self, recorder):
        """Test exception in one consumer doesn't prevent others from receiving."""
        failing_cb = Mock(side_effect=RuntimeError("boom"))
        healthy_cb = Mock()

        recorder.add_chunk_consumer(failing_cb)
        recorder.add_chunk_consumer(healthy_cb)

        chunk = np.zeros((48000, 2), dtype=np.float32)
        recorder._deliver_to_consumers(chunk)

        failing_cb.assert_called_once()
        healthy_cb.assert_called_once()


class TestConsumerThreadSafety:
    """Test thread safety of consumer registration during delivery."""

    def test_concurrent_add_remove_during_delivery(self, recorder):
        """Test adding/removing consumers while delivery is happening."""
        errors = []
        delivered = []

        def slow_consumer(chunk):
            """Consumer that takes a bit of time."""
            delivered.append(chunk)

        def add_remove_loop():
            """Rapidly add and remove a consumer."""
            try:
                cb = Mock()
                for _ in range(100):
                    recorder.add_chunk_consumer(cb)
                    recorder.remove_chunk_consumer(cb)
            except Exception as e:
                errors.append(e)

        recorder.add_chunk_consumer(slow_consumer)

        # Deliver chunks while another thread adds/removes consumers
        deliver_thread = threading.Thread(
            target=lambda: [
                recorder._deliver_to_consumers(np.zeros((100, 2), dtype=np.float32))
                for _ in range(50)
            ]
        )
        mutate_thread = threading.Thread(target=add_remove_loop)

        deliver_thread.start()
        mutate_thread.start()
        deliver_thread.join(timeout=5)
        mutate_thread.join(timeout=5)

        assert len(errors) == 0
        assert len(delivered) == 50


class TestDualModeIntegration:
    """Test bounded capture works alongside consumer fan-out."""

    def test_get_last_n_seconds_works_with_consumers_registered(self, recorder):
        """Test bounded capture returns correct audio even with consumers registered."""
        ws_callback = Mock()
        recorder.add_chunk_consumer(ws_callback)

        # Simulate recording by manually adding chunks to buffer
        for i in range(10):
            chunk = np.full((48000, 2), fill_value=i * 0.1, dtype=np.float32)
            with recorder.buffer_lock:
                recorder.audio_buffer.append(chunk)

        # Bounded capture should work independently
        result = recorder.get_last_n_seconds(5)
        assert result is not None
        assert len(result) == 5 * 48000  # 5 seconds of mono audio

    def test_buffer_fills_independently_of_consumers(self, recorder):
        """Test circular buffer fills regardless of consumer state."""
        # No consumers registered
        assert len(recorder._chunk_consumers) == 0

        # Simulate the capture loop behavior (buffer always fills)
        for i in range(5):
            chunk = np.zeros((48000, 2), dtype=np.float32)
            with recorder.buffer_lock:
                recorder.audio_buffer.append(chunk)

        assert recorder.get_buffer_seconds() == 5

        # Now register a consumer — buffer should still have data
        recorder.add_chunk_consumer(Mock())
        assert recorder.get_buffer_seconds() == 5
