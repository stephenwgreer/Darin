"""Tests for AppController meeting lifecycle methods (DAR2-26)."""

from __future__ import annotations

import asyncio
from unittest.mock import MagicMock, patch

import pytest

from app_controller import AppController, MeetingAlreadyActiveError, MeetingStartError


@pytest.fixture
def controller() -> AppController:
    """Create an AppController with mocked backend dependencies."""
    with (
        patch("app_controller.ContinuousRecorder"),
        patch("app_controller.ApiClient"),
    ):
        ctrl = AppController()

        # Set up mock meeting store
        mock_store = MagicMock()
        mock_store.start_meeting.return_value = 42
        mock_store.get_full_transcript.return_value = "Hello world transcript"
        ctrl._meeting_store = mock_store

        # Mock start_streaming / stop_streaming to avoid real audio/network
        ctrl.start_streaming = MagicMock(return_value=True)
        ctrl.stop_streaming = MagicMock(return_value="accumulated transcript")

        yield ctrl


class TestMeetingState:
    """Test meeting state machine: idle -> active -> post_meeting."""

    def test_initial_state_is_idle(self, controller: AppController) -> None:
        assert controller.meeting_state == "idle"

    def test_start_meeting_transitions_to_active(self, controller: AppController) -> None:
        loop = asyncio.new_event_loop()
        loop.run_until_complete(controller.start_meeting())
        assert controller.meeting_state == "active"
        # Clean up timer task
        if controller._timer_task:
            controller._timer_task.cancel()
        loop.close()

    def test_stop_meeting_transitions_to_post_meeting(self, controller: AppController) -> None:
        loop = asyncio.new_event_loop()
        loop.run_until_complete(controller.start_meeting())
        loop.run_until_complete(controller.stop_meeting())
        assert controller.meeting_state == "post_meeting"
        loop.close()

    def test_reset_to_idle_transitions_to_idle(self, controller: AppController) -> None:
        loop = asyncio.new_event_loop()
        loop.run_until_complete(controller.start_meeting())
        loop.run_until_complete(controller.stop_meeting())
        loop.run_until_complete(controller.reset_to_idle())
        assert controller.meeting_state == "idle"
        loop.close()

    def test_start_meeting_while_active_raises_409_error(self, controller: AppController) -> None:
        """A second start_meeting while active must be rejected, not restarted."""
        loop = asyncio.new_event_loop()
        loop.run_until_complete(controller.start_meeting())
        with pytest.raises(MeetingAlreadyActiveError):
            loop.run_until_complete(controller.start_meeting())
        # Only ONE streaming session / timer task was created
        controller.start_streaming.assert_called_once()
        loop.run_until_complete(controller.stop_meeting())
        loop.close()

    def test_failed_streaming_start_does_not_enter_active(self, controller: AppController) -> None:
        """start_streaming() failure must never produce a false 'active' state."""
        controller.start_streaming = MagicMock(return_value=False)
        states: list[str] = []
        controller.on_meeting_state_change(states.append)
        errors: list[str] = []
        controller.on_error = errors.append

        loop = asyncio.new_event_loop()
        with pytest.raises(MeetingStartError):
            loop.run_until_complete(controller.start_meeting())
        loop.close()

        assert controller.meeting_state == "idle"
        assert controller._timer_task is None
        assert states == []  # no state_change('active') was emitted
        assert errors, "an error must be surfaced to the UI"

    def test_reset_to_idle_stops_capture_while_active(self, controller: AppController) -> None:
        """/reset during an active meeting must stop streaming AND the recorder."""
        loop = asyncio.new_event_loop()
        loop.run_until_complete(controller.start_meeting())
        controller._streaming_client = MagicMock()  # simulate live stream
        loop.run_until_complete(controller.reset_to_idle())
        loop.close()

        controller.stop_streaming.assert_called_once()
        controller.recorder.stop_recording.assert_called_once()
        assert controller.meeting_state == "idle"
        assert controller._timer_task is None


class TestMeetingCallbacks:
    """Test observer callback pattern."""

    def test_start_meeting_emits_active_state(self, controller: AppController) -> None:
        callback = MagicMock()
        controller.on_meeting_state_change(callback)

        loop = asyncio.new_event_loop()
        loop.run_until_complete(controller.start_meeting())
        callback.assert_called_with("active")
        if controller._timer_task:
            controller._timer_task.cancel()
        loop.close()

    def test_stop_meeting_emits_post_meeting(self, controller: AppController) -> None:
        callback = MagicMock()
        controller.on_meeting_state_change(callback)

        loop = asyncio.new_event_loop()
        loop.run_until_complete(controller.start_meeting())
        loop.run_until_complete(controller.stop_meeting())
        callback.assert_called_with("post_meeting")
        loop.close()

    def test_reset_emits_idle(self, controller: AppController) -> None:
        callback = MagicMock()
        controller.on_meeting_state_change(callback)

        loop = asyncio.new_event_loop()
        loop.run_until_complete(controller.start_meeting())
        loop.run_until_complete(controller.stop_meeting())
        loop.run_until_complete(controller.reset_to_idle())
        callback.assert_called_with("idle")
        loop.close()


class TestTimerTick:
    """Test elapsed timer ticks."""

    def test_timer_ticks_after_start(self, controller: AppController) -> None:
        ticks: list[int] = []
        controller.on_timer_tick(lambda elapsed: ticks.append(elapsed))

        loop = asyncio.new_event_loop()
        loop.run_until_complete(controller.start_meeting())
        loop.run_until_complete(asyncio.sleep(1.5))
        loop.run_until_complete(controller.stop_meeting())
        loop.close()

        assert len(ticks) >= 1
        assert ticks[0] >= 1

    def test_timer_stops_after_stop_meeting(self, controller: AppController) -> None:
        ticks: list[int] = []
        controller.on_timer_tick(lambda elapsed: ticks.append(elapsed))

        loop = asyncio.new_event_loop()
        loop.run_until_complete(controller.start_meeting())
        loop.run_until_complete(asyncio.sleep(1.5))
        loop.run_until_complete(controller.stop_meeting())
        tick_count_at_stop = len(ticks)
        loop.run_until_complete(asyncio.sleep(1.5))
        loop.close()

        assert len(ticks) == tick_count_at_stop


class TestCopilotServiceLifecycle:
    """Watcher + rolling summary are session-scoped (start/stop with meeting)."""

    def test_start_meeting_starts_watcher_and_rolling_summary(
        self, controller: AppController
    ) -> None:
        loop = asyncio.new_event_loop()
        loop.run_until_complete(controller.start_meeting())

        assert controller._watcher is not None
        assert controller._watcher.is_running
        assert controller._rolling_summary is not None
        assert controller._rolling_summary.is_running

        loop.run_until_complete(controller.stop_meeting())
        loop.close()

    def test_watcher_model_override_propagates_to_watcher(self, controller: AppController) -> None:
        controller.watcher_model = "claude-sonnet-5"
        loop = asyncio.new_event_loop()
        loop.run_until_complete(controller.start_meeting())

        assert controller._watcher is not None
        assert controller._watcher._model == "claude-sonnet-5"

        loop.run_until_complete(controller.stop_meeting())
        loop.close()

    def test_stop_meeting_stops_watcher_and_rolling_summary(
        self, controller: AppController
    ) -> None:
        loop = asyncio.new_event_loop()
        loop.run_until_complete(controller.start_meeting())
        loop.run_until_complete(controller.stop_meeting())
        loop.close()

        assert controller._watcher is None
        assert controller._rolling_summary is None

    def test_no_copilot_services_before_meeting(self, controller: AppController) -> None:
        assert controller._watcher is None
        assert controller._rolling_summary is None

    def test_start_meeting_resets_meeting_cost(self, controller: AppController) -> None:
        reset = MagicMock()
        controller.api_client = MagicMock()
        controller.api_client.reset_meeting_cost = reset

        loop = asyncio.new_event_loop()
        loop.run_until_complete(controller.start_meeting())
        loop.run_until_complete(controller.stop_meeting())
        loop.close()

        reset.assert_called_once()

    def test_utterance_end_feeds_watcher(self, controller: AppController) -> None:
        watcher = MagicMock()
        controller._watcher = watcher

        controller._handle_utterance_end("ME: full transcript so far")

        watcher.on_utterance_end.assert_called_once_with("ME: full transcript so far")

    def test_copilot_services_not_started_when_streaming_fails(
        self, controller: AppController
    ) -> None:
        """No copilot services may start when start_streaming fails."""
        controller.start_streaming = MagicMock(return_value=False)

        loop = asyncio.new_event_loop()
        with pytest.raises(MeetingStartError):
            loop.run_until_complete(controller.start_meeting())
        loop.close()

        assert controller._watcher is None
        assert controller._rolling_summary is None


class TestGetMeetingTranscript:
    """Test transcript retrieval."""

    def test_get_meeting_transcript_returns_text(self, controller: AppController) -> None:
        # Set active_meeting_id to simulate active meeting
        controller._active_meeting_id = 42

        result = controller.get_meeting_transcript()
        assert result == "Hello world transcript"

    def test_get_meeting_transcript_returns_none_when_no_meeting(
        self, controller: AppController
    ) -> None:
        result = controller.get_meeting_transcript()
        assert result is None

    def test_get_meeting_transcript_works_in_post_meeting(self, controller: AppController) -> None:
        """After stop_meeting, _last_meeting_id should preserve access."""
        controller._active_meeting_id = 42

        loop = asyncio.new_event_loop()
        loop.run_until_complete(controller.start_meeting())
        loop.run_until_complete(controller.stop_meeting())
        loop.close()

        # _active_meeting_id is cleared by stop_streaming, but _last_meeting_id preserves it
        result = controller.get_meeting_transcript()
        assert result == "Hello world transcript"


class TestCardPersistence:
    """F4: every emitted card (both lanes) is appended to the meeting store."""

    def test_emit_card_persists_to_store(self, controller: AppController) -> None:
        from services.cards import parse_card

        controller._active_meeting_id = "2026-07-09_141323"
        card = parse_card(
            {"type": "answer", "headline": "H", "cues": ["ask pricing"]}, lane="proactive"
        )
        assert card is not None
        controller._emit_card(card)
        controller._meeting_store.append_card.assert_called_once()
        mid, card_dict = controller._meeting_store.append_card.call_args.args
        assert mid == "2026-07-09_141323"
        assert card_dict["headline"] == "H"
        assert card_dict["cues"] == ["ask pricing"]

    def test_emit_card_no_meeting_id_does_not_persist(self, controller: AppController) -> None:
        from services.cards import parse_card

        controller._active_meeting_id = None
        card = parse_card({"type": "answer", "headline": "H"}, lane="reactive")
        assert card is not None
        controller._emit_card(card)
        controller._meeting_store.append_card.assert_not_called()

    def test_emit_card_persistence_failure_does_not_raise(self, controller: AppController) -> None:
        from services.cards import parse_card

        controller._active_meeting_id = "2026-07-09_141323"
        controller._meeting_store.append_card.side_effect = OSError("disk full")
        card = parse_card({"type": "answer", "headline": "H"}, lane="reactive")
        assert card is not None
        # Must not raise — persistence failure never kills a lane.
        controller._emit_card(card)
