"""Deepgram WebSocket streaming client for real-time transcription.

Wraps the Deepgram SDK v4 threaded ``ListenWebSocketClient`` with:

- blocking ``connect()`` / ``disconnect()`` (callers wrap in asyncio.to_thread)
- multichannel ME/THEM speaker attribution (channel 0 = ME mic, channel 1 =
  THEM speaker loopback)
- a drop-OLDEST reconnect queue (~30 s of audio) plus automatic reconnect
  with exponential backoff
- UtteranceEnd events surfaced from the REAL Deepgram UtteranceEnd message

DAR2-23: M1 — Deepgram WebSocket Streaming Engine (migrated to SDK v4).
"""

from __future__ import annotations

import queue
import threading
from collections.abc import Callable
from typing import Any

import numpy as np
from deepgram import (
    DeepgramClient,
    DeepgramClientOptions,
    LiveOptions,
    LiveTranscriptionEvents,
)
from loguru import logger

import config


# Reconnect constants
_MAX_RECONNECT_DELAY_S = 30
_INITIAL_RECONNECT_DELAY_S = 1

# Reconnect queue depth: ~30 s of audio at 100 ms chunks
_RECONNECT_QUEUE_CHUNKS = 300


def _build_live_options(
    *,
    sample_rate: int,
    channels: int,
    keyterms: list[str] | None,
) -> LiveOptions:
    """Build the nova-3 live transcription options (SDK v4)."""
    return LiveOptions(
        model=config.DEEPGRAM_MODEL,
        language=config.DEEPGRAM_LANGUAGE,
        encoding="linear16",
        sample_rate=sample_rate,
        channels=channels,
        multichannel=channels > 1,
        interim_results=True,
        smart_format=True,
        punctuate=True,
        endpointing=300,
        utterance_end_ms="1000",
        keyterm=list(keyterms) if keyterms else None,
    )


class DeepgramStreamingClient:
    """Persistent WebSocket connection to Deepgram for real-time transcription.

    The SDK v4 threaded client manages its own listener/keepalive threads.
    ``send_audio()`` is thread-safe and may be called from the recorder's
    capture pump thread. ``connect()``/``disconnect()`` are blocking — the
    caller wraps them in ``asyncio.to_thread``.

    Callback signatures:
        on_interim_transcript(text, speaker)
        on_final_transcript(text, speaker)   # speaker: "ME" | "THEM" | None
        on_utterance_end(full_transcript)    # fired on the REAL UtteranceEnd
        on_connection_state(state)           # connected/reconnecting/disconnected
        on_error(message)
    """

    def __init__(
        self,
        api_key: str,
        *,
        sample_rate: int = config.DEEPGRAM_SAMPLE_RATE,
        channels: int = 2,
        keyterms: list[str] | None = None,
        on_interim_transcript: Callable[[str, str | None], None] | None = None,
        on_final_transcript: Callable[[str, str | None], None] | None = None,
        on_utterance_end: Callable[[str], None] | None = None,
        on_connection_state: Callable[[str], None] | None = None,
        on_error: Callable[[str], None] | None = None,
    ) -> None:
        self._api_key = api_key
        self._sample_rate = sample_rate
        self._channels = channels
        self._keyterms = list(keyterms) if keyterms else []

        # Callbacks
        self._on_interim_transcript = on_interim_transcript
        self._on_final_transcript = on_final_transcript
        self._on_utterance_end = on_utterance_end
        self._on_connection_state = on_connection_state
        self._on_error = on_error

        # Internal state
        self._ws: Any = None  # deepgram ListenWebSocketClient
        self._ws_lock = threading.Lock()
        self._should_stop = threading.Event()
        self._connected = threading.Event()
        self._reconnect_thread: threading.Thread | None = None
        self._reconnect_lock = threading.Lock()

        # Bounded queue to hold audio during reconnections (drop-OLDEST)
        self._reconnect_queue: queue.Queue[bytes] = queue.Queue(maxsize=_RECONNECT_QUEUE_CHUNKS)

        # Transcript accumulation ("ME: ..." / "THEM: ..." lines in arrival order)
        self._segments_lock = threading.Lock()
        self._final_segments: list[str] = []

        self._options = _build_live_options(
            sample_rate=sample_rate, channels=channels, keyterms=self._keyterms
        )

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def connect(self) -> None:
        """Connect to Deepgram (blocking). Check ``is_connected`` afterwards.

        On failure the connection is left in a disconnected state; the caller
        must call ``disconnect()`` to release any partially started threads.
        """
        if self._connected.is_set():
            logger.warning("DeepgramStreamingClient already connected")
            return

        self._should_stop.clear()

        try:
            if self._open_connection():
                return
            message = "Deepgram WebSocket connection failed"
        except Exception as e:
            message = f"Deepgram WebSocket connection failed: {e}"

        logger.error(
            "Deepgram connect failed",
            model=config.DEEPGRAM_MODEL,
            error=message,
        )
        if self._on_error:
            self._on_error(message)

    def send_audio(self, audio_chunk: np.ndarray) -> None:
        """Send an audio chunk to Deepgram.

        Thread-safe — called from the recorder's capture pump thread.

        Args:
            audio_chunk: int16 numpy array, shape (frames, channels) with
                channel 0 = ME and channel 1 = THEM (or (frames,) mono).
        """
        if self._should_stop.is_set():
            return

        pcm_bytes = self._to_pcm_bytes(audio_chunk)

        with self._ws_lock:
            ws = self._ws
        if ws is not None and self._connected.is_set():
            try:
                if ws.send(pcm_bytes):
                    return
            except Exception as e:
                logger.debug(f"Deepgram send failed — queueing audio: {e}")
        self._queue_audio(pcm_bytes)

    def disconnect(self) -> None:
        """Gracefully disconnect from Deepgram and stop all worker threads."""
        logger.info("Disconnecting Deepgram streaming client")
        self._should_stop.set()

        reconnect_thread = self._reconnect_thread
        if reconnect_thread is not None and reconnect_thread.is_alive():
            reconnect_thread.join(timeout=5)
        self._reconnect_thread = None

        self._close_ws()
        self._connected.clear()
        self._notify_state("disconnected")

    def get_full_transcript(self) -> str:
        """Return accumulated "ME: ..."/"THEM: ..." lines joined by newlines."""
        with self._segments_lock:
            return "\n".join(self._final_segments)

    def clear_transcript(self) -> None:
        """Clear the accumulated transcript segments."""
        with self._segments_lock:
            self._final_segments.clear()

    @property
    def is_connected(self) -> bool:
        return self._connected.is_set()

    # ------------------------------------------------------------------
    # Connection management
    # ------------------------------------------------------------------

    def _open_connection(self) -> bool:
        """Create a fresh SDK websocket client and start it (blocking)."""
        dg = DeepgramClient(
            self._api_key,
            config=DeepgramClientOptions(
                api_key=self._api_key,
                options={"keepalive": "true"},
            ),
        )
        ws = dg.listen.websocket.v("1")

        ws.on(LiveTranscriptionEvents.Open, self._handle_open)
        ws.on(LiveTranscriptionEvents.Transcript, self._handle_transcript)
        ws.on(LiveTranscriptionEvents.UtteranceEnd, self._handle_utterance_end)
        ws.on(LiveTranscriptionEvents.Close, self._handle_close)
        ws.on(LiveTranscriptionEvents.Error, self._handle_error)

        logger.info(
            "Connecting to Deepgram WebSocket",
            model=config.DEEPGRAM_MODEL,
            sample_rate=self._sample_rate,
            channels=self._channels,
            keyterms=len(self._keyterms),
        )
        if not ws.start(self._options):
            return False

        with self._ws_lock:
            self._ws = ws
        self._connected.set()
        self._notify_state("connected")
        logger.info("Deepgram WebSocket connected")
        self._drain_reconnect_queue()
        return True

    def _close_ws(self) -> None:
        """Finish and drop the current SDK websocket client, if any."""
        with self._ws_lock:
            ws = self._ws
            self._ws = None
        if ws is None:
            return
        try:
            ws.finish()
        except Exception as e:
            logger.debug(f"Error during Deepgram finish: {e}")

    def _start_reconnect(self) -> None:
        """Kick off the reconnect thread (at most one at a time)."""
        if self._should_stop.is_set():
            return
        with self._reconnect_lock:
            if self._reconnect_thread is not None and self._reconnect_thread.is_alive():
                return
            self._reconnect_thread = threading.Thread(
                target=self._reconnect_loop,
                name="deepgram-reconnect",
                daemon=True,
            )
            self._reconnect_thread.start()

    def _reconnect_loop(self) -> None:
        """Reconnect with exponential backoff until success or stop."""
        delay = _INITIAL_RECONNECT_DELAY_S
        self._close_ws()
        while not self._should_stop.is_set():
            logger.info(f"Reconnecting to Deepgram in {delay}s")
            self._notify_state("reconnecting")
            if self._should_stop.wait(delay):
                return
            try:
                if self._open_connection():
                    return
                logger.warning("Deepgram reconnect attempt failed")
            except Exception as e:
                logger.warning(f"Deepgram reconnect attempt failed: {e}")
            delay = min(delay * 2, _MAX_RECONNECT_DELAY_S)

    # ------------------------------------------------------------------
    # SDK event handlers (called from the SDK listener thread)
    # ------------------------------------------------------------------

    def _handle_open(self, _client: Any, open: Any = None, **_kwargs: Any) -> None:  # noqa: A002
        """Handle WebSocket open event."""
        logger.info("Deepgram WebSocket opened")

    def _handle_transcript(self, _client: Any, result: Any = None, **_kwargs: Any) -> None:
        """Handle a transcript Results message (interim or final)."""
        try:
            transcript = result.channel.alternatives[0].transcript
        except (AttributeError, IndexError):
            return
        if not transcript:
            return

        speaker = self._speaker_for_result(result)
        if getattr(result, "is_final", False):
            line = f"{speaker}: {transcript}" if speaker else transcript
            with self._segments_lock:
                self._final_segments.append(line)
            logger.debug(f"Final transcript segment: {line[:80]}")
            if self._on_final_transcript:
                self._on_final_transcript(transcript, speaker)
        elif self._on_interim_transcript:
            self._on_interim_transcript(transcript, speaker)

    def _handle_utterance_end(
        self, _client: Any, utterance_end: Any = None, **_kwargs: Any
    ) -> None:
        """Handle the real UtteranceEnd event from Deepgram."""
        logger.debug("Deepgram UtteranceEnd received")
        if self._on_utterance_end:
            self._on_utterance_end(self.get_full_transcript())

    def _handle_close(self, _client: Any, close: Any = None, **_kwargs: Any) -> None:
        """Handle WebSocket close — reconnect unless we are stopping."""
        logger.info("Deepgram WebSocket closed")
        was_connected = self._connected.is_set()
        self._connected.clear()
        if self._should_stop.is_set():
            return
        if was_connected:
            self._notify_state("disconnected")
            self._start_reconnect()

    def _handle_error(self, _client: Any, error: Any = None, **_kwargs: Any) -> None:
        """Handle WebSocket error event."""
        error_str = str(error)
        logger.error(f"Deepgram WebSocket error: {error_str}")
        if self._on_error:
            self._on_error(error_str)

    def _speaker_for_result(self, result: Any) -> str | None:
        """Map a result's channel index to "ME" (0) / "THEM" (1) / None."""
        if self._channels < 2:
            return None
        channel_index = getattr(result, "channel_index", None) or []
        if not channel_index:
            return None
        channel = channel_index[0]
        if channel == 0:
            return "ME"
        if channel == 1:
            return "THEM"
        return None

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _to_pcm_bytes(audio_chunk: np.ndarray) -> bytes:
        """Convert a numpy audio chunk to interleaved int16 PCM bytes.

        int16 input is passed through (all channels preserved — Deepgram
        receives interleaved multichannel PCM); float input is clipped to
        [-1, 1] and scaled.
        """
        arr = np.asarray(audio_chunk)
        if arr.dtype != np.int16:
            arr = (np.clip(arr, -1.0, 1.0) * 32767).astype(np.int16)
        return arr.tobytes()

    def _queue_audio(self, pcm_bytes: bytes) -> None:
        """Queue audio during a reconnect, dropping the OLDEST chunk on overflow."""
        try:
            self._reconnect_queue.put_nowait(pcm_bytes)
        except queue.Full:
            try:
                self._reconnect_queue.get_nowait()
            except queue.Empty:
                pass
            try:
                self._reconnect_queue.put_nowait(pcm_bytes)
            except queue.Full:
                pass

    def _drain_reconnect_queue(self) -> None:
        """Send any audio that was queued during reconnection."""
        with self._ws_lock:
            ws = self._ws
        if ws is None:
            return
        drained = 0
        while True:
            try:
                pcm_bytes = self._reconnect_queue.get_nowait()
            except queue.Empty:
                break
            try:
                ws.send(pcm_bytes)
                drained += 1
            except Exception as e:
                logger.debug(f"Drain send failed: {e}")
                break
        if drained:
            logger.info(f"Drained {drained} queued audio chunks after reconnect")

    def _notify_state(self, state: str) -> None:
        """Notify the connection state callback."""
        if self._on_connection_state:
            self._on_connection_state(state)
