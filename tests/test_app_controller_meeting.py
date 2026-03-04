"""Tests for AppController meeting lifecycle methods (DAR2-26)."""

from __future__ import annotations

import asyncio
from unittest.mock import MagicMock, patch

import pytest

from app_controller import AppController


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
