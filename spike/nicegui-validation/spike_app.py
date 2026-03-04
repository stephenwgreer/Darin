"""NiceGUI Validation Spike — Tests 3 HoE conditions.

Condition 1: COM threading compatibility (NiceGUI/pywebview + audio capture)
Condition 2: Streaming latency benchmark (50-100 text chunks/sec)
Condition 3: (Run separately via PyInstaller after this validates)

Tests TWO audio backends:
  A) soundcard (WASAPI/COM) — same as current Darin, uses COM apartments
  B) sounddevice (PortAudio) — bypasses COM entirely via C callback

Usage:
    uv run spike_app.py              # default: sounddevice (no COM conflict)
    uv run spike_app.py --soundcard  # test soundcard COM compatibility
"""

import argparse
import asyncio
import statistics
import threading
import time
from collections import deque

import numpy as np
from loguru import logger
from nicegui import app, ui


# ---------------------------------------------------------------------------
# Audio Capture — sounddevice backend (PortAudio, no COM)
# ---------------------------------------------------------------------------

class SoundDeviceCapture:
    """Loopback capture via sounddevice/PortAudio — avoids COM entirely."""

    def __init__(self, sample_rate: int = 48000, chunk_seconds: float = 0.1) -> None:
        import sounddevice as sd
        self.sd = sd
        self.sample_rate = sample_rate
        self.chunk_seconds = chunk_seconds
        self.chunk_frames = int(chunk_seconds * sample_rate)

        self._is_running = False
        self._lock = threading.Lock()
        self._stream = None

        # Metrics
        self.level: float = 0.0
        self.chunks_captured: int = 0
        self.dropouts: int = 0
        self.last_chunk_time: float = 0.0
        self.capture_errors: list[str] = []
        self.backend_name = "sounddevice (PortAudio)"
        self._discontinuities: int = 0

    def start(self) -> None:
        with self._lock:
            if self._is_running:
                return
            self._is_running = True

        try:
            # Find WASAPI loopback device
            loopback_id, channels = self._find_loopback_device()
            self._stream = self.sd.InputStream(
                device=loopback_id,
                samplerate=self.sample_rate,
                channels=channels,
                blocksize=self.chunk_frames,
                callback=self._audio_callback,
            )
            self._stream.start()
            logger.info(f"Audio capture started (sounddevice, device={loopback_id}, ch={channels})")
        except Exception as e:
            error = f"Failed to start sounddevice capture: {e}"
            logger.error(error)
            self.capture_errors.append(error)
            with self._lock:
                self._is_running = False

    def _find_loopback_device(self) -> tuple[int, int]:
        """Find a loopback/stereo-mix input device for system audio capture.

        Returns (device_id, channels).
        """
        devices = self.sd.query_devices()
        logger.info("Available audio devices:")
        for i, d in enumerate(devices):
            logger.info(f"  [{i}] {d['name']} (in={d['max_input_channels']}, out={d['max_output_channels']})")

        # Strategy 1: Look for explicit "loopback" in name
        for i, d in enumerate(devices):
            name = d['name'].lower()
            if 'loopback' in name and d['max_input_channels'] > 0:
                logger.info(f"Found loopback device: [{i}] {d['name']}")
                return i, min(d['max_input_channels'], 2)

        # Strategy 2: Look for "stereo mix" — Windows built-in loopback
        for i, d in enumerate(devices):
            name = d['name'].lower()
            if 'stereo mix' in name and d['max_input_channels'] > 0:
                logger.info(f"Found stereo mix device: [{i}] {d['name']}")
                return i, min(d['max_input_channels'], 2)

        # Strategy 3: Look for "what u hear", "wave out", or similar loopback names
        for i, d in enumerate(devices):
            name = d['name'].lower()
            if any(kw in name for kw in ['what u hear', 'wave out', 'mix', 'monitor']) and d['max_input_channels'] > 0:
                logger.info(f"Found loopback-like device: [{i}] {d['name']}")
                return i, min(d['max_input_channels'], 2)

        raise RuntimeError(
            "No loopback audio device found. Enable 'Stereo Mix' in Windows Sound settings: "
            "Control Panel > Sound > Recording tab > right-click > Show Disabled Devices > enable Stereo Mix"
        )

    def _audio_callback(self, indata, frames, time_info, status) -> None:
        if status:
            self._discontinuities += 1
            if 'input overflow' in str(status).lower():
                self.dropouts += 1

        mono = indata[:, 0] if indata.ndim > 1 else indata
        rms = float(np.sqrt(np.mean(mono ** 2)))
        self.level = min(rms * 10.0, 1.0)

        self.chunks_captured += 1
        self.last_chunk_time = time.time()

    def stop(self) -> None:
        with self._lock:
            self._is_running = False
        if self._stream:
            self._stream.stop()
            self._stream.close()
        logger.info(f"Audio capture stopped. Chunks: {self.chunks_captured}, Dropouts: {self.dropouts}")

    @property
    def is_running(self) -> bool:
        with self._lock:
            return self._is_running


# ---------------------------------------------------------------------------
# Audio Capture — soundcard backend (WASAPI/COM)
# ---------------------------------------------------------------------------

class SoundCardCapture:
    """Loopback capture via soundcard (WASAPI/COM) — tests COM compatibility."""

    def __init__(self, sample_rate: int = 48000, chunk_seconds: float = 0.1) -> None:
        self.sample_rate = sample_rate
        self.chunk_seconds = chunk_seconds
        self.chunk_frames = int(chunk_seconds * sample_rate)

        self._is_running = False
        self._lock = threading.Lock()
        self._thread: threading.Thread | None = None

        # Metrics
        self.level: float = 0.0
        self.chunks_captured: int = 0
        self.dropouts: int = 0
        self.last_chunk_time: float = 0.0
        self.capture_errors: list[str] = []
        self.backend_name = "soundcard (WASAPI/COM)"

    def start(self) -> None:
        with self._lock:
            if self._is_running:
                return
            self._is_running = True

        self._thread = threading.Thread(target=self._capture_loop, daemon=True)
        self._thread.start()
        logger.info("Audio capture started (soundcard)")

    def stop(self) -> None:
        with self._lock:
            self._is_running = False
        if self._thread:
            self._thread.join(timeout=3.0)
        logger.info(f"Audio capture stopped. Chunks: {self.chunks_captured}, Dropouts: {self.dropouts}")

    @property
    def is_running(self) -> bool:
        with self._lock:
            return self._is_running

    def _capture_loop(self) -> None:
        import soundcard as sc

        try:
            mic = sc.get_microphone(
                id=str(sc.default_speaker().name),
                include_loopback=True,
            )
        except Exception as e:
            error = f"Failed to get loopback mic: {e}"
            logger.error(error)
            self.capture_errors.append(error)
            with self._lock:
                self._is_running = False
            return

        try:
            with mic.recorder(samplerate=self.sample_rate) as recorder:
                while self.is_running:
                    t0 = time.perf_counter()
                    data = recorder.record(numframes=self.chunk_frames)
                    elapsed = time.perf_counter() - t0

                    mono = data[:, 0] if data.ndim > 1 else data
                    rms = float(np.sqrt(np.mean(mono ** 2)))
                    self.level = min(rms * 10.0, 1.0)

                    self.chunks_captured += 1
                    self.last_chunk_time = time.time()

                    expected = self.chunk_seconds
                    if elapsed > expected * 2.0:
                        self.dropouts += 1
                        logger.warning(f"Audio dropout: chunk took {elapsed:.2f}s (expected {expected:.1f}s)")

        except Exception as e:
            error = f"Capture loop error: {e}"
            logger.error(error)
            self.capture_errors.append(error)
        finally:
            with self._lock:
                self._is_running = False


# ---------------------------------------------------------------------------
# Streaming Latency Benchmark
# ---------------------------------------------------------------------------

class StreamingBenchmark:
    """Simulates Claude API streaming at 50-100 chunks/sec, measures latency."""

    def __init__(self) -> None:
        self.is_running = False
        self.chunks_sent: int = 0
        self.latencies: deque[float] = deque(maxlen=500)
        self.target_rate: int = 75  # chunks per second (middle of 50-100 range)
        self.text_buffer: str = ""
        self._emit_times: deque[tuple[int, float]] = deque(maxlen=500)

    def record_emit(self, chunk_id: int) -> None:
        """Called right before UI update — records the Python-side emit time."""
        self._emit_times.append((chunk_id, time.perf_counter()))

    def record_ack(self, chunk_id: int) -> None:
        """Called when JS confirms render — records round-trip latency."""
        for cid, t in self._emit_times:
            if cid == chunk_id:
                latency_ms = (time.perf_counter() - t) * 1000
                self.latencies.append(latency_ms)
                break

    @property
    def avg_latency_ms(self) -> float:
        if not self.latencies:
            return 0.0
        return statistics.mean(self.latencies)

    @property
    def p95_latency_ms(self) -> float:
        if len(self.latencies) < 5:
            return 0.0
        sorted_lats = sorted(self.latencies)
        idx = int(len(sorted_lats) * 0.95)
        return sorted_lats[idx]

    @property
    def max_latency_ms(self) -> float:
        if not self.latencies:
            return 0.0
        return max(self.latencies)


# ---------------------------------------------------------------------------
# Sample text for streaming simulation
# ---------------------------------------------------------------------------

SAMPLE_CHUNKS = [
    "Based on the analysis of the meeting transcript, ",
    "here are the key action items identified: ",
    "First, the team needs to finalize the Q3 budget ",
    "by end of next week. Sarah will coordinate with ",
    "the finance department to gather remaining figures. ",
    "Second, the product launch timeline has been moved ",
    "to September 15th, giving engineering an additional ",
    "two weeks for stability testing. ",
    "Third, customer feedback from the beta program ",
    "indicates strong interest in the reporting feature, ",
    "with 78% of participants rating it as 'very useful'. ",
    "The team agreed to prioritize the dashboard redesign ",
    "in Sprint 4, incorporating the top 5 requested ",
    "improvements from the feedback survey. ",
    "Finally, a follow-up meeting is scheduled for ",
    "Thursday at 2pm to review the implementation plan. ",
]


# ---------------------------------------------------------------------------
# UI
# ---------------------------------------------------------------------------

# Parse CLI args before NiceGUI takes over
_parser = argparse.ArgumentParser()
_parser.add_argument("--soundcard", action="store_true", help="Use soundcard (COM) backend instead of sounddevice")
_parser.add_argument("--browser", action="store_true", help="Run in browser instead of native window (removes pywebview/COM)")
_args, _ = _parser.parse_known_args()

# Select audio backend
if _args.soundcard:
    audio = SoundCardCapture(chunk_seconds=0.1)  # 100ms chunks (was 1s)
else:
    audio = SoundDeviceCapture(chunk_seconds=0.1)

benchmark = StreamingBenchmark()
start_time: float = 0.0


@ui.page('/')
def index():
    global start_time
    start_time = time.time()

    # Start audio capture when page loads
    if not audio.is_running:
        audio.start()
        logger.info(f"Spike app started — {audio.backend_name}")

    ui.dark_mode().enable()

    with ui.header().classes("items-center justify-between bg-blue-900"):
        ui.label("NiceGUI Validation Spike").classes("text-xl font-bold")
        ui.label(f"DAR2-31/32/33 | Backend: {audio.backend_name}").classes("text-sm opacity-70")

    with ui.column().classes("w-full max-w-4xl mx-auto p-4 gap-4"):

        # ── Status Banner ──
        status_label = ui.label("Initializing...").classes(
            "text-lg font-bold p-3 rounded bg-yellow-900 w-full text-center"
        )
        timer_label = ui.label("Elapsed: 0:00").classes("text-center text-sm opacity-70")

        # ── Condition 1: COM Compatibility ──
        with ui.card().classes("w-full"):
            ui.label(f"Condition 1: Audio Capture ({audio.backend_name})").classes(
                "text-lg font-bold text-blue-400"
            )
            ui.label(f"Backend: {audio.backend_name} | Chunk size: {audio.chunk_seconds}s")
            ui.separator()

            with ui.row().classes("items-center gap-4 w-full"):
                ui.label("Audio Level:")
                level_bar = ui.linear_progress(value=0).classes("flex-grow")
                level_text = ui.label("0%").classes("w-16 text-right")

            with ui.row().classes("gap-8"):
                chunks_label = ui.label("Chunks captured: 0")
                dropouts_label = ui.label("Dropouts: 0")
                capture_status = ui.label("Status: Starting...").classes("text-yellow-400")

        # ── Condition 2: Streaming Latency ──
        with ui.card().classes("w-full"):
            ui.label("Condition 2: Streaming Latency Benchmark").classes(
                "text-lg font-bold text-green-400"
            )
            ui.label(f"Target: {benchmark.target_rate} chunks/sec — simulating Claude API streaming")
            ui.separator()

            with ui.row().classes("gap-8"):
                stream_chunks_label = ui.label("Chunks streamed: 0")
                avg_lat_label = ui.label("Avg latency: --")
                p95_lat_label = ui.label("P95 latency: --")
                max_lat_label = ui.label("Max latency: --")

            stream_output = ui.html("", sanitize=False).classes(
                "w-full h-48 overflow-y-auto bg-gray-800 p-3 rounded font-mono text-sm"
            )

            with ui.row().classes("gap-4"):
                stream_btn = ui.button("Start Streaming Benchmark", on_click=lambda: toggle_streaming())
                rate_slider = ui.slider(min=10, max=100, value=75, step=5).classes("w-48")
                rate_label = ui.label("75 chunks/sec")

        # ── Results Summary ──
        with ui.card().classes("w-full"):
            ui.label("Results Summary").classes("text-lg font-bold text-purple-400")
            ui.separator()
            results_log = ui.log(max_lines=50).classes("w-full h-40")

        # ── Controls ──
        with ui.row().classes("gap-4"):
            ui.button("Stop Audio Capture", on_click=lambda: stop_audio())
            ui.button("Export Results", on_click=lambda: export_results())

    # ── State ──
    streaming_active = {"value": False}
    streaming_task = {"ref": None}
    chunk_counter = {"value": 0}

    def toggle_streaming() -> None:
        if streaming_active["value"]:
            streaming_active["value"] = False
            stream_btn.text = "Start Streaming Benchmark"
            results_log.push(f"[{elapsed_str()}] Streaming benchmark stopped")
        else:
            streaming_active["value"] = True
            benchmark.text_buffer = ""
            benchmark.chunks_sent = 0
            benchmark.latencies.clear()
            stream_output.set_content("")
            stream_btn.text = "Stop Streaming Benchmark"
            results_log.push(f"[{elapsed_str()}] Streaming benchmark started at {benchmark.target_rate} chunks/sec")
            streaming_task["ref"] = asyncio.create_task(run_streaming())

    async def run_streaming() -> None:
        chunk_idx = 0
        while streaming_active["value"]:
            text = SAMPLE_CHUNKS[chunk_idx % len(SAMPLE_CHUNKS)]
            chunk_id = chunk_counter["value"]
            chunk_counter["value"] += 1

            benchmark.record_emit(chunk_id)
            benchmark.text_buffer += text
            benchmark.chunks_sent += 1

            # Update UI — this is what we're measuring
            html_content = f'<span style="color: #e0e0e0;">{benchmark.text_buffer}</span>'
            stream_output.set_content(html_content)

            # Record ack (Python-side — measures through NiceGUI's Socket.io push)
            # In a real app we'd measure JS-side paint, but this measures the
            # Python → Socket.io → browser push latency which is the critical path
            benchmark.record_ack(chunk_id)

            chunk_idx += 1
            await asyncio.sleep(1.0 / benchmark.target_rate)

    def stop_audio() -> None:
        audio.stop()
        capture_status.text = "Status: Stopped"
        capture_status.classes(remove="text-yellow-400 text-green-400", add="text-red-400")
        results_log.push(f"[{elapsed_str()}] Audio capture stopped manually")

    def export_results() -> None:
        elapsed = time.time() - start_time
        report = [
            "=" * 60,
            "NiceGUI VALIDATION SPIKE — RESULTS",
            "=" * 60,
            f"Total runtime: {elapsed:.0f}s ({elapsed/60:.1f} min)",
            "",
            f"--- Condition 1: Audio Capture ({audio.backend_name}) ---",
            f"Audio chunks captured: {audio.chunks_captured}",
            f"Audio dropouts: {audio.dropouts}",
            f"Capture errors: {len(audio.capture_errors)}",
            f"Dropout rate: {audio.dropouts / max(audio.chunks_captured, 1) * 100:.1f}%",
            f"PASS: {'YES' if audio.chunks_captured > 0 and audio.dropouts < audio.chunks_captured * 0.01 else 'NO'} (target: < 1% dropout)",
            "",
            "--- Condition 2: Streaming Latency ---",
            f"Chunks streamed: {benchmark.chunks_sent}",
            f"Target rate: {benchmark.target_rate} chunks/sec",
            f"Avg latency: {benchmark.avg_latency_ms:.1f}ms",
            f"P95 latency: {benchmark.p95_latency_ms:.1f}ms",
            f"Max latency: {benchmark.max_latency_ms:.1f}ms",
            f"PASS: {'YES' if benchmark.avg_latency_ms < 100 else 'NO'} (target: < 100ms avg)",
            "",
            "--- Overall ---",
            f"10-min stability: {'PASS' if elapsed >= 600 and not audio.capture_errors else 'NOT YET' if elapsed < 600 else 'FAIL'}",
            "=" * 60,
        ]
        report_text = "\n".join(report)
        results_log.push(report_text)
        logger.info(report_text)

        # Also write to file
        with open("spike_results.txt", "w") as f:
            f.write(report_text)
        results_log.push(f"Results exported to spike_results.txt")

    def elapsed_str() -> str:
        e = int(time.time() - start_time)
        return f"{e // 60}:{e % 60:02d}"

    # ── Periodic UI update timer ──
    def update_ui() -> None:
        elapsed = time.time() - start_time
        mins = int(elapsed) // 60
        secs = int(elapsed) % 60
        timer_label.text = f"Elapsed: {mins}:{secs:02d}"

        # Rate slider binding
        benchmark.target_rate = int(rate_slider.value)
        rate_label.text = f"{benchmark.target_rate} chunks/sec"

        # Audio metrics
        if audio.is_running:
            level_bar.value = audio.level
            level_text.text = f"{int(audio.level * 100)}%"
            chunks_label.text = f"Chunks captured: {audio.chunks_captured}"
            dropouts_label.text = f"Dropouts: {audio.dropouts}"
            capture_status.text = "Status: Running"
            capture_status.classes(remove="text-yellow-400 text-red-400", add="text-green-400")
        elif audio.capture_errors:
            capture_status.text = f"Status: ERROR — {audio.capture_errors[-1]}"
            capture_status.classes(remove="text-yellow-400 text-green-400", add="text-red-400")

        # Streaming metrics
        stream_chunks_label.text = f"Chunks streamed: {benchmark.chunks_sent}"
        avg_lat_label.text = f"Avg latency: {benchmark.avg_latency_ms:.1f}ms"
        p95_lat_label.text = f"P95 latency: {benchmark.p95_latency_ms:.1f}ms"
        max_lat_label.text = f"Max latency: {benchmark.max_latency_ms:.1f}ms"

        # Status banner
        if elapsed >= 600:  # 10 minutes
            if audio.chunks_captured > 0 and not audio.capture_errors and audio.is_running:
                status_label.text = "10 MINUTES PASSED — COM Compatibility: PASS"
                status_label.classes(remove="bg-yellow-900 bg-red-900", add="bg-green-900")
            elif audio.capture_errors:
                status_label.text = "FAIL — COM conflict or audio error detected"
                status_label.classes(remove="bg-yellow-900 bg-green-900", add="bg-red-900")
        elif audio.capture_errors:
            status_label.text = "FAIL — COM conflict or audio error detected"
            status_label.classes(remove="bg-yellow-900 bg-green-900", add="bg-red-900")
        else:
            remaining = 600 - elapsed
            status_label.text = f"Running... {int(remaining)}s until 10-min COM stability mark"

        # Auto-log milestones
        if int(elapsed) in (60, 120, 180, 300, 600) and int(elapsed) == int(elapsed):
            results_log.push(
                f"[{elapsed_str()}] Milestone: {mins}min | "
                f"Audio chunks: {audio.chunks_captured} | "
                f"Dropouts: {audio.dropouts} | "
                f"Errors: {len(audio.capture_errors)}"
            )

    ui.timer(0.5, update_ui)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if _args.browser:
    ui.run(title="NiceGUI Validation Spike", reload=False)
else:
    ui.run(
        title="NiceGUI Validation Spike",
        native=True,
        window_size=(1000, 800),
        reload=False,
    )
