"""Tests for MeetingControls component (DAR2-26)."""

from __future__ import annotations

from unittest.mock import MagicMock, patch


class TestMeetingControlsState:
    """Test visibility state transitions."""

    def test_idle_state_shows_start_button(self) -> None:
        with patch("ui.components.meeting_controls.ui"):
            from ui.components.meeting_controls import MeetingControls

            ctrl = MeetingControls(MagicMock())
            ctrl._start_btn = MagicMock()
            ctrl._stop_btn = MagicMock()
            ctrl._new_btn = MagicMock()
            ctrl._timer_row = MagicMock()
            ctrl._indicator = MagicMock()

            ctrl.set_state("idle")

            ctrl._start_btn.set_visibility.assert_called_with(True)
            ctrl._stop_btn.set_visibility.assert_called_with(False)
            ctrl._new_btn.set_visibility.assert_called_with(False)
            ctrl._timer_row.set_visibility.assert_called_with(False)

    def test_active_state_shows_stop_button(self) -> None:
        with patch("ui.components.meeting_controls.ui"):
            from ui.components.meeting_controls import MeetingControls

            ctrl = MeetingControls(MagicMock())
            ctrl._start_btn = MagicMock()
            ctrl._stop_btn = MagicMock()
            ctrl._new_btn = MagicMock()
            ctrl._timer_row = MagicMock()
            ctrl._indicator = MagicMock()

            ctrl.set_state("active")

            ctrl._start_btn.set_visibility.assert_called_with(False)
            ctrl._stop_btn.set_visibility.assert_called_with(True)
            ctrl._new_btn.set_visibility.assert_called_with(False)
            ctrl._timer_row.set_visibility.assert_called_with(True)

    def test_post_meeting_shows_new_button(self) -> None:
        with patch("ui.components.meeting_controls.ui"):
            from ui.components.meeting_controls import MeetingControls

            ctrl = MeetingControls(MagicMock())
            ctrl._start_btn = MagicMock()
            ctrl._stop_btn = MagicMock()
            ctrl._new_btn = MagicMock()
            ctrl._timer_row = MagicMock()
            ctrl._indicator = MagicMock()

            ctrl.set_state("post_meeting")

            ctrl._start_btn.set_visibility.assert_called_with(False)
            ctrl._stop_btn.set_visibility.assert_called_with(False)
            ctrl._new_btn.set_visibility.assert_called_with(True)
            ctrl._timer_row.set_visibility.assert_called_with(True)


class TestTimerFormat:
    """Test timer display formatting."""

    def test_zero_seconds(self) -> None:
        with patch("ui.components.meeting_controls.ui"):
            from ui.components.meeting_controls import MeetingControls

            ctrl = MeetingControls(MagicMock())
            ctrl._timer_label = MagicMock()

            ctrl.update_timer(0)
            ctrl._timer_label.set_text.assert_called_with("00:00:00")

    def test_one_hour_one_minute_one_second(self) -> None:
        with patch("ui.components.meeting_controls.ui"):
            from ui.components.meeting_controls import MeetingControls

            ctrl = MeetingControls(MagicMock())
            ctrl._timer_label = MagicMock()

            ctrl.update_timer(3661)
            ctrl._timer_label.set_text.assert_called_with("01:01:01")

    def test_59_minutes_59_seconds(self) -> None:
        with patch("ui.components.meeting_controls.ui"):
            from ui.components.meeting_controls import MeetingControls

            ctrl = MeetingControls(MagicMock())
            ctrl._timer_label = MagicMock()

            ctrl.update_timer(3599)
            ctrl._timer_label.set_text.assert_called_with("00:59:59")
