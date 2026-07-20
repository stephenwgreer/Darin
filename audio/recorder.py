"""Dual-source audio capture with a rolling in-memory buffer.

DAR2-24: session-scoped dual-mode capture. Two WASAPI sources are resolved
FRESH on every ``start_recording()`` call:

- ``ME``   — the default microphone (channel column 0)
- ``THEM`` — the loopback of the default speaker (channel column 1)

Internal chunk format: int16, 16 000 Hz, 100 ms chunks (1600 frames),
numpy shape ``(1600, 2)``. If one source is unavailable its column is
zero-filled and ``sources_active`` reflects the degradation — capture never
crashes because a single device is missing.

If a device refuses 16 kHz the source is captured at 48 kHz and decimated
3:1 with a small windowed-sinc FIR (numpy only, no scipy).

Nothing in this module writes files: ``save_buffer()`` and
``get_last_n_seconds()`` return mono int16 numpy arrays mixed from both
columns.
"""

from __future__ import annotations

import queue
import threading
from collections import deque
from collections.abc import Callable

import numpy as np
from loguru import logger

import config


try:  # soundcard needs an audio backend (WASAPI on Windows, pulseaudio on Linux)
    import soundcard as sc
except Exception as _sc_import_error:  # pragma: no cover — hosts without audio
    sc = None  # type: ignore[assignment]
    _SOUNDCARD_IMPORT_ERROR: Exception | None = _sc_import_error
else:
    _SOUNDCARD_IMPORT_ERROR = None


# Source names → channel columns in the (frames, 2) chunk
SOURCE_ME = "me"  # default microphone → column 0
SOURCE_THEM = "them"  # loopback of default speaker → column 1

# Device failure handling
_OPEN_RETRIES = 3
_OPEN_RETRY_BACKOFF_S = 0.5

# Per-source queue depth between a capture thread and the pairing pump (~5 s)
_SOURCE_QUEUE_CHUNKS = 50

# How many chunks a lagging source may fall behind before the pump emits the
# paired chunk with zeros in the lagging column (~500 ms at 100 ms chunks).
_MAX_LAG_CHUNKS = 5

# FIR design for the 48 kHz → 16 kHz fallback decimation
_FIR_NUM_TAPS = 63


def _design_decimation_fir(num_taps: int = _FIR_NUM_TAPS, cutoff: float = 1.0 / 6.0) -> np.ndarray:
    """Design a windowed-sinc low-pass FIR for 3:1 decimation (numpy only).

    Args:
        num_taps: Filter length (odd for a symmetric linear-phase filter).
        cutoff: Normalized cutoff frequency (fraction of the input sample
            rate). 1/6 of 48 kHz = 8 kHz, the Nyquist limit of 16 kHz output.

    Returns:
        Float32 FIR coefficients normalized to unity DC gain.
    """
    n = np.arange(num_taps) - (num_taps - 1) / 2.0
    taps = 2.0 * cutoff * np.sinc(2.0 * cutoff * n)
    taps *= np.hamming(num_taps)
    taps /= taps.sum()
    return taps.astype(np.float32)


class ContinuousRecorder:
    """Session-scoped dual-source recorder with a rolling chunk buffer.

    Capture starts only when ``start_recording()`` is called (nothing records
    at construction time) and devices are re-resolved on every start so the
    current Windows defaults are always used.
    """

    def __init__(
        self,
        buffer_minutes: int = config.BUFFER_MINUTES,
        sample_rate: int = config.SAMPLE_RATE,
        chunk_seconds: float = config.CHUNK_SECONDS,
        on_chunk: Callable[[np.ndarray], None] | None = None,
        on_error: Callable[[str], None] | None = None,
    ) -> None:
        self.sample_rate: int = int(sample_rate)
        self.chunk_seconds: float = float(chunk_seconds)
        self.chunk_frames: int = int(round(self.chunk_seconds * self.sample_rate))
        self.buffer_minutes: int = buffer_minutes
        self.buffer_chunks: int = int(round(buffer_minutes * 60 / self.chunk_seconds))

        # Rolling buffer of int16 (chunk_frames, 2) chunks
        self.audio_buffer: deque[np.ndarray] = deque(maxlen=self.buffer_chunks)
        self.buffer_lock: threading.Lock = threading.Lock()

        # Recording control
        self._is_recording: bool = False
        self._recording_lock: threading.Lock = threading.Lock()
        self._stop_event: threading.Event = threading.Event()

        # Capture threads (created per session in start_recording)
        self._source_threads: dict[str, threading.Thread] = {}
        self._pump_thread: threading.Thread | None = None
        self._source_queues: dict[str, queue.Queue[tuple[int, np.ndarray]]] = {}
        self._pump_next_index: int = 0

        # Health / error state
        self.sources_active: dict[str, bool] = {SOURCE_ME: False, SOURCE_THEM: False}
        self.error: str | None = None
        self._on_error = on_error

        # Fan-out consumers for real-time chunk forwarding (e.g. WebSocket streaming)
        self._chunk_consumers: list[Callable[[np.ndarray], None]] = []
        self._consumers_lock: threading.Lock = threading.Lock()
        if on_chunk is not None:
            self._chunk_consumers.append(on_chunk)

    # ------------------------------------------------------------------
    # Recording state
    # ------------------------------------------------------------------

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

    # ------------------------------------------------------------------
    # Consumer fan-out
    # ------------------------------------------------------------------

    def add_chunk_consumer(self, callback: Callable[[np.ndarray], None]) -> None:
        """Register a consumer to receive int16 (chunk_frames, 2) chunks.

        Thread-safe. Duplicate registrations are silently ignored. Consumers
        are invoked from the capture pump thread.
        """
        with self._consumers_lock:
            if callback not in self._chunk_consumers:
                self._chunk_consumers.append(callback)
                logger.debug(f"Chunk consumer registered: {callback!r}")

    def remove_chunk_consumer(self, callback: Callable[[np.ndarray], None]) -> None:
        """Unregister a previously added consumer.

        Thread-safe. Removing a consumer that was never added is a no-op.
        """
        with self._consumers_lock:
            try:
                self._chunk_consumers.remove(callback)
                logger.debug(f"Chunk consumer removed: {callback!r}")
            except ValueError:
                pass  # Not registered — silently ignore

    def _deliver_to_consumers(self, chunk: np.ndarray) -> None:
        """Deliver an audio chunk to all registered consumers.

        Iterates over a snapshot of the consumer list so add/remove from
        other threads during delivery is safe. Each consumer is called
        inside its own try/except so a failing consumer cannot prevent
        others from receiving the chunk.
        """
        with self._consumers_lock:
            consumers = list(self._chunk_consumers)

        for consumer in consumers:
            try:
                consumer(chunk)
            except Exception:
                logger.exception(f"Chunk consumer {consumer!r} raised an exception")

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def start_recording(self) -> bool:
        """Start dual-source capture. Devices are resolved fresh on every call.

        Returns True if at least one source thread was started.
        """
        if self.is_recording:
            return False

        if sc is None:
            self.error = f"soundcard library unavailable: {_SOUNDCARD_IMPORT_ERROR}"
            logger.error("Cannot start recording", error=self.error)
            self._notify_error(self.error)
            return False

        self._stop_event.clear()
        self.error = None
        self._pump_next_index = 0
        self.sources_active = {SOURCE_ME: False, SOURCE_THEM: False}

        sources = self._resolve_sources()
        if all(source is None for source in sources.values()):
            self.error = "No audio sources available (mic and speaker loopback both failed)"
            logger.error("Cannot start recording", error=self.error)
            self._notify_error(self.error)
            return False

        self.is_recording = True
        self._source_queues = {
            name: queue.Queue(maxsize=_SOURCE_QUEUE_CHUNKS) for name in (SOURCE_ME, SOURCE_THEM)
        }
        self._source_threads = {}
        for name, source in sources.items():
            if source is None:
                continue
            thread = threading.Thread(
                target=self._source_loop,
                args=(name, source),
                daemon=True,
                name=f"capture-{name}",
            )
            self._source_threads[name] = thread
            thread.start()

        self._pump_thread = threading.Thread(
            target=self._pump_loop, daemon=True, name="capture-pump"
        )
        self._pump_thread.start()

        logger.info(
            "Recording started",
            sample_rate=self.sample_rate,
            chunk_frames=self.chunk_frames,
            sources=[name for name, s in sources.items() if s is not None],
        )
        return True

    def stop_recording(self) -> bool:
        """Stop capture and join all capture threads."""
        self.is_recording = False
        self._stop_event.set()

        for thread in self._source_threads.values():
            thread.join(timeout=2.0)
        if self._pump_thread is not None:
            self._pump_thread.join(timeout=2.0)

        self._source_threads = {}
        self._pump_thread = None
        self._source_queues = {}
        self.sources_active = {SOURCE_ME: False, SOURCE_THEM: False}
        logger.info("Recording stopped")
        return True

    def _resolve_sources(self) -> dict[str, object | None]:
        """Resolve the current default mic (ME) and speaker loopback (THEM).

        Called on every start_recording() so device changes between sessions
        are picked up. A missing source is logged and returned as None — its
        column will be zero-filled.
        """
        sources: dict[str, object | None] = {SOURCE_ME: None, SOURCE_THEM: None}
        try:
            sources[SOURCE_ME] = sc.default_microphone()
        except Exception as e:
            logger.warning(
                "Default microphone unavailable — ME column will be silent",
                error=str(e),
            )
        try:
            speaker = sc.default_speaker()
            sources[SOURCE_THEM] = sc.get_microphone(id=str(speaker.name), include_loopback=True)
        except Exception as e:
            logger.warning(
                "Speaker loopback unavailable — THEM column will be silent",
                error=str(e),
            )
        return sources

    # ------------------------------------------------------------------
    # Capture threads
    # ------------------------------------------------------------------

    def _source_loop(self, name: str, source: object) -> None:
        """Capture loop for a single source. Exception-guarded.

        Produces (chunk_index, mono int16 (chunk_frames,)) tuples on the
        source queue. On device failure the open is retried 3x with backoff;
        after that the source is marked inactive and — if no source remains —
        the recorder enters an error state.
        """
        fir = _design_decimation_fir()
        fir_state = np.zeros(len(fir) - 1, dtype=np.float32)
        chunk_index = 0
        failures = 0
        backoff = _OPEN_RETRY_BACKOFF_S

        while not self._stop_event.is_set():
            try:
                recorder_cm, native_rate = self._open_source(name, source)
                rec = recorder_cm.__enter__()
                native_frames = int(round(self.chunk_seconds * native_rate))
                decimate = native_rate != self.sample_rate
                self.sources_active[name] = True
                # Fast-forward past any chunks missed while re-opening so the
                # source stays time-aligned with the healthy one.
                chunk_index = max(chunk_index, self._pump_next_index)
                logger.info(
                    "Audio source opened",
                    source=name,
                    native_rate=native_rate,
                    decimate=decimate,
                )
                try:
                    while not self._stop_event.is_set():
                        data = rec.record(numframes=native_frames)
                        failures = 0
                        backoff = _OPEN_RETRY_BACKOFF_S
                        mono = self._to_mono_float(data)
                        if decimate:
                            mono, fir_state = self._decimate_3to1(mono, fir, fir_state)
                        chunk = self._float_to_int16(mono, self.chunk_frames)
                        self._enqueue_source_chunk(name, chunk_index, chunk)
                        chunk_index += 1
                finally:
                    recorder_cm.__exit__(None, None, None)
            except Exception as e:
                if self._stop_event.is_set():
                    break
                failures += 1
                self.sources_active[name] = False
                if failures > _OPEN_RETRIES:
                    message = (
                        f"Audio source '{name}' failed after {_OPEN_RETRIES} reopen attempts: {e}"
                    )
                    logger.error("Audio source giving up", source=name, error=str(e))
                    self._handle_source_death(message)
                    break
                logger.warning(
                    "Audio source error — retrying",
                    source=name,
                    attempt=failures,
                    backoff_s=backoff,
                    error=str(e),
                )
                self._stop_event.wait(backoff)
                backoff *= 2

        self.sources_active[name] = False

    def _open_source(self, name: str, source: object) -> tuple[object, int]:
        """Open a soundcard recorder at 16 kHz, falling back to 48 kHz.

        Returns (context_manager, native_rate). The context manager has NOT
        been entered yet. Raises if both rates fail.
        """
        try:
            return source.recorder(samplerate=self.sample_rate), self.sample_rate
        except Exception as e:
            logger.info(
                "Device refused target sample rate — falling back",
                source=name,
                target_rate=self.sample_rate,
                fallback_rate=config.FALLBACK_SAMPLE_RATE,
                error=str(e),
            )
            return (
                source.recorder(samplerate=config.FALLBACK_SAMPLE_RATE),
                config.FALLBACK_SAMPLE_RATE,
            )

    def _handle_source_death(self, message: str) -> None:
        """A source gave up permanently. If none remain, enter error state."""
        self._notify_error(message)
        if not any(self.sources_active.values()) and not self._stop_event.is_set():
            self.error = message
            self.is_recording = False  # reflect reality
            self._stop_event.set()
            logger.error("All audio sources failed — recording stopped", error=message)

    def _notify_error(self, message: str) -> None:
        if self._on_error is not None:
            try:
                self._on_error(message)
            except Exception:
                logger.exception("on_error callback raised")

    def _enqueue_source_chunk(self, name: str, index: int, chunk: np.ndarray) -> None:
        """Queue a chunk for the pump, dropping the OLDEST entry when full."""
        q = self._source_queues.get(name)
        if q is None:
            return
        try:
            q.put_nowait((index, chunk))
        except queue.Full:
            try:
                q.get_nowait()
            except queue.Empty:
                pass
            try:
                q.put_nowait((index, chunk))
            except queue.Full:
                pass

    # ------------------------------------------------------------------
    # Pairing pump
    # ------------------------------------------------------------------

    def _pump_loop(self) -> None:
        """Combine the two mono source streams into (chunk_frames, 2) chunks.

        Chunks are aligned by index. If one source lags more than
        ``_MAX_LAG_CHUNKS`` behind the healthy one (or is inactive), the
        missing column is zero-filled so the healthy source is never blocked.
        """
        pending: dict[str, dict[int, np.ndarray]] = {SOURCE_ME: {}, SOURCE_THEM: {}}
        latest: dict[str, int] = {SOURCE_ME: -1, SOURCE_THEM: -1}
        zeros = np.zeros(self.chunk_frames, dtype=np.int16)

        try:
            while not self._stop_event.is_set():
                drained = self._drain_source_queues(pending, latest)

                emitted = False
                while True:
                    i = self._pump_next_index
                    me = pending[SOURCE_ME].get(i)
                    them = pending[SOURCE_THEM].get(i)

                    if me is None and not self._source_gave_up_on(SOURCE_ME, i, latest):
                        break
                    if them is None and not self._source_gave_up_on(SOURCE_THEM, i, latest):
                        break
                    if me is None and them is None:
                        break

                    pending[SOURCE_ME].pop(i, None)
                    pending[SOURCE_THEM].pop(i, None)
                    paired = np.column_stack(
                        (me if me is not None else zeros, them if them is not None else zeros)
                    )
                    self._pump_next_index = i + 1
                    emitted = True

                    with self.buffer_lock:
                        self.audio_buffer.append(paired)
                    self._deliver_to_consumers(paired)

                if not emitted and not drained:
                    # Nothing to do — wait a beat without busy-spinning
                    self._stop_event.wait(self.chunk_seconds / 4)
        except Exception:
            logger.exception("Capture pump crashed")
            self.error = "Capture pump crashed"
            self.is_recording = False
            self._stop_event.set()
            self._notify_error(self.error)

    def _drain_source_queues(
        self,
        pending: dict[str, dict[int, np.ndarray]],
        latest: dict[str, int],
    ) -> bool:
        """Move all queued source chunks into the pending maps."""
        drained = False
        for name, q in self._source_queues.items():
            while True:
                try:
                    index, chunk = q.get_nowait()
                except queue.Empty:
                    break
                drained = True
                if index < self._pump_next_index:
                    continue  # stale chunk from before a device re-open
                pending[name][index] = chunk
                if index > latest[name]:
                    latest[name] = index
        return drained

    def _source_gave_up_on(self, name: str, index: int, latest: dict[str, int]) -> bool:
        """Whether the pump should stop waiting for `name` to produce `index`."""
        if not self.sources_active.get(name, False):
            return True
        other = SOURCE_THEM if name == SOURCE_ME else SOURCE_ME
        return latest[other] >= index + _MAX_LAG_CHUNKS

    # ------------------------------------------------------------------
    # Sample format helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _to_mono_float(data: np.ndarray) -> np.ndarray:
        """Average a float (frames, channels) capture block down to mono."""
        arr = np.asarray(data, dtype=np.float32)
        if arr.ndim == 2:
            return arr.mean(axis=1)
        return arr

    @staticmethod
    def _decimate_3to1(
        samples: np.ndarray, fir: np.ndarray, state: np.ndarray
    ) -> tuple[np.ndarray, np.ndarray]:
        """Low-pass filter and decimate 48 kHz mono samples 3:1 to 16 kHz.

        Carries (len(fir) - 1) samples of state across calls so chunk
        boundaries are filtered seamlessly.
        """
        buf = np.concatenate((state, samples))
        filtered = np.convolve(buf, fir, mode="valid")
        new_state = buf[-(len(fir) - 1) :]
        return filtered[::3], new_state

    @staticmethod
    def _float_to_int16(samples: np.ndarray, target_frames: int) -> np.ndarray:
        """Convert float [-1, 1] mono samples to int16, padded/trimmed to size."""
        pcm = (np.clip(samples, -1.0, 1.0) * 32767.0).astype(np.int16)
        if len(pcm) < target_frames:
            pcm = np.concatenate((pcm, np.zeros(target_frames - len(pcm), dtype=np.int16)))
        elif len(pcm) > target_frames:
            pcm = pcm[:target_frames]
        return pcm

    @staticmethod
    def _mix_to_mono(data: np.ndarray) -> np.ndarray:
        """Mix an int16 (frames, 2) array to mono int16 (int32 sum + clip)."""
        mixed = data[:, 0].astype(np.int32) + data[:, 1].astype(np.int32)
        return np.clip(mixed, -32768, 32767).astype(np.int16)

    # ------------------------------------------------------------------
    # Buffer access (no file writes — in-memory only)
    # ------------------------------------------------------------------

    def save_buffer(self) -> np.ndarray | None:
        """Return the whole rolling buffer as mono int16 (or None if empty).

        The deque is snapshotted under the lock; concatenation happens
        outside the lock so capture is never stalled by a large copy.
        """
        with self.buffer_lock:
            if not self.audio_buffer:
                logger.warning("No audio in buffer")
                return None
            chunks = list(self.audio_buffer)

        combined = np.concatenate(chunks, axis=0)
        return self._mix_to_mono(combined)

    def get_buffer_seconds(self) -> int:
        """Get the current buffer length in whole seconds."""
        with self.buffer_lock:
            return int(round(len(self.audio_buffer) * self.chunk_seconds))

    def get_last_n_seconds(self, seconds: float) -> np.ndarray | None:
        """Return the last N seconds of audio as mono int16 (or None if empty)."""
        with self.buffer_lock:
            if not self.audio_buffer:
                return None
            chunks_needed = max(1, int(round(seconds / self.chunk_seconds)))
            chunks = list(self.audio_buffer)[-chunks_needed:]

        combined = np.concatenate(chunks, axis=0)
        return self._mix_to_mono(combined)
