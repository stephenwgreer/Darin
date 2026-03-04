"""Tests for CaptureButtons component (DAR2-26)."""

from __future__ import annotations

from unittest.mock import MagicMock, patch


class TestCaptureButtonsLoadingState:
    """Test button enable/disable during capture."""

    def test_buttons_disabled_during_capture(self) -> None:
        with patch("ui.components.capture_buttons.ui"):
            from ui.components.capture_buttons import CaptureButtons

            cap = CaptureButtons(MagicMock())
            cap._btn_30 = MagicMock()
            cap._btn_60 = MagicMock()
            cap._status = MagicMock()

            cap._set_loading(True, 30)

            cap._btn_30.set_enabled.assert_called_with(False)
            cap._btn_60.set_enabled.assert_called_with(False)
            cap._status.set_text.assert_called_with("Transcribing last 30s...")

    def test_buttons_reenabled_after_capture(self) -> None:
        with patch("ui.components.capture_buttons.ui"):
            from ui.components.capture_buttons import CaptureButtons

            cap = CaptureButtons(MagicMock())
            cap._btn_30 = MagicMock()
            cap._btn_60 = MagicMock()
            cap._status = MagicMock()

            cap._set_loading(False, 30)

            cap._btn_30.set_enabled.assert_called_with(True)
            cap._btn_60.set_enabled.assert_called_with(True)
            cap._status.set_text.assert_called_with("")

    def test_status_shows_correct_duration(self) -> None:
        with patch("ui.components.capture_buttons.ui"):
            from ui.components.capture_buttons import CaptureButtons

            cap = CaptureButtons(MagicMock())
            cap._btn_30 = MagicMock()
            cap._btn_60 = MagicMock()
            cap._status = MagicMock()

            cap._set_loading(True, 60)
            cap._status.set_text.assert_called_with("Transcribing last 60s...")
