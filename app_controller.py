"""Framework-agnostic application controller for Darin Audio Assistant.

Owns all orchestration logic: recording lifecycle, transcription dispatch,
prompt execution, and thread management. Communicates via callbacks — no Qt
imports allowed in this module.

DAR2-35: Extracted from ui/main_window.py so NiceGUI (or any future UI) can
consume the same interface.
"""

from __future__ import annotations

import threading
import time
from collections.abc import Callable

import numpy as np
from loguru import logger

import config
from api.client import ApiClient
from api.deepgram_streaming import DeepgramStreamingClient
from audio.recorder import ContinuousRecorder


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
            on_final_transcript=self._on_final_transcript,
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

        # Update current transcript with the accumulated result
        self.current_transcript = transcript

        # Unhook the chunk consumer
        self.recorder.remove_chunk_consumer(self._on_recorder_chunk)
        self._streaming_client = None

        # Notify via standard transcription callback
        if self._on_transcription_complete and transcript:
            self._on_transcription_complete(transcript)

        return transcript

    @property
    def is_streaming(self) -> bool:
        """Whether live WebSocket streaming is active."""
        return self._streaming_client is not None and self._streaming_client.is_connected

    def _on_recorder_chunk(self, audio_chunk: np.ndarray) -> None:
        """Forward audio chunks from the recorder to the streaming client."""
        if self._streaming_client is not None:
            self._streaming_client.send_audio(audio_chunk)

    def _handle_utterance_end(self, full_transcript: str) -> None:
        """Handle utterance end — update current transcript."""
        self.current_transcript = full_transcript
        if self._on_utterance_end:
            self._on_utterance_end(full_transcript)

    def _on_streaming_error(self, error: str) -> None:
        """Handle streaming errors."""
        logger.error(f"Streaming error: {error}")

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

        # Check for existing transcript
        with self._transcript_lock:
            has_transcript = bool(self._current_transcript)
            transcript_copy = self._current_transcript if has_transcript else None

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
