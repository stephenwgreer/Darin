# DAR2-24: Dual-Mode Audio Capture Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Replace `ContinuousRecorder`'s single-slot `_on_chunk` callback with a thread-safe consumer registration API, and update `AppController` to use it.

**Architecture:** The recorder's capture loop already feeds both a circular buffer and an `_on_chunk` callback. We formalize this by adding `add_chunk_consumer()` / `remove_chunk_consumer()` methods with a lock-protected consumer list and copy-on-iterate delivery. The circular buffer stays hardwired (not a registered consumer). `AppController` switches from mutating `recorder._on_chunk` to using the public API.

**Tech Stack:** Python 3.11+, pytest, threading, numpy, unittest.mock

---

## Important Context

- **Workspace root:** `/mnt/c/Users/stwgre/Github/Darin_AA/claude-redesign/`
- **Branch:** `feature/DAR2-24-dual-mode-audio` (based on `claude-redesign`)
- **Git wrapper:** Always use `./scripts/wsl-git.sh` from the engineering-manager directory, OR use plain `git` from within the claude-redesign directory since it's a worktree
- **Test runner:** `cd /mnt/c/Users/stwgre/Github/Darin_AA/claude-redesign && python -m pytest tests/ -v`
- **Existing test pattern:** Tests use `sys.path.insert(0, str(Path(__file__).parent.parent))` for imports, `patch("audio.recorder.sc.get_microphone")` to mock soundcard

---

### Task 1: Write failing tests for consumer registration API

**Files:**
- Create: `tests/test_recorder_consumers.py`

**Step 1: Write the test file**

```python
"""Tests for ContinuousRecorder consumer registration API (DAR2-24).

Tests the add_chunk_consumer / remove_chunk_consumer fan-out pattern
that replaces the single-slot _on_chunk callback.
"""

import sys
import threading
from pathlib import Path
from unittest.mock import Mock, patch

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

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
                recorder._deliver_to_consumers(
                    np.zeros((100, 2), dtype=np.float32)
                )
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
```

**Step 2: Run tests to verify they fail**

Run: `cd /mnt/c/Users/stwgre/Github/Darin_AA/claude-redesign && python -m pytest tests/test_recorder_consumers.py -v`
Expected: FAIL — `AttributeError: 'ContinuousRecorder' object has no attribute '_chunk_consumers'` (and similar for `add_chunk_consumer`, `_deliver_to_consumers`)

---

### Task 2: Implement consumer registration API in ContinuousRecorder

**Files:**
- Modify: `audio/recorder.py`

**Step 1: Add consumer list, lock, and registration methods to `__init__` and class body**

Replace the `_on_chunk` attribute in `__init__` with a consumer list. Add `add_chunk_consumer`, `remove_chunk_consumer`, and `_deliver_to_consumers` methods. Update `_record_loop` to use `_deliver_to_consumers`.

The full updated `audio/recorder.py` should be:

```python
import threading
from collections import deque
from collections.abc import Callable

import numpy as np
import soundcard as sc
import soundfile as sf
from loguru import logger


class ContinuousRecorder:
    def __init__(
        self,
        buffer_minutes: int = 3,
        sample_rate: int = 48000,
        chunk_seconds: int = 1,
        on_chunk: Callable[[np.ndarray], None] | None = None,
    ) -> None:
        self.sample_rate: int = sample_rate
        self.chunk_seconds: int = chunk_seconds
        self.chunk_frames: int = chunk_seconds * sample_rate
        self.buffer_minutes: int = buffer_minutes
        self.buffer_chunks: int = int(buffer_minutes * 60 // chunk_seconds)

        # Create a circular buffer to store audio (deque for O(1) operations)
        self.audio_buffer: deque = deque(maxlen=self.buffer_chunks)
        self.buffer_lock: threading.Lock = threading.Lock()

        # Recording control - using private variable with lock for thread safety
        self._is_recording: bool = False
        self._recording_lock: threading.Lock = threading.Lock()
        self.record_thread: threading.Thread | None = None

        # Consumer registration (DAR2-24): thread-safe list of chunk callbacks
        self._chunk_consumers: list[Callable[[np.ndarray], None]] = []
        self._consumers_lock: threading.Lock = threading.Lock()

        # Backward compat: if on_chunk provided, register as a consumer
        if on_chunk is not None:
            self._chunk_consumers.append(on_chunk)

        # Setup microphone
        self.mic = sc.get_microphone(id=str(sc.default_speaker().name), include_loopback=True)

    @property
    def is_recording(self) -> bool:
        """Thread-safe property for recording state"""
        with self._recording_lock:
            return self._is_recording

    @is_recording.setter
    def is_recording(self, value: bool) -> None:
        """Thread-safe setter for recording state"""
        with self._recording_lock:
            self._is_recording = value

    def add_chunk_consumer(self, callback: Callable[[np.ndarray], None]) -> None:
        """Register a consumer to receive audio chunks. Thread-safe.

        Duplicate registration is a no-op (logs a warning).
        """
        with self._consumers_lock:
            if callback in self._chunk_consumers:
                logger.warning("Consumer already registered, ignoring duplicate")
                return
            self._chunk_consumers.append(callback)
            logger.info("Chunk consumer registered", consumer_count=len(self._chunk_consumers))

    def remove_chunk_consumer(self, callback: Callable[[np.ndarray], None]) -> None:
        """Unregister a consumer. Thread-safe.

        Removing a non-registered consumer is a no-op.
        """
        with self._consumers_lock:
            try:
                self._chunk_consumers.remove(callback)
                logger.info("Chunk consumer removed", consumer_count=len(self._chunk_consumers))
            except ValueError:
                pass  # Not registered — no-op

    def _deliver_to_consumers(self, chunk: np.ndarray) -> None:
        """Deliver an audio chunk to all registered consumers.

        Uses copy-on-iterate to avoid holding the lock during callback execution.
        Exceptions in individual consumers are caught and logged.
        """
        with self._consumers_lock:
            consumers_snapshot = list(self._chunk_consumers)

        for consumer in consumers_snapshot:
            try:
                consumer(chunk)
            except Exception:
                logger.warning("Chunk consumer raised an exception", exc_info=True)

    def start_recording(self) -> bool:
        """Start the recording process in a separate thread"""
        if self.is_recording:
            return False

        self.is_recording = True
        self.record_thread = threading.Thread(target=self._record_loop)
        self.record_thread.daemon = True
        self.record_thread.start()
        return True

    def stop_recording(self) -> bool:
        """Stop the recording process"""
        self.is_recording = False
        if self.record_thread:
            self.record_thread.join(timeout=2.0)
        return True

    def _record_loop(self) -> None:
        """Main recording loop that continuously captures audio in chunks"""
        with self.mic.recorder(samplerate=self.sample_rate) as recorder:
            while True:
                # Check recording state with lock
                with self._recording_lock:
                    if not self._is_recording:
                        break

                # Record a chunk of audio
                data = recorder.record(numframes=self.chunk_frames)

                # Add to the circular buffer (always active, not a consumer)
                with self.buffer_lock:
                    # deque with maxlen automatically drops oldest when full
                    self.audio_buffer.append(data)

                # Deliver to all registered consumers (outside buffer lock)
                self._deliver_to_consumers(data)

    def save_buffer(self, filename: str | None = None) -> np.ndarray | None:
        """Save the current audio buffer to a file and return mono data"""

        with self.buffer_lock:
            if not self.audio_buffer:
                logger.warning("No audio to save!")
                return None

            # Combine all chunks in the buffer
            combined_data = np.concatenate(self.audio_buffer, axis=0)

            # Get mono audio (first channel)
            mono_data = combined_data[:, 0]

            # Save to file
            output_file = filename or "BSGPT_REC.wav"
            sf.write(file=output_file, data=mono_data, samplerate=self.sample_rate)
            logger.info(f"Audio saved to {output_file}")

            return mono_data

    def get_buffer_seconds(self) -> int:
        """Get the current buffer length in seconds"""
        with self.buffer_lock:
            return len(self.audio_buffer) * self.chunk_seconds

    def get_last_n_seconds(self, seconds: float) -> np.ndarray | None:
        """Get the last N seconds of audio from the buffer"""
        with self.buffer_lock:
            if not self.audio_buffer:
                return None

            # Calculate how many chunks we need
            chunks_needed = int(seconds // self.chunk_seconds)
            if chunks_needed == 0:
                chunks_needed = 1  # At least get one chunk

            # Get the last N chunks (convert deque to list for slicing)
            buffer_list = list(self.audio_buffer)
            chunks = buffer_list[-chunks_needed:]

            # Combine chunks into one array
            if len(chunks) > 1:
                combined_data = np.concatenate(chunks, axis=0)
            else:
                combined_data = chunks[0]

            # Get mono audio (first channel)
            mono_data = combined_data[:, 0]

            return mono_data
```

**Step 2: Run the new tests to verify they pass**

Run: `cd /mnt/c/Users/stwgre/Github/Darin_AA/claude-redesign && python -m pytest tests/test_recorder_consumers.py -v`
Expected: All PASS

**Step 3: Run the existing recorder tests to verify no regressions**

Run: `cd /mnt/c/Users/stwgre/Github/Darin_AA/claude-redesign && python -m pytest tests/test_recorder_config.py -v`
Expected: All PASS

**Step 4: Commit**

```bash
git add audio/recorder.py tests/test_recorder_consumers.py
git commit -m "feat(DAR2-24): add consumer registration API to ContinuousRecorder

Replace single-slot _on_chunk callback with thread-safe consumer list.
add_chunk_consumer/remove_chunk_consumer with copy-on-iterate delivery
and per-consumer error isolation.

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>"
```

---

### Task 3: Update AppController to use consumer registration API

**Files:**
- Modify: `app_controller.py` (lines 186, 209)

**Step 1: Update `start_streaming()` — replace line 186**

Change:
```python
self.recorder._on_chunk = self._on_recorder_chunk
```
To:
```python
self.recorder.add_chunk_consumer(self._on_recorder_chunk)
```

**Step 2: Update `stop_streaming()` — replace line 209**

Change:
```python
self.recorder._on_chunk = None
```
To:
```python
self.recorder.remove_chunk_consumer(self._on_recorder_chunk)
```

**Step 3: Run all tests**

Run: `cd /mnt/c/Users/stwgre/Github/Darin_AA/claude-redesign && python -m pytest tests/test_recorder_consumers.py tests/test_recorder_config.py tests/test_deepgram_streaming.py -v`
Expected: All PASS

**Step 4: Commit**

```bash
git add app_controller.py
git commit -m "refactor(DAR2-24): AppController uses consumer registration API

Replace direct mutation of recorder._on_chunk with
add_chunk_consumer/remove_chunk_consumer calls.

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>"
```

---

### Task 4: Final verification — run full test suite

**Step 1: Run all project tests**

Run: `cd /mnt/c/Users/stwgre/Github/Darin_AA/claude-redesign && python -m pytest tests/ -v --tb=short`
Expected: All PASS (some thread safety tests may be skipped if PyQt6 not available in CI — that's OK)

**Step 2: Verify no remaining `_on_chunk` references in app_controller.py**

Run: `grep -n "_on_chunk" /mnt/c/Users/stwgre/Github/Darin_AA/claude-redesign/app_controller.py`
Expected: No output (zero references to `_on_chunk`)

**Step 3: Verify consumer API exists on recorder**

Run: `grep -n "def add_chunk_consumer\|def remove_chunk_consumer\|def _deliver_to_consumers" /mnt/c/Users/stwgre/Github/Darin_AA/claude-redesign/audio/recorder.py`
Expected: Three method definitions found
