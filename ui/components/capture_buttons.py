"""Bounded capture buttons: Last 30s, Last 1m (DAR2-26).

Always available in all states (IDLE, MEETING_ACTIVE, POST_MEETING).
Triggers AppController.transcribe_last_n_seconds() which reads from
the circular audio buffer (DAR2-24).
"""

from __future__ import annotations

from nicegui import ui


class CaptureButtons:
    """Bounded capture buttons with loading state."""

    def __init__(self, controller: object) -> None:
        self._controller = controller

        with ui.card().classes("w-full"):
            ui.label("Quick Capture").classes(
                "text-sm font-semibold text-gray-500 uppercase tracking-wide"
            )
            with ui.row().classes("gap-3"):
                self._btn_30 = ui.button(
                    "Last 30s",
                    on_click=lambda: self._capture(30),
                ).classes("bg-blue-600 text-white")

                self._btn_60 = ui.button(
                    "Last 1m",
                    on_click=lambda: self._capture(60),
                ).classes("bg-blue-600 text-white")

                self._status = ui.label("").classes("text-sm text-gray-500 self-center")

        # Register for transcription completion to re-enable buttons
        # (transcribe_last_n_seconds is non-blocking — we must wait for callback)
        if hasattr(controller, "on_transcription_complete"):
            controller.on_transcription_complete = self._on_transcription_done  # type: ignore[attr-defined]

    async def _capture(self, seconds: int) -> None:
        """Disable buttons, show status, trigger capture."""
        self._set_loading(True, seconds)
        self._controller.transcribe_last_n_seconds(seconds)  # type: ignore[attr-defined]
        # Buttons re-enabled by _on_transcription_done callback when transcription finishes

    def _on_transcription_done(self, text: str) -> None:
        """Re-enable buttons when transcription completes (called from background thread)."""
        self._set_loading(False)

    def _set_loading(self, loading: bool, seconds: int = 0) -> None:
        """Toggle button enabled state and status label."""
        self._btn_30.set_enabled(not loading)
        self._btn_60.set_enabled(not loading)
        if loading:
            self._status.set_text(f"Transcribing last {seconds}s...")
        else:
            self._status.set_text("")
