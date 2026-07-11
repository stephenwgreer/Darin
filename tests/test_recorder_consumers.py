"""Tests for ContinuousRecorder consumer registration API (DAR2-24).

Tests the add_chunk_consumer / remove_chunk_consumer fan-out pattern and the
in-memory rolling buffer (mono int16 mixing, no file writes).

Chunk format under test: int16, shape (1600, 2) — 100 ms at 16 kHz,
column 0 = ME (mic), column 1 = THEM (speaker loopback).
"""

import inspect
import threading
from unittest.mock import Mock

import numpy as np
import pytest

import config
from audio.recorder import ContinuousRecorder


def _chunk(me: int = 0, them: int = 0) -> np.ndarray:
    """Build an int16 (1600, 2) chunk with constant per-column values."""
    chunk = np.empty((1600, 2), dtype=np.int16)
    chunk[:, 0] = me
    chunk[:, 1] = them
    return chunk


@pytest.fixture
def recorder() -> ContinuousRecorder:
    """Create a ContinuousRecorder (no devices touched at construction)."""
    return ContinuousRecorder(buffer_minutes=1)


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
        rec = ContinuousRecorder(buffer_minutes=1, on_chunk=callback)
        assert callback in rec._chunk_consumers


class TestChunkFanout:
    """Test that chunks are delivered to all registered consumers."""

    def test_single_consumer_receives_chunks(self, recorder):
        """Test a single consumer receives audio chunks."""
        callback = Mock()
        recorder.add_chunk_consumer(callback)

        chunk = _chunk(me=100, them=-100)
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

        chunk = _chunk(me=500)
        recorder._deliver_to_consumers(chunk)

        for cb in [cb1, cb2, cb3]:
            cb.assert_called_once()
            np.testing.assert_array_equal(cb.call_args[0][0], chunk)

    def test_no_consumers_no_error(self, recorder):
        """Test delivering with no consumers does not raise."""
        recorder._deliver_to_consumers(_chunk())  # should not raise


class TestConsumerErrorIsolation:
    """Test that a failing consumer does not break others."""

    def test_failing_consumer_does_not_block_others(self, recorder):
        """Test exception in one consumer doesn't prevent others from receiving."""
        failing_cb = Mock(side_effect=RuntimeError("boom"))
        healthy_cb = Mock()

        recorder.add_chunk_consumer(failing_cb)
        recorder.add_chunk_consumer(healthy_cb)

        recorder._deliver_to_consumers(_chunk())

        failing_cb.assert_called_once()
        healthy_cb.assert_called_once()


class TestConsumerThreadSafety:
    """Test thread safety of consumer registration during delivery."""

    def test_concurrent_add_remove_during_delivery(self, recorder):
        """Test adding/removing consumers while delivery is happening."""
        errors = []
        delivered = []

        def slow_consumer(chunk):
            delivered.append(chunk)

        def add_remove_loop():
            try:
                cb = Mock()
                for _ in range(100):
                    recorder.add_chunk_consumer(cb)
                    recorder.remove_chunk_consumer(cb)
            except Exception as e:
                errors.append(e)

        recorder.add_chunk_consumer(slow_consumer)

        deliver_thread = threading.Thread(
            target=lambda: [recorder._deliver_to_consumers(_chunk()) for _ in range(50)]
        )
        mutate_thread = threading.Thread(target=add_remove_loop)

        deliver_thread.start()
        mutate_thread.start()
        deliver_thread.join(timeout=5)
        mutate_thread.join(timeout=5)

        assert len(errors) == 0
        assert len(delivered) == 50


class TestBufferAccess:
    """Test the rolling buffer: mono int16 mixing, snapshot semantics."""

    def _fill_buffer(self, recorder, chunks):
        for c in chunks:
            with recorder.buffer_lock:
                recorder.audio_buffer.append(c)

    def test_get_last_n_seconds_returns_mono_int16(self, recorder):
        """Bounded capture returns mixed mono int16 of the right length."""
        recorder.add_chunk_consumer(Mock())
        # 100 chunks of 100 ms = 10 s of audio
        self._fill_buffer(recorder, [_chunk(me=1000, them=200) for _ in range(100)])

        result = recorder.get_last_n_seconds(5)
        assert result is not None
        assert result.dtype == np.int16
        assert result.ndim == 1
        assert len(result) == 5 * config.SAMPLE_RATE  # 5 s of mono @ 16 kHz
        # Mixed = me + them
        assert np.all(result == 1200)

    def test_get_last_n_seconds_empty_buffer_returns_none(self, recorder):
        assert recorder.get_last_n_seconds(5) is None

    def test_save_buffer_returns_full_mono_mix(self, recorder):
        self._fill_buffer(recorder, [_chunk(me=100, them=-40) for _ in range(30)])

        result = recorder.save_buffer()
        assert result is not None
        assert result.dtype == np.int16
        assert len(result) == 30 * 1600
        assert np.all(result == 60)

    def test_save_buffer_empty_returns_none(self, recorder):
        assert recorder.save_buffer() is None

    def test_save_buffer_takes_no_filename_and_writes_no_files(self, recorder):
        """DAR2-24: no WAV side effects — save_buffer is in-memory only."""
        assert list(inspect.signature(recorder.save_buffer).parameters) == []

    def test_mono_mix_clips_at_int16_range(self, recorder):
        """Mixing loud columns must clip via int32 intermediate, not wrap."""
        self._fill_buffer(recorder, [_chunk(me=30000, them=30000)])
        result = recorder.save_buffer()
        assert np.all(result == 32767)  # clipped, not wrapped negative

    def test_get_buffer_seconds(self, recorder):
        self._fill_buffer(recorder, [_chunk() for _ in range(50)])
        assert recorder.get_buffer_seconds() == 5

    def test_buffer_fills_independently_of_consumers(self, recorder):
        """Test rolling buffer fills regardless of consumer state."""
        assert len(recorder._chunk_consumers) == 0
        self._fill_buffer(recorder, [_chunk() for _ in range(10)])
        assert recorder.get_buffer_seconds() == 1
        recorder.add_chunk_consumer(Mock())
        assert recorder.get_buffer_seconds() == 1
