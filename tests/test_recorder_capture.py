"""Tests for the DAR2-24 dual-source capture pipeline in ContinuousRecorder.

All soundcard access is faked — no audio hardware is required. Verifies:
- dual-source pairing into (1600, 2) int16 chunks (ME=col 0, THEM=col 1)
- fresh device resolution on every start_recording()
- zero-fill + sources_active flag when one source is unavailable
- 48 kHz fallback with 3:1 windowed-sinc FIR decimation
- exception-guarded capture loops (retry, then error state)
"""

from __future__ import annotations

import time
from types import SimpleNamespace
from unittest.mock import MagicMock

import numpy as np
import pytest

import audio.recorder as recorder_module
from audio.recorder import ContinuousRecorder, _design_decimation_fir


# ---------------------------------------------------------------------------
# Fakes
# ---------------------------------------------------------------------------


class FakeRecorderCM:
    """Fake soundcard recorder context manager producing constant samples."""

    def __init__(self, source: FakeSource) -> None:
        self.source = source

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def record(self, numframes: int) -> np.ndarray:
        # fail_after counts records across ALL opens of the source, so a dead
        # device keeps failing after every re-open (retry exhaustion path).
        self.source.total_records += 1
        if (
            self.source.fail_after is not None
            and self.source.total_records > self.source.fail_after
        ):
            raise RuntimeError("device disappeared")
        time.sleep(0.005)  # pace the producer a little
        return np.full((numframes, 2), self.source.value, dtype=np.float32)


class FakeSource:
    """Fake soundcard microphone/loopback source."""

    def __init__(
        self,
        value: float,
        *,
        refuse_16k: bool = False,
        refuse_all: bool = False,
        fail_after: int | None = None,
    ) -> None:
        self.value = value
        self.refuse_16k = refuse_16k
        self.refuse_all = refuse_all
        self.fail_after = fail_after
        self.total_records = 0

    def recorder(self, samplerate: int) -> FakeRecorderCM:
        if self.refuse_all:
            raise RuntimeError("device gone")
        if self.refuse_16k and samplerate == 16000:
            raise RuntimeError("unsupported sample rate")
        return FakeRecorderCM(self)


def _fake_sc(
    mic: FakeSource | None,
    loopback: FakeSource | None,
) -> SimpleNamespace:
    """Build a fake `soundcard` module for audio.recorder.sc."""

    def default_microphone():
        if mic is None:
            raise RuntimeError("no default microphone")
        return mic

    def default_speaker():
        return SimpleNamespace(name="Fake Speakers")

    def get_microphone(id, include_loopback=False):  # noqa: A002, ARG001
        if loopback is None:
            raise RuntimeError("no loopback device")
        return loopback

    return SimpleNamespace(
        default_microphone=MagicMock(side_effect=default_microphone),
        default_speaker=MagicMock(side_effect=default_speaker),
        get_microphone=MagicMock(side_effect=get_microphone),
    )


def _wait_for(condition, timeout: float = 5.0) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if condition():
            return True
        time.sleep(0.02)
    return False


def _buffer_len(rec: ContinuousRecorder) -> int:
    with rec.buffer_lock:
        return len(rec.audio_buffer)


@pytest.fixture
def recorder() -> ContinuousRecorder:
    rec = ContinuousRecorder(buffer_minutes=1)
    yield rec
    rec.stop_recording()


# ---------------------------------------------------------------------------
# Dual capture
# ---------------------------------------------------------------------------


class TestDualCapture:
    def test_pairs_mic_and_loopback_into_two_columns(self, recorder, monkeypatch):
        monkeypatch.setattr(recorder_module, "sc", _fake_sc(FakeSource(0.5), FakeSource(-0.25)))

        assert recorder.start_recording() is True
        assert _wait_for(lambda: _buffer_len(recorder) >= 5)
        recorder.stop_recording()

        with recorder.buffer_lock:
            chunk = recorder.audio_buffer[-1]
        assert chunk.shape == (1600, 2)
        assert chunk.dtype == np.int16
        # column 0 = ME (mic value 0.5), column 1 = THEM (loopback value -0.25)
        assert abs(int(chunk[0, 0]) - 16383) <= 1
        assert abs(int(chunk[0, 1]) - (-8192)) <= 1

    def test_sources_active_flags_set_while_recording(self, recorder, monkeypatch):
        monkeypatch.setattr(recorder_module, "sc", _fake_sc(FakeSource(0.1), FakeSource(0.1)))
        recorder.start_recording()
        assert _wait_for(lambda: recorder.sources_active["me"] and recorder.sources_active["them"])
        recorder.stop_recording()
        assert recorder.sources_active == {"me": False, "them": False}

    def test_devices_resolved_fresh_on_every_start(self, recorder, monkeypatch):
        fake = _fake_sc(FakeSource(0.1), FakeSource(0.1))
        monkeypatch.setattr(recorder_module, "sc", fake)

        recorder.start_recording()
        recorder.stop_recording()
        recorder.start_recording()
        recorder.stop_recording()

        assert fake.default_microphone.call_count == 2
        assert fake.default_speaker.call_count == 2

    def test_start_when_already_recording_returns_false(self, recorder, monkeypatch):
        monkeypatch.setattr(recorder_module, "sc", _fake_sc(FakeSource(0.1), FakeSource(0.1)))
        assert recorder.start_recording() is True
        assert recorder.start_recording() is False
        recorder.stop_recording()

    def test_stop_recording_clears_threads_and_state(self, recorder, monkeypatch):
        monkeypatch.setattr(recorder_module, "sc", _fake_sc(FakeSource(0.1), FakeSource(0.1)))
        recorder.start_recording()
        assert _wait_for(lambda: _buffer_len(recorder) >= 1)
        recorder.stop_recording()

        assert not recorder.is_recording
        assert recorder._source_threads == {}
        assert recorder._pump_thread is None


# ---------------------------------------------------------------------------
# Degraded / missing sources
# ---------------------------------------------------------------------------


class TestSourceDegradation:
    def test_missing_mic_zero_fills_me_column(self, recorder, monkeypatch):
        monkeypatch.setattr(recorder_module, "sc", _fake_sc(None, FakeSource(0.5)))

        assert recorder.start_recording() is True
        assert _wait_for(lambda: _buffer_len(recorder) >= 3)
        recorder.stop_recording()

        assert recorder.error is None
        with recorder.buffer_lock:
            chunk = recorder.audio_buffer[-1]
        assert np.all(chunk[:, 0] == 0)  # ME column zero-filled
        assert np.all(chunk[:, 1] != 0)  # THEM column has audio

    def test_missing_loopback_zero_fills_them_column(self, recorder, monkeypatch):
        monkeypatch.setattr(recorder_module, "sc", _fake_sc(FakeSource(0.5), None))

        assert recorder.start_recording() is True
        assert _wait_for(lambda: _buffer_len(recorder) >= 3)
        recorder.stop_recording()

        with recorder.buffer_lock:
            chunk = recorder.audio_buffer[-1]
        assert np.all(chunk[:, 0] != 0)
        assert np.all(chunk[:, 1] == 0)

    def test_no_sources_at_all_fails_cleanly(self, monkeypatch):
        errors: list[str] = []
        rec = ContinuousRecorder(buffer_minutes=1, on_error=errors.append)
        monkeypatch.setattr(recorder_module, "sc", _fake_sc(None, None))

        assert rec.start_recording() is False
        assert not rec.is_recording
        assert rec.error is not None
        assert len(errors) == 1

    def test_device_failure_retries_then_error_state(self, monkeypatch):
        """A dying single source exhausts retries → error state, honest flags."""
        errors: list[str] = []
        rec = ContinuousRecorder(buffer_minutes=1, on_error=errors.append)
        monkeypatch.setattr(recorder_module, "_OPEN_RETRY_BACKOFF_S", 0.01)
        # Only the mic exists, and its device dies after two chunks and
        # refuses to re-open.
        dying = FakeSource(0.5, fail_after=2)
        monkeypatch.setattr(recorder_module, "sc", _fake_sc(dying, None))

        assert rec.start_recording() is True
        assert _wait_for(lambda: _buffer_len(rec) >= 1)
        # Once it dies, record() keeps failing across re-opens → retries exhaust.
        assert _wait_for(lambda: rec.error is not None, timeout=10.0)
        assert not rec.is_recording  # is_recording reflects reality
        assert errors  # on_error callback invoked
        rec.stop_recording()


# ---------------------------------------------------------------------------
# 48 kHz fallback + FIR decimation
# ---------------------------------------------------------------------------


class TestDecimation:
    def test_device_refusing_16k_falls_back_to_48k_decimated(self, recorder, monkeypatch):
        monkeypatch.setattr(
            recorder_module,
            "sc",
            _fake_sc(FakeSource(0.5, refuse_16k=True), FakeSource(0.25)),
        )

        assert recorder.start_recording() is True
        assert _wait_for(lambda: _buffer_len(recorder) >= 5)
        recorder.stop_recording()

        with recorder.buffer_lock:
            chunk = recorder.audio_buffer[-1]  # past the FIR warm-up transient
        assert chunk.shape == (1600, 2)
        # DC value survives decimation with unity gain
        assert abs(int(chunk[800, 0]) - 16383) <= 30

    def test_decimate_3to1_length_and_dc_gain(self):
        fir = _design_decimation_fir()
        state = np.zeros(len(fir) - 1, dtype=np.float32)
        samples = np.full(4800, 0.5, dtype=np.float32)

        out, state = ContinuousRecorder._decimate_3to1(samples, fir, state)
        assert len(out) == 1600
        # Second chunk is past the transient: pure DC at unity gain
        out2, _ = ContinuousRecorder._decimate_3to1(samples, fir, state)
        assert np.allclose(out2, 0.5, atol=1e-3)

    def test_decimate_attenuates_above_nyquist(self):
        """Content above 8 kHz must be filtered out before 3:1 downsampling."""
        fir = _design_decimation_fir()
        state = np.zeros(len(fir) - 1, dtype=np.float32)
        t = np.arange(9600) / 48000.0
        tone = np.sin(2 * np.pi * 15000 * t).astype(np.float32)  # 15 kHz

        out, _ = ContinuousRecorder._decimate_3to1(tone, fir, state)
        rms = float(np.sqrt(np.mean(out[200:] ** 2)))
        assert rms < 0.05  # >20 dB attenuation of aliasing content

    def test_decimate_preserves_passband_tone(self):
        """A 1 kHz tone (well inside the passband) survives decimation."""
        fir = _design_decimation_fir()
        state = np.zeros(len(fir) - 1, dtype=np.float32)
        t = np.arange(9600) / 48000.0
        tone = np.sin(2 * np.pi * 1000 * t).astype(np.float32)

        out, _ = ContinuousRecorder._decimate_3to1(tone, fir, state)
        rms = float(np.sqrt(np.mean(out[200:] ** 2)))
        assert abs(rms - 1 / np.sqrt(2)) < 0.02  # sine RMS preserved
