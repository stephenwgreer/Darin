"""Deepgram WebSocket streaming client for real-time transcription.

Provides a persistent WebSocket connection to Deepgram's live transcription
API. Runs an asyncio event loop in a dedicated daemon thread so the rest of
the application can remain synchronous/threaded.

DAR2-23: M1 — Deepgram WebSocket Streaming Engine
"""

from __future__ import annotations

import asyncio
import queue
import threading
from collections.abc import Callable

import numpy as np
from deepgram import Deepgram
from deepgram._enums import LiveTranscriptionEvent
from loguru import logger

import config


# Default options for Deepgram live transcription (v2 SDK dict format)
DEFAULT_LIVE_OPTIONS: dict = {
    "model": config.DEEPGRAM_MODEL,
    "language": config.DEEPGRAM_LANGUAGE,
    "encoding": "linear16",
    "sample_rate": config.DEEPGRAM_SAMPLE_RATE,
    "channels": 1,
    "interim_results": True,
    "punctuate": True,
    "smart_format": True,
    "endpointing": True,
    "vad_turnoff": 500,
}

# Reconnect constants
_MAX_RECONNECT_DELAY_S = 30
_INITIAL_RECONNECT_DELAY_S = 1
_KEEPALIVE_INTERVAL_S = 8


class DeepgramStreamingClient:
    """Persistent WebSocket connection to Deepgram for real-time transcription.

    Runs its own asyncio event loop in a daemon thread. Audio is sent from
    the recorder thread via ``send_audio()`` which is thread-safe (the SDK
    uses an internal ``asyncio.Queue``).

    Usage::

        client = DeepgramStreamingClient(
            api_key="...",
            on_final_transcript=print,
        )
        client.connect()
        client.send_audio(numpy_chunk)   # from any thread
        ...
        client.disconnect()
    """

    def __init__(
        self,
        api_key: str,
        *,
        sample_rate: int = config.DEEPGRAM_SAMPLE_RATE,
        on_interim_transcript: Callable[[str], None] | None = None,
        on_final_transcript: Callable[[str], None] | None = None,
        on_utterance_end: Callable[[str], None] | None = None,
        on_connection_state: Callable[[str], None] | None = None,
        on_error: Callable[[str], None] | None = None,
    ) -> None:
        self._api_key = api_key
        self._sample_rate = sample_rate

        # Callbacks
        self._on_interim_transcript = on_interim_transcript
        self._on_final_transcript = on_final_transcript
        self._on_utterance_end = on_utterance_end
        self._on_connection_state = on_connection_state
        self._on_error = on_error

        # Internal state
        self._connection = None  # LiveTranscription instance
        self._loop: asyncio.AbstractEventLoop | None = None
        self._loop_thread: threading.Thread | None = None
        self._should_stop = threading.Event()
        self._connected = threading.Event()
        # Bounded queue to hold audio during brief reconnections (max ~10 seconds of audio)
        self._reconnect_queue: queue.Queue[bytes] = queue.Queue(maxsize=10)

        # Transcript accumulation
        self._segments_lock = threading.Lock()
        self._final_segments: list[str] = []

        # Live options (copy so callers can't mutate the default)
        self._options = dict(DEFAULT_LIVE_OPTIONS)
        self._options["sample_rate"] = sample_rate

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def connect(self) -> None:
        """Start the asyncio event loop thread and connect to Deepgram."""
        if self._loop_thread is not None and self._loop_thread.is_alive():
            logger.warning("DeepgramStreamingClient already connected")
            return

        self._should_stop.clear()
        self._connected.clear()

        self._loop_thread = threading.Thread(
            target=self._run_loop,
            name="deepgram-ws-loop",
            daemon=True,
        )
        self._loop_thread.start()

        # Wait for connection to establish (with timeout)
        if not self._connected.wait(timeout=10):
            logger.error("Deepgram WebSocket connection timed out")
            if self._on_error:
                self._on_error("Connection timed out after 10 seconds")

    def send_audio(self, audio_chunk: np.ndarray) -> None:
        """Send an audio chunk to Deepgram.

        Thread-safe — may be called from the recorder thread.

        Args:
            audio_chunk: Float32 numpy array from the recorder.
                         Shape: (num_frames, num_channels) or (num_frames,)
        """
        if self._should_stop.is_set():
            return

        # Convert float32 numpy → mono int16 PCM bytes
        pcm_bytes = self._to_pcm_bytes(audio_chunk)

        if self._connection is not None and self._connected.is_set():
            self._connection.send(pcm_bytes)
        else:
            # Queue audio during reconnect (drop if queue is full)
            try:
                self._reconnect_queue.put_nowait(pcm_bytes)
            except queue.Full:
                pass  # Drop oldest audio rather than blocking

    def disconnect(self) -> None:
        """Gracefully disconnect from Deepgram and stop the event loop."""
        logger.info("Disconnecting Deepgram streaming client")
        self._should_stop.set()

        if self._loop and not self._loop.is_closed():
            # Schedule finish() on the event loop and wait for it
            future = asyncio.run_coroutine_threadsafe(self._finish(), self._loop)
            try:
                future.result(timeout=3)
            except Exception as e:
                logger.debug(f"Finish future completed with error: {e}")

        if self._loop_thread is not None:
            self._loop_thread.join(timeout=5)
            self._loop_thread = None

        self._connected.clear()
        self._connection = None
        self._notify_state("disconnected")

    def get_full_transcript(self) -> str:
        """Return the accumulated transcript from all finalized segments."""
        with self._segments_lock:
            return " ".join(self._final_segments)

    def clear_transcript(self) -> None:
        """Clear the accumulated transcript segments."""
        with self._segments_lock:
            self._final_segments.clear()

    @property
    def is_connected(self) -> bool:
        return self._connected.is_set()

    # ------------------------------------------------------------------
    # Asyncio event loop (runs in daemon thread)
    # ------------------------------------------------------------------

    def _run_loop(self) -> None:
        """Entry point for the daemon thread — runs the asyncio event loop."""
        try:
            asyncio.run(self._run())
        except Exception as e:
            logger.error(f"Deepgram event loop crashed: {e}", exc_info=True)
            if self._on_error:
                self._on_error(f"Event loop crashed: {e}")

    async def _run(self) -> None:
        """Main async routine: connect, keepalive, reconnect loop."""
        self._loop = asyncio.get_running_loop()

        while not self._should_stop.is_set():
            try:
                await self._connect_and_stream()
            except Exception as e:
                logger.error(f"Deepgram streaming error: {e}", exc_info=True)
                if self._on_error:
                    self._on_error(str(e))

            if self._should_stop.is_set():
                break

            # Reconnect with exponential backoff
            delay = _INITIAL_RECONNECT_DELAY_S
            while not self._should_stop.is_set():
                logger.info(f"Reconnecting to Deepgram in {delay}s")
                self._notify_state("reconnecting")
                await asyncio.sleep(delay)

                if self._should_stop.is_set():
                    break

                try:
                    await self._connect_and_stream()
                    break  # Connected successfully
                except Exception as e:
                    logger.error(f"Reconnect failed: {e}")
                    delay = min(delay * 2, _MAX_RECONNECT_DELAY_S)

    async def _connect_and_stream(self) -> None:
        """Establish connection and wait until it closes or we stop."""
        dg = Deepgram(self._api_key)

        logger.info(f"Connecting to Deepgram WebSocket (model={self._options.get('model')})")
        self._connection = await dg.transcription.live(self._options)

        # Register event handlers
        self._connection.register_handler(
            LiveTranscriptionEvent.TRANSCRIPT_RECEIVED,
            self._on_message,
        )
        self._connection.register_handler(
            LiveTranscriptionEvent.OPEN,
            self._on_open,
        )
        self._connection.register_handler(
            LiveTranscriptionEvent.CLOSE,
            self._on_close,
        )
        self._connection.register_handler(
            LiveTranscriptionEvent.ERROR,
            self._on_ws_error,
        )

        self._connected.set()
        self._notify_state("connected")
        logger.info("Deepgram WebSocket connected")

        # Drain any audio queued during reconnect
        self._drain_reconnect_queue()

        # Start keepalive task
        keepalive_task = asyncio.create_task(self._keepalive_loop())

        # Wait until the connection is done or we should stop
        try:
            while not self._connection.done and not self._should_stop.is_set():
                await asyncio.sleep(0.1)
        finally:
            keepalive_task.cancel()
            self._connected.clear()

    async def _keepalive_loop(self) -> None:
        """Send keepalive pings to prevent idle timeout."""
        while not self._should_stop.is_set():
            await asyncio.sleep(_KEEPALIVE_INTERVAL_S)
            if self._connection and not self._connection.done:
                try:
                    self._connection.keep_alive()
                except Exception as e:
                    logger.debug(f"KeepAlive failed: {e}")

    async def _finish(self) -> None:
        """Gracefully close the WebSocket connection."""
        if self._connection and not self._connection.done:
            try:
                await self._connection.finish()
            except Exception as e:
                logger.debug(f"Error during finish: {e}")

    # ------------------------------------------------------------------
    # Event handlers (called from asyncio context)
    # ------------------------------------------------------------------

    def _on_message(self, result: dict) -> None:
        """Handle a transcript message from Deepgram."""
        is_final = result.get("is_final", False)
        speech_final = result.get("speech_final", False)

        try:
            transcript = result["channel"]["alternatives"][0]["transcript"]
        except (KeyError, IndexError):
            return

        if not transcript:
            return

        if is_final:
            with self._segments_lock:
                self._final_segments.append(transcript)
            logger.debug(f"Final transcript segment: {transcript[:80]}")
            if self._on_final_transcript:
                self._on_final_transcript(transcript)

        if speech_final and self._on_utterance_end:
            full_text = self.get_full_transcript()
            self._on_utterance_end(full_text)

        if not is_final and self._on_interim_transcript:
            self._on_interim_transcript(transcript)

    def _on_open(self, _connection: object) -> None:
        """Handle WebSocket open event."""
        logger.info("Deepgram WebSocket opened")

    def _on_close(self, close_code: object) -> None:
        """Handle WebSocket close event."""
        logger.info(f"Deepgram WebSocket closed with code: {close_code}")
        self._connected.clear()
        self._notify_state("disconnected")

    def _on_ws_error(self, error: object) -> None:
        """Handle WebSocket error event."""
        error_str = str(error)
        logger.error(f"Deepgram WebSocket error: {error_str}")
        if self._on_error:
            self._on_error(error_str)

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _to_pcm_bytes(audio_chunk: np.ndarray) -> bytes:
        """Convert a float32 numpy audio chunk to int16 PCM bytes.

        Args:
            audio_chunk: Float32 array, shape (frames, channels) or (frames,).

        Returns:
            Raw int16 PCM bytes (mono, little-endian).
        """
        # Take first channel if multichannel
        if audio_chunk.ndim == 2:
            mono = audio_chunk[:, 0]
        else:
            mono = audio_chunk

        # Clip and convert float32 [-1.0, 1.0] → int16
        clipped = np.clip(mono, -1.0, 1.0)
        pcm_int16 = (clipped * 32767).astype(np.int16)
        return pcm_int16.tobytes()

    def _drain_reconnect_queue(self) -> None:
        """Send any audio that was queued during reconnection."""
        drained = 0
        while not self._reconnect_queue.empty():
            try:
                pcm_bytes = self._reconnect_queue.get_nowait()
                if self._connection:
                    self._connection.send(pcm_bytes)
                drained += 1
            except queue.Empty:
                break
        if drained:
            logger.info(f"Drained {drained} queued audio chunks after reconnect")

    def _notify_state(self, state: str) -> None:
        """Notify the connection state callback."""
        if self._on_connection_state:
            self._on_connection_state(state)
