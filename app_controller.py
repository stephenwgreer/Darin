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
from collections import deque
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from typing import TYPE_CHECKING

import numpy as np
from loguru import logger

import config
from api.client import ApiClient, build_system_blocks, build_transcript_messages
from api.deepgram_streaming import DeepgramStreamingClient
from audio.recorder import ContinuousRecorder
from services.auto_answer import AUTO_ANSWER_TRIGGER, AutoAnswerPolicy
from services.cards import Card
from services.context_pack import ContextPack
from services.rolling_summary import RollingSummaryService
from services.watcher import Watcher
from storage.meeting_store import MeetingStore


if TYPE_CHECKING:
    from services.knowledge_base import KnowledgeBase


class MeetingAlreadyActiveError(RuntimeError):
    """Raised when start_meeting() is called while a meeting is already active."""


class MeetingStartError(RuntimeError):
    """Raised when capture/transcription fails to start — no meeting was begun."""


# Interactive-lane key shared by ALL long-form streaming prompts. The streaming
# pipeline (StreamBuffer + template state on the SSE bus) is a single shared
# slot, so long-form runs are single-flight: a second long-form prompt while
# one is streaming is rejected. Card prompts stay keyed per prompt_id.
LONGFORM_LANE_KEY = "longform"


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
        # Live streaming callbacks (DAR2-23). Interim/final callbacks receive
        # (text, speaker) where speaker is "ME", "THEM", or None.
        on_interim_transcript: Callable[[str, str | None], None] | None = None,
        on_final_transcript: Callable[[str, str | None], None] | None = None,
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

        # Component error callback (wired to the SSE "error" event by the web
        # layer) — surfaces device death / streaming failures to the UI.
        self._on_error: Callable[[str], None] | None = None

        # Backend components
        self.recorder = ContinuousRecorder(
            buffer_minutes=config.BUFFER_MINUTES,
            on_error=self._handle_component_error,
        )
        self.api_client = ApiClient()

        # Live streaming client (DAR2-23)
        self._streaming_client: DeepgramStreamingClient | None = None

        # Thread-safe state
        self._transcript_lock = threading.Lock()
        self._current_transcript: str = ""

        # Per-lane concurrency (replaces the old global _is_processing gate):
        # - watcher lane: always allowed (never touches this set)
        # - interactive lane: one in-flight request PER prompt_id — a second
        #   click of the SAME button is rejected, different buttons run
        #   concurrently
        # - background lane (title, rolling summary, map-reduce): unrestricted
        self._processing_lock = threading.Lock()
        self._interactive_inflight: set[str] = set()

        # Copilot services (session-scoped; created on meeting start)
        self._watcher: Watcher | None = None
        self._rolling_summary: RollingSummaryService | None = None
        self.context_pack: ContextPack | None = None
        # Local SAS Viya RAG knowledge base (grounds reactive/Ask/auto-answer
        # lanes). Bound by the web layer; None = RAG inactive. The proactive
        # watcher lane deliberately never consults it (latency-critical).
        self.knowledge_base: KnowledgeBase | None = None
        self._persona: str = "general"
        # F2: per-prompt model override for the proactive watcher lane. None =
        # fall back to config.WATCHER_MODEL. Set/refreshed by the web layer from
        # AppConfig.watcher_model.
        self.watcher_model: str | None = None

        # Auto-Answer (default enabled; refreshed by the web layer from AppConfig).
        self.auto_answer_enabled: bool = True
        self._auto_answer_policy = AutoAnswerPolicy()

        # Card plumbing: emitted cards by id (for dismiss), recent transcript
        # lines with monotonic timestamps (for the reactive "last ~3 min").
        self._emitted_cards: dict[str, Card] = {}
        self._recent_lines: deque[tuple[float, str]] = deque(maxlen=2000)

        # Card/watcher callbacks (Wave 3 wires these to SSE)
        self._on_card: Callable[[dict], None] | None = None
        self._on_card_dismissed: Callable[[str], None] | None = None
        self._on_watcher_status: Callable[[str], None] | None = None

        # HTML streaming state (needed by _setup_static_template flow)
        self._template_type: str | None = None

        # Meeting storage (DAR2-25)
        self._meeting_store: MeetingStore | None = None
        self._active_meeting_id: str | None = None

        # Meeting state machine (DAR2-26)
        self._meeting_state: str = "idle"  # idle | active | post_meeting
        # Serializes start_meeting / stop_meeting / reset_to_idle so two
        # concurrent transitions can never interleave (double Deepgram
        # connections, leaked timer tasks, mid-meeting transcript wipes).
        self._transition_lock = asyncio.Lock()
        self._state_change_callbacks: list[Callable[[str], None]] = []
        self._timer_callbacks: list[Callable[[int], None]] = []
        self._timer_task: asyncio.Task | None = None
        self._meeting_start_time: float | None = None
        self._last_meeting_id: int | None = None

        # Test mode: if TEST_AUDIO_TRANSCRIPT is set, use it as a fixed transcript
        # for all mid-meeting prompts (bypasses live audio transcription).
        # Set via: controller.test_transcript = "some text"
        self._test_transcript: str | None = None

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
        """True while ANY interactive-lane request is in flight (UI compat)."""
        with self._processing_lock:
            return bool(self._interactive_inflight)

    def _try_acquire_interactive(self, prompt_id: str) -> bool:
        """Claim an interactive-lane slot for prompt_id. False if already in flight."""
        with self._processing_lock:
            if prompt_id in self._interactive_inflight:
                logger.warning(
                    "Interactive request rejected: already in flight", prompt_id=prompt_id
                )
                return False
            self._interactive_inflight.add(prompt_id)
            return True

    def _release_interactive(self, prompt_id: str) -> None:
        with self._processing_lock:
            self._interactive_inflight.discard(prompt_id)

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

    @property
    def test_transcript(self) -> str | None:
        """When set, all mid-meeting run_prompt() calls use this transcript
        instead of transcribing from the audio buffer. Useful for UI testing."""
        return self._test_transcript

    @test_transcript.setter
    def test_transcript(self, value: str | None) -> None:
        self._test_transcript = value
        if value:
            # Also set as the current transcript so post-meeting features work
            with self._transcript_lock:
                self._current_transcript = value

    @property
    def on_transcription_complete(self) -> Callable[[str], None] | None:
        """Callback invoked when bounded transcription completes."""
        return self._on_transcription_complete

    @on_transcription_complete.setter
    def on_transcription_complete(self, callback: Callable[[str], None] | None) -> None:
        self._on_transcription_complete = callback

    @property
    def on_card(self) -> Callable[[dict], None] | None:
        """Callback invoked with a card dict whenever any lane emits a card."""
        return self._on_card

    @on_card.setter
    def on_card(self, callback: Callable[[dict], None] | None) -> None:
        self._on_card = callback

    @property
    def on_card_dismissed(self) -> Callable[[str], None] | None:
        """Callback invoked with the card id when a card is dismissed."""
        return self._on_card_dismissed

    @on_card_dismissed.setter
    def on_card_dismissed(self, callback: Callable[[str], None] | None) -> None:
        self._on_card_dismissed = callback

    @property
    def on_watcher_status(self) -> Callable[[str], None] | None:
        """Callback invoked with the watcher state ("watching"/"thinking"/"stopped")."""
        return self._on_watcher_status

    @on_watcher_status.setter
    def on_watcher_status(self, callback: Callable[[str], None] | None) -> None:
        self._on_watcher_status = callback

    @property
    def on_error(self) -> Callable[[str], None] | None:
        """Callback invoked with an error message on component failure."""
        return self._on_error

    @on_error.setter
    def on_error(self, callback: Callable[[str], None] | None) -> None:
        self._on_error = callback

    @property
    def on_usage(self) -> Callable[[dict], None] | None:
        """Callback invoked with {"meeting_cost_usd": float} after each LLM call."""
        return self.api_client.on_usage

    @on_usage.setter
    def on_usage(self, callback: Callable[[dict], None] | None) -> None:
        self.api_client.on_usage = callback

    @property
    def persona(self) -> str:
        """Copilot persona: "general" | "sales" | "technical"."""
        return self._persona

    @persona.setter
    def persona(self, value: str) -> None:
        from prompts.templates import PERSONAS

        self._persona = value if value in PERSONAS else "general"

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

        # Create streaming client (dual-channel: 0 = ME mic, 1 = THEM loopback)
        self._streaming_client = DeepgramStreamingClient(
            api_key=self.api_client.deepgram_api_key,
            sample_rate=config.DEEPGRAM_SAMPLE_RATE,
            channels=2,
            keyterms=config.DEEPGRAM_KEYTERMS,
            on_interim_transcript=self._handle_interim_transcript,
            on_final_transcript=self._on_final_transcript_with_storage,
            on_utterance_end=self._handle_utterance_end,
            on_error=self._on_streaming_error,
        )
        self._streaming_client.connect()

        if not self._streaming_client.is_connected:
            logger.error("Failed to establish Deepgram WebSocket connection")
            # Release any worker threads started during the failed connect
            self._streaming_client.disconnect()
            self._streaming_client = None
            return False

        # Start recording if not already. A recorder that refuses to start
        # (no audio devices) is a start FAILURE — never report a live session
        # that captures nothing.
        if not self.recorder.is_recording and not self.start_recording():
            logger.error("Recorder failed to start — aborting streaming start")
            self._streaming_client.disconnect()
            self._streaming_client = None
            return False

        # Wire the recorder's chunk consumer to forward audio to the streaming client
        self.recorder.add_chunk_consumer(self._on_recorder_chunk)

        # Create meeting record if storage is available
        if self._meeting_store is not None:
            self._active_meeting_id = self._meeting_store.start_meeting()

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

        # Unhook the chunk consumer
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
        """Forward int16 (frames, 2) chunks from the recorder to Deepgram."""
        if self._streaming_client is not None:
            self._streaming_client.send_audio(audio_chunk)

    def _handle_utterance_end(self, full_transcript: str) -> None:
        """Handle utterance end — update current transcript and tick the watcher."""
        self.current_transcript = full_transcript
        if self._watcher is not None:
            self._watcher.on_utterance_end(full_transcript)
        if self._on_utterance_end:
            self._on_utterance_end(full_transcript)

    def _on_streaming_error(self, error: str) -> None:
        """Handle streaming errors — log AND surface to the UI."""
        self._handle_component_error(f"Live transcription error: {error}")

    def _handle_component_error(self, message: str) -> None:
        """Forward a component failure (recorder/streaming) to the UI layer."""
        logger.error("Component error", message=message)
        if self._on_error is not None:
            try:
                self._on_error(message)
            except Exception as e:  # noqa: BLE001 — a bad consumer never kills a lane
                logger.warning("on_error callback failed: {}", e)

    def _handle_meeting_segment(self, text: str) -> None:
        """Append a final transcript segment to the active meeting."""
        if self._meeting_store is not None and self._active_meeting_id is not None:
            self._meeting_store.append_segment(self._active_meeting_id, text)

    def _handle_interim_transcript(self, text: str, speaker: str | None) -> None:
        """Forward interim transcripts (with speaker attribution) to the UI."""
        if self._on_interim_transcript:
            self._on_interim_transcript(text, speaker)

    def _on_final_transcript_with_storage(self, text: str, speaker: str | None) -> None:
        """Handle final transcript: store speaker-prefixed segment AND notify UI."""
        line = f"{speaker}: {text}" if speaker else text
        self._handle_meeting_segment(line)
        self._recent_lines.append((time.monotonic(), line))
        if self._on_final_transcript:
            self._on_final_transcript(text, speaker)

    def _recent_transcript(self, seconds: float = 180.0) -> str:
        """Verbatim transcript lines from the last N seconds (reactive context)."""
        cutoff = time.monotonic() - seconds
        lines = [line for ts, line in list(self._recent_lines) if ts >= cutoff]
        return "\n".join(lines)

    # ------------------------------------------------------------------
    # Meeting lifecycle (DAR2-26)
    # ------------------------------------------------------------------

    @property
    def meeting_state(self) -> str:
        """Current meeting state: 'idle', 'active', or 'post_meeting'."""
        return self._meeting_state

    @property
    def elapsed_seconds(self) -> int:
        """Elapsed meeting time in seconds (0 if not active)."""
        if self._meeting_start_time is None:
            return 0
        return int(time.monotonic() - self._meeting_start_time)

    async def start_meeting(self) -> None:
        """Begin a meeting session.

        Capture is SESSION-SCOPED: the recorder and the Deepgram stream both
        start here (nothing records at app boot). The stale transcript from a
        previous meeting is cleared first. Blocking connect work runs in a
        worker thread so the event loop stays responsive.

        Raises:
            MeetingAlreadyActiveError: A meeting is already active (the route
                maps this to HTTP 409). Guards against double-start races.
            MeetingStartError: Capture/transcription failed to start; the app
                stays in its previous state and NO false "active" is emitted.
        """
        async with self._transition_lock:
            if self._meeting_state == "active":
                logger.warning("start_meeting rejected: a meeting is already active")
                raise MeetingAlreadyActiveError("A meeting is already active")

            self.current_transcript = ""  # never answer about a previous meeting
            self._recent_lines.clear()
            self._emitted_cards.clear()
            self.api_client.reset_meeting_cost()

            started = await asyncio.to_thread(self.start_streaming)
            if not started:
                # Tear down anything partially started; stay OUT of "active" so
                # the UI never shows a live REC indicator over a dead session.
                await asyncio.to_thread(self._teardown_failed_start)
                self._handle_component_error(
                    "Failed to start capture/transcription — meeting not started"
                )
                raise MeetingStartError("Failed to start capture/transcription")

            # Context-pack file reads + thread starts are blocking — off-loop.
            await asyncio.to_thread(self._start_copilot_services)

            if self._timer_task is not None:  # never leak a previous timer task
                self._timer_task.cancel()
            self._meeting_state = "active"
            self._meeting_start_time = time.monotonic()
            self._timer_task = asyncio.create_task(self._run_timer())
            self._emit_state_change("active")

    def _teardown_failed_start(self) -> None:
        """Best-effort cleanup after a failed start_streaming() (blocking)."""
        # start_streaming() cleans up its own client on failure; only a
        # dangling recorder can be left behind here.
        if self._streaming_client is not None and not self._streaming_client.is_connected:
            self.stop_streaming()
        if self.recorder.is_recording:
            self.stop_recording()

    def _start_copilot_services(self) -> None:
        """Create and start the watcher + rolling summary for this session."""
        context_text = self.context_pack.as_text() if self.context_pack is not None else ""

        self._watcher = Watcher(
            self.api_client,
            persona=self._persona,
            context_pack_text=context_text,
            on_card=self._emit_card,
            on_status=self._emit_watcher_status,
            model=self.watcher_model or config.WATCHER_MODEL,
        )
        self._watcher.start()

        self._rolling_summary = RollingSummaryService(
            self.api_client,
            get_transcript=lambda: self.current_transcript,
            on_update=self._persist_rolling_summary,
        )
        self._rolling_summary.start()

    def _stop_copilot_services(self) -> None:
        """Stop the watcher + rolling summary (blocking joins, run off-loop)."""
        if self._watcher is not None:
            self._watcher.stop()
            self._watcher = None
        if self._rolling_summary is not None:
            self._rolling_summary.stop()
            self._rolling_summary = None

    def _persist_rolling_summary(self, summary: str) -> None:
        """Persist the rolling summary per-meeting via the meeting store."""
        if self._meeting_store is not None and self._active_meeting_id is not None:
            try:
                self._meeting_store.save_analysis(
                    self._active_meeting_id, "rolling_summary", summary
                )
            except Exception as e:  # noqa: BLE001 — background lane must never die
                logger.warning("Failed to persist rolling summary: {}", e)

    async def stop_meeting(self) -> None:
        """End the meeting session: stop streaming AND the recorder."""
        async with self._transition_lock:
            await self._cancel_timer_task()

            self._last_meeting_id = self._active_meeting_id  # preserve for post-meeting
            completed_id = self._active_meeting_id
            await asyncio.to_thread(self._stop_copilot_services)
            await asyncio.to_thread(self.stop_streaming)
            if self.recorder.is_recording:
                await asyncio.to_thread(self.stop_recording)
            self._meeting_state = "post_meeting"
            self._emit_state_change("post_meeting")
        if completed_id is not None:
            threading.Thread(
                target=self._generate_title_thread,
                args=(completed_id,),
                daemon=True,
            ).start()

    async def _cancel_timer_task(self) -> None:
        if self._timer_task is not None:
            self._timer_task.cancel()
            try:
                await self._timer_task
            except asyncio.CancelledError:
                pass
            self._timer_task = None

    def _generate_title_thread(self, meeting_id: str) -> None:
        """Background: generate a short title for a completed meeting via Claude."""
        from prompts.templates import MEETING_TITLE_PROMPT

        try:
            if self._meeting_store is None:
                return
            transcript = self._meeting_store.get_full_transcript(meeting_id)
            if not transcript or len(transcript.split()) < 10:
                return
            title = self.api_client.process_with_anthropic(
                transcript[:8000],  # cap length
                MEETING_TITLE_PROMPT,
                stream=False,
                callback=None,
                model=config.WATCHER_MODEL,
                max_tokens=config.TITLE_MAX_TOKENS,
                lane="background",
                cache_transcript=False,  # one-shot call — never re-read
            )
            title = title.strip().strip('"').strip("'")
            if title:
                self._meeting_store.save_title(meeting_id, title)
                logger.info("Meeting title generated", meeting_id=meeting_id, title=title)
        except Exception as e:  # noqa: BLE001
            logger.warning("Title generation failed: {}", e)

    async def reset_to_idle(self) -> None:
        """Return to idle state (clears the stale meeting transcript).

        Mirrors stop_meeting(): the timer task is cancelled and any live
        capture is fully stopped, so a /reset during an active meeting can
        never leave the recorder or the Deepgram socket running behind an
        "Idle" UI (silent-recording privacy bug).
        """
        async with self._transition_lock:
            await self._cancel_timer_task()
            await asyncio.to_thread(self._stop_copilot_services)
            if self._streaming_client is not None:
                await asyncio.to_thread(self.stop_streaming)
            if self.recorder.is_recording:
                await asyncio.to_thread(self.stop_recording)
            self._meeting_state = "idle"
            self._meeting_start_time = None
            self._last_meeting_id = None
            self.current_transcript = ""  # stale-transcript bug fix
            self._recent_lines.clear()
            self._emitted_cards.clear()
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

    def get_saved_analyses(self) -> dict[str, str]:
        """Return {prompt_id: output_text} for the current/last meeting.

        Returns an empty dict if no meeting store is set or no meeting ID is
        available.
        """
        meeting_id = self._last_meeting_id or self._active_meeting_id
        if self._meeting_store is None or meeting_id is None:
            return {}
        return self._meeting_store.list_analyses_for_meeting(meeting_id)

    def run_post_meeting_prompt(
        self,
        prompt_config: object,
        *,
        from_minute: int | None = None,
        to_minute: int | None = None,
        on_template_setup: Callable[[str], str | None] | None = None,
        on_complete: Callable[[str, str], None] | None = None,
    ) -> bool:
        """Run a post-meeting prompt against the stored meeting transcript.

        Retrieves the full (or segment-filtered) transcript from SQLite, sends
        it to Claude for streaming analysis, saves the result to
        ``meeting_analyses``, and invokes ``on_complete`` when done.

        Long-form streaming is SINGLE-FLIGHT (shared ``LONGFORM_LANE_KEY``):
        the SSE StreamBuffer/template state is one shared slot, so a second
        long-form prompt while one is streaming is rejected (returns False and
        the route maps it to HTTP 409).

        Args:
            prompt_config: A ``PromptConfig`` from ``PROMPT_REGISTRY``.
            from_minute: Start of transcript window in minutes (None = start).
            to_minute: End of transcript window in minutes (None = end).
            on_template_setup: UI callback to configure the output panel
                template. Receives the prompt template string; returns the
                template_type string or None.
            on_complete: Called with ``(prompt_id, output_text)`` after the
                result is saved to SQLite.

        Returns:
            True if the request was accepted.
        """
        prompt_id = getattr(prompt_config, "id", "post_meeting")
        if not self._try_acquire_interactive(LONGFORM_LANE_KEY):
            logger.warning(
                "Long-form prompt rejected: another analysis is streaming",
                prompt_id=prompt_id,
            )
            return False

        if self._on_progress:
            self._on_progress("Retrieving transcript...")

        threading.Thread(
            target=self._run_post_meeting_thread,
            args=(prompt_config, from_minute, to_minute, on_template_setup, on_complete),
            daemon=True,
        ).start()
        return True

    def _run_post_meeting_thread(
        self,
        prompt_config: object,
        from_minute: int | None,
        to_minute: int | None,
        on_template_setup: Callable[[str], str | None] | None,
        on_complete: Callable[[str, str], None] | None,
    ) -> None:
        """Background thread: retrieve transcript and run post-meeting prompt."""
        start_time = time.perf_counter()
        prompt_id = getattr(prompt_config, "id", "post_meeting")

        try:
            meeting_id = self._last_meeting_id or self._active_meeting_id
            if self._meeting_store is None or meeting_id is None:
                logger.error("Post-meeting prompt: no meeting available")
                if self._on_processing_complete:
                    self._on_processing_complete(
                        {"error": "No meeting available", "prompt_id": prompt_id}
                    )
                return

            # Retrieve transcript (full or segment range)
            if from_minute is not None and to_minute is not None:
                transcript = self._meeting_store.get_transcript_segment_range(
                    meeting_id, from_minute, to_minute
                )
                logger.info(
                    "Post-meeting transcript segment retrieved",
                    meeting_id=meeting_id,
                    from_minute=from_minute,
                    to_minute=to_minute,
                    length=len(transcript),
                )
            else:
                if (from_minute is None) != (to_minute is None):
                    logger.warning(
                        "Segment range requires both from_minute and to_minute"
                        " — falling back to full transcript",
                        from_minute=from_minute,
                        to_minute=to_minute,
                    )
                transcript = self._meeting_store.get_full_transcript(meeting_id)
                logger.info(
                    "Post-meeting full transcript retrieved",
                    meeting_id=meeting_id,
                    length=len(transcript),
                )

            if not transcript.strip():
                logger.warning("Post-meeting prompt: transcript is empty")
                if self._on_processing_complete:
                    self._on_processing_complete(
                        {"error": "No transcript available", "prompt_id": prompt_id}
                    )
                return

            # Context window handling: rough word-to-token estimate
            token_estimate = len(transcript.split()) * 1.3
            token_limit = 150_000

            if token_estimate > token_limit:
                logger.info(
                    "Transcript exceeds context window — applying map-reduce",
                    token_estimate=int(token_estimate),
                )
                if self._on_progress:
                    self._on_progress(
                        "Transcript exceeds context window — summarizing in sections first..."
                    )
                transcript = self._map_reduce_transcript(transcript)

            if self._on_progress:
                self._on_progress("Processing with Claude...")

            # Set up output panel template
            template_type = None
            if on_template_setup:
                template_type = on_template_setup(prompt_config.template)  # type: ignore[attr-defined]

            self._template_type = template_type

            # Collect full output for persistence
            output_chunks: list[str] = []

            def handle_stream(text: str) -> None:
                output_chunks.append(text)
                if self._on_stream_chunk:
                    self._on_stream_chunk(text)

            result = self.api_client.process_with_anthropic(
                transcript,
                prompt_config.template,  # type: ignore[attr-defined]
                stream=True,
                callback=handle_stream,
                model=getattr(prompt_config, "model", None),
                max_tokens=getattr(prompt_config, "max_tokens", None),
                context_pack_text=(
                    self.context_pack.as_text() if self.context_pack is not None else None
                ),
                lane="interactive",
                web_search=getattr(prompt_config, "web_search", False),
            )

            output_text = "".join(output_chunks) or str(result)

            duration_ms = (time.perf_counter() - start_time) * 1000
            logger.info(
                "Post-meeting LLM processing complete",
                prompt_id=prompt_config.id,  # type: ignore[attr-defined]
                duration_ms=f"{duration_ms:.2f}",
                output_length=len(output_text),
            )

            # Persist result to SQLite
            self._meeting_store.save_analysis(
                meeting_id,
                prompt_config.id,  # type: ignore[attr-defined]
                output_text,
            )

            if self._on_processing_complete:
                self._on_processing_complete({"result": result, "prompt_id": prompt_id})

            if on_complete:
                on_complete(prompt_config.id, output_text)  # type: ignore[attr-defined]

        except Exception as e:
            duration_ms = (time.perf_counter() - start_time) * 1000
            logger.error(
                "Post-meeting prompt failed",
                error=str(e),
                duration_ms=f"{duration_ms:.2f}",
                exc_info=True,
            )
            if self._on_processing_complete:
                self._on_processing_complete({"error": str(e), "prompt_id": prompt_id})
        finally:
            self._release_interactive(LONGFORM_LANE_KEY)

    def _map_reduce_transcript(self, transcript: str) -> str:
        """Summarize a very long transcript in chunks before final analysis.

        Splits the transcript into overlapping 30,000-token chunks, summarizes
        each chunk CONCURRENTLY on the watcher model (background lane), then
        returns the concatenated summaries for use as the analysis input.

        This path is only triggered for transcripts estimated to exceed 150,000
        tokens (roughly 11+ hours of continuous speech).
        """
        chunk_words = 23_000  # ~30k tokens at 1.3 tokens/word
        overlap_words = 1_500  # ~2k tokens overlap between chunks

        summarize_prompt = (
            "Summarize the key points, decisions, and action items from the "
            "transcript segment in concise bullet points.\n\n{transcript}"
        )

        words = transcript.split()
        chunks: list[str] = []
        start = 0

        while start < len(words):
            end = min(start + chunk_words, len(words))
            chunks.append(" ".join(words[start:end]))
            if end >= len(words):
                break
            start = end - overlap_words

        logger.info("Map-reduce: summarizing chunks concurrently", chunk_count=len(chunks))

        def summarize(chunk: str) -> str:
            return str(
                self.api_client.process_with_anthropic(
                    chunk,
                    summarize_prompt,
                    stream=False,
                    callback=None,
                    model=config.WATCHER_MODEL,
                    lane="background",
                    # Each unique chunk is sent exactly once — a cache write
                    # here is a pure 1.25x premium with zero possible reads.
                    cache_transcript=False,
                )
            )

        with ThreadPoolExecutor(max_workers=4) as pool:
            summaries = list(pool.map(summarize, chunks))

        return "\n\n".join(summaries)

    # ------------------------------------------------------------------
    # Prompt execution
    # ------------------------------------------------------------------

    def ask_question(
        self,
        question: str,
        *,
        on_template_setup: Callable[[str], str | None] | None = None,  # noqa: ARG002 — kept for API compat; cards need no scaffold
        on_complete: Callable[[], None] | None = None,
        historical_transcript: str | None = None,
    ) -> bool:
        """Run a freeform question through the reactive card lane.

        If historical_transcript is provided (meeting-history Q&A), it replaces
        the live context of [rolling summary + last ~3 minutes verbatim].

        Returns:
            True if the request was accepted (False when an 'ask' is already
            in flight — the route maps this to HTTP 409).
        """
        from prompts.registry import ASK_PROMPT_CONFIG

        return self.run_reactive_prompt(
            ASK_PROMPT_CONFIG,
            question=question,
            transcript_override=historical_transcript,
            on_complete=on_complete,
        )

    def run_reactive_prompt(
        self,
        prompt_config: object,
        *,
        question: str | None = None,
        transcript_override: str | None = None,
        on_complete: Callable[[], None] | None = None,
        trigger_override: str | None = None,
        discard_if_inactive: bool = False,
    ) -> bool:
        """Run a reactive card prompt (built-in buttons / Ask / custom prompts).

        Interactive lane: one in-flight request per prompt_id — a second click
        of the SAME button is rejected; different buttons run concurrently.
        Context = [rolling summary (~300 tokens)] + [last ~3 minutes verbatim],
        never the full transcript. Cards are emitted via the on_card callback.

        Returns True if the request was accepted.
        """
        prompt_id = getattr(prompt_config, "id", "reactive")
        if not self._try_acquire_interactive(prompt_id):
            return False

        threading.Thread(
            target=self._run_reactive_thread,
            args=(prompt_config, question, transcript_override, on_complete),
            kwargs={
                "trigger_override": trigger_override,
                "discard_if_inactive": discard_if_inactive,
            },
            daemon=True,
        ).start()
        return True

    def _run_reactive_thread(
        self,
        prompt_config: object,
        question: str | None,
        transcript_override: str | None,
        on_complete: Callable[[], None] | None,
        *,
        trigger_override: str | None = None,
        discard_if_inactive: bool = False,
    ) -> None:
        """Background thread: build reactive context, force emit_cards, emit."""
        from prompts.templates import REACTIVE_SYSTEM_PROMPT, persona_line

        prompt_id = getattr(prompt_config, "id", "reactive")
        start_time = time.perf_counter()
        try:
            instruction = prompt_config.template  # type: ignore[attr-defined]
            if question is not None:
                instruction = instruction.replace("{question}", question)

            # Context blocks: [rolling summary] + [last ~3 min verbatim]
            blocks: list[str] = []
            if transcript_override is not None:
                blocks.append(f"Meeting transcript:\n{transcript_override}")
            else:
                # Snapshot: _stop_copilot_services (another thread) can null
                # self._rolling_summary between the check and the access.
                rolling_summary = self._rolling_summary
                if rolling_summary is not None and rolling_summary.summary:
                    blocks.append(
                        "Rolling summary of the meeting so far:\n" + rolling_summary.summary
                    )
                recent = self._recent_transcript(180.0) or self.current_transcript[-6000:]
                if recent.strip():
                    blocks.append(f"Most recent transcript (last ~3 minutes):\n{recent}")

            # RAG grounding: retrieved chunks change every query, so they go in
            # the per-request transcript blocks (never the cached system block).
            # A KB failure must never break the reactive run — fall back to an
            # ungrounded answer. The watcher lane never reaches this path.
            kb = self.knowledge_base
            if kb and kb.enabled and not kb.is_empty and getattr(prompt_config, "use_rag", True):
                try:
                    kb_query = question if question is not None else (
                        self._recent_transcript(60.0) or ""
                    )
                    hits = kb.search(kb_query, k=config.KB_TOP_K)
                    if hits:
                        blocks.append(kb.format_for_prompt(hits))
                except Exception as e:
                    logger.warning("RAG retrieval failed; continuing ungrounded", error=str(e))

            if not any(b.strip() for b in blocks):
                if self._on_processing_complete:
                    self._on_processing_complete(
                        {"error": "No transcript available", "prompt_id": prompt_id}
                    )
                return

            system_text = f"{REACTIVE_SYSTEM_PROMPT}\n\n{persona_line(self._persona)}"
            context_text = self.context_pack.as_text() if self.context_pack is not None else None
            system = build_system_blocks(system_text, context_text)
            # Reactive context churns every request — don't waste cache writes on it.
            messages = build_transcript_messages(blocks, instruction, cache_transcript=False)

            cards = self.api_client.create_cards(
                lane="reactive",
                model=getattr(prompt_config, "model", config.REACTIVE_MODEL),
                max_tokens=getattr(prompt_config, "max_tokens", config.REACTIVE_MAX_TOKENS),
                system=system,
                messages=messages,
                web_search=getattr(prompt_config, "web_search", False),
            )

            duration_ms = (time.perf_counter() - start_time) * 1000
            logger.info(
                "Reactive prompt complete",
                prompt_id=prompt_id,
                card_count=len(cards),
                duration_ms=f"{duration_ms:.2f}",
            )

            if trigger_override is not None:
                for card in cards:
                    card.trigger = trigger_override

            # Late-completion guard (mirrors watcher.py post-stop discard): an
            # auto-answer that finished after the meeting ended must not surface.
            if discard_if_inactive and self._meeting_state != "active":
                logger.info("Auto-answer finished after meeting end — discarded")
                return

            for card in cards:
                self._emit_card(card)
            if self._on_processing_complete:
                self._on_processing_complete(
                    {"cards": [c.to_dict() for c in cards], "prompt_id": prompt_id}
                )
        except Exception as e:
            duration_ms = (time.perf_counter() - start_time) * 1000
            logger.error(
                "Reactive prompt failed",
                prompt_id=prompt_id,
                error=str(e),
                duration_ms=f"{duration_ms:.2f}",
                exc_info=True,
            )
            if self._on_processing_complete:
                self._on_processing_complete({"error": str(e), "prompt_id": prompt_id})
        finally:
            # Guarantee the auto-answer in-flight guard is released on every exit
            # path (no-transcript return, discard, success, or exception); the
            # try body no longer calls on_complete so this fires exactly once.
            if on_complete:
                on_complete()
            self._release_interactive(prompt_id)

    # ------------------------------------------------------------------
    # Card plumbing
    # ------------------------------------------------------------------

    def _emit_card(self, card: Card) -> None:
        """Register an emitted card (for dismissal), persist it, notify the UI."""
        self._emitted_cards[card.id] = card
        card_dict = card.to_dict()
        self._persist_card(card_dict)
        if self._on_card:
            try:
                self._on_card(card_dict)
            except Exception as e:  # noqa: BLE001 — a bad consumer never kills a lane
                logger.warning("on_card callback failed: {}", e)

        # Auto-Answer: a watcher card asking the user a question auto-triggers
        # the reactive answer_this pipeline (non-blocking).
        if card.trigger == "question_at_user":
            self._maybe_auto_answer(card)

    def _maybe_auto_answer(self, source_card: Card) -> None:
        """Kick off an auto-answer for a watcher question card, if gated in."""
        allowed, reason = self._auto_answer_policy.should_answer(
            enabled=self.auto_answer_enabled,
            trigger=source_card.trigger,
            meeting_active=self._meeting_state == "active",
            source_card_id=source_card.id,
        )
        if not allowed:
            logger.info("Auto-answer skipped", reason=reason, source_card_id=source_card.id)
            return

        from prompts.registry import get_prompt_config_by_id

        answer_cfg = get_prompt_config_by_id("answer_this")
        if answer_cfg is None:
            logger.warning("Auto-answer: answer_this prompt not found")
            return

        self._auto_answer_policy.note_started(source_card.id)

        def _release() -> None:
            self._auto_answer_policy.note_finished(source_card.id)

        accepted = self.run_reactive_prompt(
            answer_cfg,
            trigger_override=AUTO_ANSWER_TRIGGER,
            discard_if_inactive=True,
            on_complete=_release,
        )
        if accepted:
            self._auto_answer_policy.note_accepted()
        else:
            # answer_this already in flight (manual click) — release the source
            # guard so a later watcher card can retry. Cooldown stays unarmed:
            # nothing ran.
            self._auto_answer_policy.note_finished(source_card.id)
            logger.info("Auto-answer not started: answer_this already in flight")

    def _persist_card(self, card_dict: dict) -> None:
        """Append a rendered card (both lanes) to the meeting's cards.jsonl (F4)."""
        store = self._meeting_store
        # Reactive cards can be generated during the post_meeting state (buttons
        # stay enabled), when _active_meeting_id has already moved to
        # _last_meeting_id — resolve the same way the reactive lane resolves its
        # transcript so post-meeting cards still land in the meeting's cards.jsonl.
        meeting_id = self._active_meeting_id or self._last_meeting_id
        if store is None or meeting_id is None:
            return
        try:
            store.append_card(meeting_id, card_dict)
        except Exception as e:  # noqa: BLE001 — persistence must never kill a lane
            logger.warning("Failed to persist card: {}", e)

    def _emit_watcher_status(self, state: str) -> None:
        if self._on_watcher_status:
            try:
                self._on_watcher_status(state)
            except Exception as e:  # noqa: BLE001
                logger.warning("on_watcher_status callback failed: {}", e)

    def dismiss_card(self, card_id: str) -> bool:
        """Dismiss a card: suppress its topic for the meeting, notify the UI.

        Returns True if the card was found.
        """
        card = self._emitted_cards.get(card_id)
        if card is None:
            logger.warning("Dismiss requested for unknown card", card_id=card_id)
            return False
        if self._watcher is not None and card.topic_key:
            self._watcher.dismiss_topic(card.topic_key)
        logger.info("Card dismissed", card_id=card_id, topic_key=card.topic_key)
        if self._on_card_dismissed:
            try:
                self._on_card_dismissed(card_id)
            except Exception as e:  # noqa: BLE001
                logger.warning("on_card_dismissed callback failed: {}", e)
        return True

    def run_prompt(
        self,
        prompt_template: str,
        title: str | None = None,
        *,
        prompt_id: str | None = None,
        model: str | None = None,
        max_tokens: int | None = None,
        web_search: bool = False,
        on_template_setup: Callable[[str], str | None] | None = None,
        on_complete: Callable[[], None] | None = None,
    ) -> bool:
        """Run a legacy long-form prompt against the current transcript.

        Kept for the post-meeting/streaming path and backwards compatibility.
        Long-form streaming is SINGLE-FLIGHT (shared ``LONGFORM_LANE_KEY``):
        the SSE StreamBuffer/template state is one shared slot, so a second
        long-form prompt while one is streaming is rejected.

        Args:
            prompt_template: The prompt template string with {transcript} placeholder.
            title: Display title for the output.
            prompt_id: Prompt id carried into processing_complete payloads.
            model: Per-prompt model override (default POST_MEETING_MODEL).
            max_tokens: Per-prompt output cap (default POST_MEETING_MAX_TOKENS).
            web_search: Attach Anthropic server-side web search on Anthropic
                        models (F3); ignored with a warning on openai_compat.
            on_template_setup: UI callback to set up the static HTML template.
                              Receives prompt_template, returns template_type string.
                              Called from the background thread — UI layer must marshal.

        Returns:
            True if the request was accepted.
        """
        if not self._try_acquire_interactive(LONGFORM_LANE_KEY):
            logger.warning(
                "Long-form prompt rejected: another analysis is streaming",
                prompt_id=prompt_id,
            )
            return False

        if self._on_progress:
            self._on_progress("Capturing audio and transcribing...")

        thread_kwargs = {
            "release_key": LONGFORM_LANE_KEY,
            "prompt_id": prompt_id,
            "model": model,
            "max_tokens": max_tokens,
            "web_search": web_search,
        }

        # Test mode: bypass audio capture and use fixed transcript
        if self._test_transcript:
            threading.Thread(
                target=self._run_prompt_thread,
                args=(self._test_transcript, prompt_template, on_template_setup, on_complete),
                kwargs=thread_kwargs,
                daemon=True,
            ).start()
            return True

        # Check for existing transcript
        with self._transcript_lock:
            has_transcript = bool(self._current_transcript)
            transcript_copy = self._current_transcript if has_transcript else None

        if has_transcript:
            threading.Thread(
                target=self._run_prompt_thread,
                args=(transcript_copy, prompt_template, on_template_setup, on_complete),
                kwargs=thread_kwargs,
                daemon=True,
            ).start()
            return True

        # No transcript — transcribe the rolling buffer first
        audio_data = self.recorder.save_buffer()

        if audio_data is None:
            logger.warning("Processing failed: No audio in buffer")
            self._release_interactive(LONGFORM_LANE_KEY)
            if self._on_processing_complete:
                self._on_processing_complete(
                    {"error": "No audio in buffer to process", "prompt_id": prompt_id}
                )
            return True

        threading.Thread(
            target=self._transcribe_and_process_thread,
            args=(
                audio_data,
                self.recorder.sample_rate,
                prompt_template,
                on_template_setup,
                on_complete,
            ),
            kwargs=thread_kwargs,
            daemon=True,
        ).start()
        return True

    def _transcribe_and_process_thread(
        self,
        audio_data: object,
        sample_rate: int,
        prompt_template: str,
        on_template_setup: Callable[[str], str | None] | None,
        on_complete: Callable[[], None] | None = None,
        *,
        release_key: str | None = None,
        prompt_id: str | None = None,
        model: str | None = None,
        max_tokens: int | None = None,
        web_search: bool = False,
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

            if not text.strip():
                logger.warning("Transcription returned empty text — skipping prompt execution")
                if self._on_processing_complete:
                    self._on_processing_complete(
                        {"error": "Transcription returned empty text", "prompt_id": prompt_id}
                    )
                return

            self._run_prompt_thread(
                text,
                prompt_template,
                on_template_setup,
                on_complete,
                prompt_id=prompt_id,
                model=model,
                max_tokens=max_tokens,
                web_search=web_search,
            )

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
                self._on_processing_complete({"error": str(e), "prompt_id": prompt_id})
        finally:
            if release_key is not None:
                self._release_interactive(release_key)

    def _run_prompt_thread(
        self,
        transcript: str,
        prompt_template: str,
        on_template_setup: Callable[[str], str | None] | None,
        on_complete: Callable[[], None] | None = None,
        *,
        release_key: str | None = None,
        prompt_id: str | None = None,
        model: str | None = None,
        max_tokens: int | None = None,
        web_search: bool = False,
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
                transcript,
                prompt_template,
                stream=True,
                callback=handle_stream,
                model=model,
                max_tokens=max_tokens,
                context_pack_text=(
                    self.context_pack.as_text() if self.context_pack is not None else None
                ),
                lane="interactive",
                web_search=web_search,
            )
            duration_ms = (time.perf_counter() - start_time) * 1000
            logger.info(
                "LLM processing complete",
                template_type=template_type,
                duration_ms=f"{duration_ms:.2f}",
                result_length=len(str(result)),
            )

            if self._on_processing_complete:
                self._on_processing_complete({"result": result, "prompt_id": prompt_id})
            if on_complete:
                on_complete()
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
                self._on_processing_complete({"error": str(e), "prompt_id": prompt_id})
        finally:
            if release_key is not None:
                self._release_interactive(release_key)
