"""Framework-agnostic application controller for Darin Audio Assistant.

Owns all orchestration logic: recording lifecycle, transcription dispatch,
prompt execution, and thread management. Communicates via callbacks — no Qt
imports allowed in this module.

DAR2-35: Extracted from ui/main_window.py so NiceGUI (or any future UI) can
consume the same interface.
"""

from __future__ import annotations

import asyncio
import threading
import time
from collections.abc import Callable

import numpy as np
from loguru import logger

import config
from api.client import ApiClient
from api.deepgram_streaming import DeepgramStreamingClient
from audio.recorder import ContinuousRecorder
from storage.meeting_store import MeetingStore


class AppController:
    """Framework-agnostic backend controller.

    All UI communication happens through callbacks passed at init time.
    The controller runs background threads internally and invokes callbacks
    from those threads — the UI layer is responsible for marshalling to its
    own main thread (e.g. Qt signal emission, NiceGUI ui.timer, etc.).
    """

    def __init__(
        self,
        *,
        on_recording_started: Callable[[], None] | None = None,
        on_recording_stopped: Callable[[], None] | None = None,
        on_transcription_complete: Callable[[str], None] | None = None,
        on_processing_complete: Callable[[dict], None] | None = None,
        on_progress: Callable[[str], None] | None = None,
        on_stream_chunk: Callable[[str], None] | None = None,
        # Live streaming callbacks (DAR2-23)
        on_interim_transcript: Callable[[str], None] | None = None,
        on_final_transcript: Callable[[str], None] | None = None,
        on_utterance_end: Callable[[str], None] | None = None,
        # Whisper mode callback (DAR2-15)
        on_whisper_transcript: Callable[[str], None] | None = None,
    ) -> None:
        # Callbacks (UI layer provides these)
        self._on_recording_started = on_recording_started
        self._on_recording_stopped = on_recording_stopped
        self._on_transcription_complete = on_transcription_complete
        self._on_processing_complete = on_processing_complete
        self._on_progress = on_progress
        self._on_stream_chunk = on_stream_chunk

        # Live streaming callbacks (DAR2-23)
        self._on_interim_transcript = on_interim_transcript
        self._on_final_transcript = on_final_transcript
        self._on_utterance_end = on_utterance_end

        # Whisper mode callback (DAR2-15)
        self._on_whisper_transcript = on_whisper_transcript

        # Backend components
        self.recorder = ContinuousRecorder(buffer_minutes=config.BUFFER_MINUTES)
        self.api_client = ApiClient()

        # Live streaming client (DAR2-23)
        self._streaming_client: DeepgramStreamingClient | None = None

        # Thread-safe state
        self._transcript_lock = threading.Lock()
        self._processing_lock = threading.Lock()
        self._current_transcript: str = ""
        self._is_processing: bool = False

        # HTML streaming state (needed by _setup_static_template flow)
        self._template_type: str | None = None

        # Whisper mode — always-on background transcription (DAR2-15)
        self._whisper_client: DeepgramStreamingClient | None = None
        self._whisper_active: bool = False

        # Meeting storage (DAR2-25)
        self._meeting_store: MeetingStore | None = None
        self._active_meeting_id: int | None = None

        # Meeting state machine (DAR2-26)
        self._meeting_state: str = "idle"  # idle | active | post_meeting
        self._state_change_callbacks: list[Callable[[str], None]] = []
        self._timer_callbacks: list[Callable[[int], None]] = []
        self._timer_task: asyncio.Task | None = None
        self._meeting_start_time: float | None = None
        self._last_meeting_id: int | None = None

        logger.info("AppController initialized", buffer_minutes=config.BUFFER_MINUTES)

    # ------------------------------------------------------------------
    # Thread-safe properties
    # ------------------------------------------------------------------

    @property
    def current_transcript(self) -> str:
        with self._transcript_lock:
            return self._current_transcript

    @current_transcript.setter
    def current_transcript(self, value: str) -> None:
        with self._transcript_lock:
            self._current_transcript = value

    @property
    def is_processing(self) -> bool:
        with self._processing_lock:
            return self._is_processing

    @is_processing.setter
    def is_processing(self, value: bool) -> None:
        with self._processing_lock:
            self._is_processing = value

    @property
    def is_recording(self) -> bool:
        return self.recorder.is_recording

    @property
    def buffer_seconds(self) -> int:
        return self.recorder.get_buffer_seconds()

    @property
    def template_type(self) -> str | None:
        return self._template_type

    @template_type.setter
    def template_type(self, value: str | None) -> None:
        self._template_type = value

    @property
    def meeting_store(self) -> MeetingStore | None:
        return self._meeting_store

    @meeting_store.setter
    def meeting_store(self, store: MeetingStore | None) -> None:
        self._meeting_store = store

    # ------------------------------------------------------------------
    # Callback setters (DAR2-36)
    #
    # Allow UI components to register callbacks after construction.
    # The setters write directly into the private fields that
    # _run_prompt_thread reads, so late-binding (e.g. NiceGUI) works
    # identically to constructor-time wiring (e.g. PyQt6).
    # ------------------------------------------------------------------

    @property
    def on_stream_chunk(self) -> Callable[[str], None] | None:
        """Callback invoked with each streaming text chunk from Claude."""
        return self._on_stream_chunk

    @on_stream_chunk.setter
    def on_stream_chunk(self, callback: Callable[[str], None] | None) -> None:
        self._on_stream_chunk = callback

    @property
    def on_processing_complete(self) -> Callable[[dict], None] | None:
        """Callback invoked when Claude finishes processing a prompt."""
        return self._on_processing_complete

    @on_processing_complete.setter
    def on_processing_complete(self, callback: Callable[[dict], None] | None) -> None:
        self._on_processing_complete = callback

    @property
    def on_progress(self) -> Callable[[str], None] | None:
        """Callback invoked with progress status messages."""
        return self._on_progress

    @on_progress.setter
    def on_progress(self, callback: Callable[[str], None] | None) -> None:
        self._on_progress = callback

    # ------------------------------------------------------------------
    # Recording lifecycle
    # ------------------------------------------------------------------

    def start_recording(self) -> bool:
        """Start audio capture. Returns True on success."""
        logger.info("Starting audio recording")
        if self.recorder.start_recording():
            logger.info("Audio recording started successfully")
            if self._on_recording_started:
                self._on_recording_started()
            return True
        logger.error("Failed to start audio recording")
        return False

    def stop_recording(self) -> bool:
        """Stop audio capture. Returns True on success."""
        logger.info("Stopping audio recording")
        if self.recorder.stop_recording():
            logger.info("Audio recording stopped successfully")
            if self._on_recording_stopped:
                self._on_recording_stopped()
            return True
        logger.error("Failed to stop audio recording")
        return False

    def toggle_recording(self) -> bool:
        """Toggle recording state. Returns True on success."""
        if not self.recorder.is_recording:
            return self.start_recording()
        return self.stop_recording()

    # ------------------------------------------------------------------
    # Live streaming (DAR2-23)
    # ------------------------------------------------------------------

    def start_streaming(self) -> bool:
        """Start live WebSocket transcription alongside recording.

        Creates a DeepgramStreamingClient connected to Deepgram, then starts
        the recorder with an on_chunk callback that forwards audio to the
        WebSocket. Returns True on success.
        """
        if self._streaming_client is not None and self._streaming_client.is_connected:
            logger.warning("Streaming already active")
            return False

        logger.info("Starting live streaming transcription")

        # Create streaming client
        self._streaming_client = DeepgramStreamingClient(
            api_key=self.api_client.deepgram_api_key,
            sample_rate=self.recorder.sample_rate,
            on_interim_transcript=self._on_interim_transcript,
            on_final_transcript=self._on_final_transcript_with_storage,
            on_utterance_end=self._handle_utterance_end,
            on_error=self._on_streaming_error,
        )
        self._streaming_client.connect()

        if not self._streaming_client.is_connected:
            logger.error("Failed to establish Deepgram WebSocket connection")
            self._streaming_client = None
            return False

        # Wire the recorder's chunk consumer to forward audio to the streaming client
        self.recorder.add_chunk_consumer(self._on_recorder_chunk)

        # Create meeting record if storage is available
        if self._meeting_store is not None:
            self._active_meeting_id = self._meeting_store.start_meeting()

        # Start recording if not already
        if not self.recorder.is_recording:
            self.start_recording()

        return True

    def stop_streaming(self) -> str:
        """Stop live WebSocket streaming. Returns the accumulated transcript."""
        if self._streaming_client is None:
            return ""

        logger.info("Stopping live streaming transcription")

        # Disconnect streaming
        self._streaming_client.disconnect()
        transcript = self._streaming_client.get_full_transcript()

        # Finalize meeting record
        if self._meeting_store is not None and self._active_meeting_id is not None:
            self._meeting_store.end_meeting(self._active_meeting_id)

        # Update current transcript with the accumulated result
        self.current_transcript = transcript

        # Only unhook the chunk consumer if whisper mode is also inactive
        if not self._whisper_active:
            self.recorder.remove_chunk_consumer(self._on_recorder_chunk)
        self._streaming_client = None
        self._active_meeting_id = None

        # Notify via standard transcription callback
        if self._on_transcription_complete and transcript:
            self._on_transcription_complete(transcript)

        return transcript

    @property
    def is_streaming(self) -> bool:
        """Whether live WebSocket streaming is active."""
        return self._streaming_client is not None and self._streaming_client.is_connected

    def _on_recorder_chunk(self, audio_chunk: np.ndarray) -> None:
        """Forward audio chunks from the recorder and whisper client."""
        if self._streaming_client is not None:
            self._streaming_client.send_audio(audio_chunk)
        if self._whisper_client is not None and self._whisper_active:
            self._whisper_client.send_audio(audio_chunk)

    # ------------------------------------------------------------------
    # Whisper mode — always-on background transcription (DAR2-15)
    # ------------------------------------------------------------------

    @property
    def is_whisper_active(self) -> bool:
        """Whether whisper mode (always-on background transcription) is running."""
        return self._whisper_active and self._whisper_client is not None

    @property
    def on_whisper_transcript(self) -> Callable[[str], None] | None:
        """Callback for whisper transcript updates."""
        return self._on_whisper_transcript

    @on_whisper_transcript.setter
    def on_whisper_transcript(self, callback: Callable[[str], None] | None) -> None:
        self._on_whisper_transcript = callback

    def start_whisper_mode(self) -> bool:
        """Start always-on background transcription.

        Creates a dedicated DeepgramStreamingClient that receives audio chunks
        continuously. Accumulated transcript is used by run_prompt() instead of
        triggering a REST batch transcription call.

        Returns True on success.
        """
        if self._whisper_active:
            logger.info("Whisper mode already active")
            return True

        logger.info("Starting whisper mode")

        self._whisper_client = DeepgramStreamingClient(
            api_key=self.api_client.deepgram_api_key,
            sample_rate=self.recorder.sample_rate,
            on_interim_transcript=None,
            on_final_transcript=self._handle_whisper_final,
            on_utterance_end=None,
            on_error=lambda err: logger.warning(f"Whisper error: {err}"),
        )
        self._whisper_client.connect()

        if not self._whisper_client.is_connected:
            logger.error("Whisper mode: failed to connect to Deepgram")
            self._whisper_client = None
            return False

        self._whisper_active = True

        # Start the recorder so audio chunks flow — it may already be running
        if not self.recorder.is_recording:
            self.recorder.start_recording()

        # Register our chunk consumer (shared with meeting streaming if active)
        self.recorder.add_chunk_consumer(self._on_recorder_chunk)

        logger.info("Whisper mode active")
        return True

    def stop_whisper_mode(self) -> None:
        """Stop background transcription and release resources."""
        if not self._whisper_active:
            return

        logger.info("Stopping whisper mode")
        self._whisper_active = False

        if self._whisper_client is not None:
            self._whisper_client.disconnect()
            self._whisper_client = None

        # Only remove the chunk consumer if meeting streaming is also inactive
        if self._streaming_client is None:
            self.recorder.remove_chunk_consumer(self._on_recorder_chunk)

        logger.info("Whisper mode stopped")

    def _handle_whisper_final(self, text: str) -> None:
        """Handle a finalized whisper transcript segment."""
        if not text.strip():
            return

        with self._transcript_lock:
            if self._current_transcript:
                self._current_transcript = self._current_transcript + " " + text
            else:
                self._current_transcript = text

        logger.debug(f"Whisper segment received: {len(text)} chars")

        if self._on_whisper_transcript:
            self._on_whisper_transcript(text)

    def _handle_utterance_end(self, full_transcript: str) -> None:
        """Handle utterance end — update current transcript."""
        self.current_transcript = full_transcript
        if self._on_utterance_end:
            self._on_utterance_end(full_transcript)

    def _on_streaming_error(self, error: str) -> None:
        """Handle streaming errors."""
        logger.error(f"Streaming error: {error}")

    def _handle_meeting_segment(self, text: str) -> None:
        """Append a final transcript segment to the active meeting."""
        if self._meeting_store is not None and self._active_meeting_id is not None:
            self._meeting_store.append_segment(self._active_meeting_id, text)

    def _on_final_transcript_with_storage(self, text: str) -> None:
        """Handle final transcript: store segment AND notify UI."""
        self._handle_meeting_segment(text)
        if self._on_final_transcript:
            self._on_final_transcript(text)

    # ------------------------------------------------------------------
    # Meeting lifecycle (DAR2-26)
    # ------------------------------------------------------------------

    @property
    def meeting_state(self) -> str:
        """Current meeting state: 'idle', 'active', or 'post_meeting'."""
        return self._meeting_state

    async def start_meeting(self) -> None:
        """Begin a meeting session."""
        self.start_streaming()
        self._meeting_state = "active"
        self._meeting_start_time = time.monotonic()
        self._timer_task = asyncio.create_task(self._run_timer())
        self._emit_state_change("active")

    async def stop_meeting(self) -> None:
        """End the meeting session."""
        if self._timer_task is not None:
            self._timer_task.cancel()
            try:
                await self._timer_task
            except asyncio.CancelledError:
                pass
            self._timer_task = None

        self._last_meeting_id = self._active_meeting_id  # preserve for post-meeting
        self.stop_streaming()
        self._meeting_state = "post_meeting"
        self._emit_state_change("post_meeting")

    async def reset_to_idle(self) -> None:
        """Return to idle state."""
        self._meeting_state = "idle"
        self._meeting_start_time = None
        self._last_meeting_id = None
        self._emit_state_change("idle")

    def on_meeting_state_change(self, callback: Callable[[str], None]) -> None:
        """Register callback for state transitions."""
        self._state_change_callbacks.append(callback)

    def on_timer_tick(self, callback: Callable[[int], None]) -> None:
        """Register callback for elapsed timer ticks (every second)."""
        self._timer_callbacks.append(callback)

    def get_meeting_transcript(self) -> str | None:
        """Retrieve full transcript for the current/last meeting."""
        meeting_id = self._active_meeting_id or self._last_meeting_id
        if self._meeting_store is None or meeting_id is None:
            return None
        return self._meeting_store.get_full_transcript(meeting_id)

    def _emit_state_change(self, state: str) -> None:
        """Notify all registered state-change callbacks."""
        for cb in self._state_change_callbacks:
            cb(state)

    async def _run_timer(self) -> None:
        """Tick every second with elapsed time since meeting start."""
        while True:
            await asyncio.sleep(1)
            if self._meeting_start_time is not None:
                elapsed = int(time.monotonic() - self._meeting_start_time)
                for cb in self._timer_callbacks:
                    cb(elapsed)

    # ------------------------------------------------------------------
    # Transcription (batch/REST)
    # ------------------------------------------------------------------

    def transcribe_buffer(self) -> None:
        """Transcribe the full audio buffer in a background thread."""
        audio_data = self.recorder.save_buffer()
        if audio_data is None:
            logger.warning("Transcription failed: No audio in buffer")
            if self._on_transcription_complete:
                self._on_transcription_complete("")
            return

        logger.info(
            "Starting transcription from buffer",
            buffer_size_bytes=len(audio_data),
            sample_rate=self.recorder.sample_rate,
        )
        threading.Thread(
            target=self._transcribe_thread,
            args=(audio_data, self.recorder.sample_rate),
            daemon=True,
        ).start()

    def transcribe_last_n_seconds(self, seconds: float = 30) -> None:
        """Transcribe the last N seconds of audio in a background thread."""
        audio_data = self.recorder.get_last_n_seconds(seconds)
        if audio_data is None:
            logger.warning(
                "Transcription failed: Not enough audio in buffer",
                requested_seconds=seconds,
            )
            if self._on_transcription_complete:
                self._on_transcription_complete("")
            return

        logger.info(
            "Starting transcription from last N seconds",
            seconds=seconds,
            buffer_size_bytes=len(audio_data),
            sample_rate=self.recorder.sample_rate,
        )
        threading.Thread(
            target=self._transcribe_thread,
            args=(audio_data, self.recorder.sample_rate),
            daemon=True,
        ).start()

    def _transcribe_thread(self, audio_data: object, sample_rate: int) -> None:
        """Background thread for transcription."""
        start_time = time.perf_counter()
        logger.info(
            "Transcription thread started",
            buffer_size_bytes=len(audio_data),
            sample_rate=sample_rate,
        )
        try:
            text = self.api_client.transcribe_with_deepgram(audio_data, sample_rate)
            duration_ms = (time.perf_counter() - start_time) * 1000
            logger.info(
                "Transcription complete",
                transcript_length=len(text),
                duration_ms=f"{duration_ms:.2f}",
            )
            self.current_transcript = text
            if self._on_transcription_complete:
                self._on_transcription_complete(text)
        except Exception as e:
            duration_ms = (time.perf_counter() - start_time) * 1000
            logger.error(
                "Transcription failed",
                error=str(e),
                duration_ms=f"{duration_ms:.2f}",
                exc_info=True,
            )
            if self._on_transcription_complete:
                self._on_transcription_complete(f"Transcription error: {e!s}")

    # ------------------------------------------------------------------
    # Prompt execution
    # ------------------------------------------------------------------

    def run_prompt(
        self,
        prompt_template: str,
        title: str | None = None,
        *,
        on_template_setup: Callable[[str], str | None] | None = None,
    ) -> None:
        """Run a prompt against the current transcript (or auto-transcribe first).

        Args:
            prompt_template: The prompt template string with {transcript} placeholder.
            title: Display title for the output.
            on_template_setup: UI callback to set up the static HTML template.
                              Receives prompt_template, returns template_type string.
                              Called from the background thread — UI layer must marshal.
        """
        # Atomic check-and-set for processing state
        with self._processing_lock:
            if self._is_processing:
                logger.warning("Prompt request rejected: already processing")
                return
            self._is_processing = True

        if self._on_progress:
            self._on_progress("Capturing audio and transcribing...")

        # Check for existing transcript (includes whisper-accumulated text)
        with self._transcript_lock:
            has_transcript = bool(self._current_transcript)
            transcript_copy = self._current_transcript if has_transcript else None

        # If whisper mode is active and we have accumulated text, use it directly
        # (skips the slow REST batch transcription path entirely)
        if self._whisper_active and has_transcript:
            logger.info(
                "Using whisper transcript",
                transcript_length=len(transcript_copy or ""),
            )

        if has_transcript:
            threading.Thread(
                target=self._run_prompt_thread,
                args=(transcript_copy, prompt_template, on_template_setup),
                daemon=True,
            ).start()
            return

        # No transcript — get audio and transcribe first
        from prompts.templates import (
            ANSWER_QUESTION_PROMPT,
            PRACTITIONER_INSIGHTS_STREAMING_PROMPT,
        )

        use_last_30s = prompt_template in [
            PRACTITIONER_INSIGHTS_STREAMING_PROMPT,
            ANSWER_QUESTION_PROMPT,
        ]

        audio_data = None
        if use_last_30s:
            audio_data = self.recorder.get_last_n_seconds(30)

        if audio_data is None:
            audio_data = self.recorder.save_buffer()

        if audio_data is None:
            logger.warning("Processing failed: No audio in buffer")
            self.is_processing = False
            if self._on_processing_complete:
                self._on_processing_complete({"error": "No audio in buffer to process"})
            return

        threading.Thread(
            target=self._transcribe_and_process_thread,
            args=(audio_data, self.recorder.sample_rate, prompt_template, on_template_setup),
            daemon=True,
        ).start()

    def _transcribe_and_process_thread(
        self,
        audio_data: object,
        sample_rate: int,
        prompt_template: str,
        on_template_setup: Callable[[str], str | None] | None,
    ) -> None:
        """Background thread: transcribe then process."""
        start_time = time.perf_counter()
        logger.info(
            "Transcribe and process thread started",
            buffer_size_bytes=len(audio_data),
            sample_rate=sample_rate,
        )
        try:
            if self._on_progress:
                self._on_progress("Transcribing audio...")

            text = self.api_client.transcribe_with_deepgram(audio_data, sample_rate)
            transcribe_duration_ms = (time.perf_counter() - start_time) * 1000
            logger.info(
                "Transcription phase complete",
                transcript_length=len(text),
                duration_ms=f"{transcribe_duration_ms:.2f}",
            )

            self.current_transcript = text
            if self._on_transcription_complete:
                self._on_transcription_complete(text)

            self._run_prompt_thread(text, prompt_template, on_template_setup)

            total_duration_ms = (time.perf_counter() - start_time) * 1000
            logger.info(
                "Transcribe and process complete",
                total_duration_ms=f"{total_duration_ms:.2f}",
            )
        except Exception as e:
            duration_ms = (time.perf_counter() - start_time) * 1000
            logger.error(
                "Transcribe and process failed",
                error=str(e),
                duration_ms=f"{duration_ms:.2f}",
                exc_info=True,
            )
            if self._on_processing_complete:
                self._on_processing_complete({"error": str(e)})

    def _run_prompt_thread(
        self,
        transcript: str,
        prompt_template: str,
        on_template_setup: Callable[[str], str | None] | None,
    ) -> None:
        """Background thread: process transcript with Claude API."""
        start_time = time.perf_counter()
        logger.info(
            "Starting LLM processing",
            transcript_length=len(transcript),
            template_type=str(prompt_template)[:50],
        )
        try:
            if self._on_progress:
                self._on_progress("Processing with Claude...")

            # Let UI set up the static template
            template_type = None
            if on_template_setup:
                template_type = on_template_setup(prompt_template)

            self._template_type = template_type
            logger.info("Template set up", template_type=template_type)

            def handle_stream(text: str) -> None:
                if self._on_stream_chunk:
                    self._on_stream_chunk(text)

            result = self.api_client.process_with_anthropic(
                transcript, prompt_template, stream=True, callback=handle_stream
            )
            duration_ms = (time.perf_counter() - start_time) * 1000
            logger.info(
                "LLM processing complete",
                template_type=template_type,
                duration_ms=f"{duration_ms:.2f}",
                result_length=len(str(result)),
            )

            if self._on_processing_complete:
                self._on_processing_complete({"result": result})
        except Exception as e:
            duration_ms = (time.perf_counter() - start_time) * 1000
            logger.error(
                "LLM processing failed",
                template_type=str(prompt_template)[:50],
                error=str(e),
                duration_ms=f"{duration_ms:.2f}",
                exc_info=True,
            )
            if self._on_processing_complete:
                self._on_processing_complete({"error": str(e)})
