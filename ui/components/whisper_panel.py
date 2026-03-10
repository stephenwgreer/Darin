"""Live transcript panel for whisper mode (DAR2-15).

Displays the continuously accumulating Deepgram transcript as words arrive.
Receives finalized segment text via on_whisper_transcript callback and
appends it to a scrollable text area.
"""

from __future__ import annotations

import asyncio
import functools
from collections.abc import Callable

from nicegui import ui

from app_controller import AppController


class WhisperPanel:
    """Scrollable panel showing the live whisper-mode transcript."""

    def __init__(self, controller: AppController) -> None:
        self._segments: list[str] = []
        self._loop = asyncio.get_event_loop()

        with ui.card().classes("w-full"):
            with ui.row().classes("w-full items-center justify-between"):
                ui.label("Live Transcript").classes(
                    "text-sm font-semibold text-gray-500 uppercase tracking-wide"
                )
                self._status = ui.label("● Listening").classes("text-xs text-green-500")

            with ui.scroll_area().classes("w-full h-40 border rounded") as self._scroll:
                self._content = ui.label("").classes(
                    "p-3 text-sm text-gray-700 whitespace-pre-wrap"
                )

        # Wire callback
        controller.on_whisper_transcript = self._on_segment

    def _on_segment(self, text: str) -> None:
        """Called from background thread when a finalized segment arrives."""
        self._call_on_ui_thread(self._append_segment, text)

    def _append_segment(self, text: str) -> None:
        """Append a segment to the display (must run on UI thread)."""
        self._segments.append(text)
        combined = " ".join(self._segments)
        self._content.set_text(combined)
        self._scroll.scroll_to(percent=1.0)

    def clear(self) -> None:
        """Clear the transcript display."""
        self._segments.clear()
        self._content.set_text("")

    def _call_on_ui_thread(self, fn: Callable[..., object], *args: object) -> None:
        """Schedule a UI call thread-safely onto the NiceGUI event loop."""
        if self._loop.is_running():
            self._loop.call_soon_threadsafe(functools.partial(fn, *args))
        else:
            fn(*args)
