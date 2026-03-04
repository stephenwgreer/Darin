"""Claude analysis results display (DAR2-26).

This panel shows ONLY Claude analysis output — never raw transcript.
Results arrive from bounded capture buttons and prompt buttons.
Supports streaming: chunks arrive via on_stream_chunk callback.
"""

from __future__ import annotations

from nicegui import ui


class OutputPanel:
    """Claude analysis results display with streaming support."""

    def __init__(self, controller: object) -> None:
        with ui.card().classes("w-full"):
            ui.label("Analysis Output").classes(
                "text-sm font-semibold text-gray-500 uppercase tracking-wide"
            )
            with ui.scroll_area().classes("w-full h-96 border rounded") as self._scroll:
                self._content = ui.html("").classes("prose max-w-none p-3")

        # Wire callbacks on controller
        controller.on_stream_chunk = lambda chunk: self._append_chunk(chunk)  # type: ignore[attr-defined]
        controller.on_processing_complete = lambda result: self._finalize(result)  # type: ignore[attr-defined]

    def _append_chunk(self, chunk: str) -> None:
        """Append streaming chunk to output."""
        current = self._content.content or ""
        self._content.set_content(current + chunk)
        self._scroll.scroll_to(percent=1.0)

    def _finalize(self, result: dict) -> None:
        """Called when streaming is complete."""
        if "result" in result:
            self._content.set_content(result["result"])
        self._scroll.scroll_to(percent=1.0)

    def clear(self) -> None:
        """Clear the output panel."""
        self._content.set_content("")
