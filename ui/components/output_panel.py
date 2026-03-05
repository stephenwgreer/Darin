"""Claude analysis results display with streaming buffer pipeline (DAR2-37).

Displays Claude analysis output with bullet-by-bullet streaming:
1. setup_template() installs scaffold HTML with empty <ul> containers
2. handle_stream_chunk() buffers text, extracts complete <li> items,
   routes them via TEMPLATE_REGISTRY, and appends to DOM via JavaScript
3. _finalize() handles completion — skips content replace for registered
   templates (scaffold + streamed items are already correct)
"""

from __future__ import annotations

import json

from nicegui import ui

from ui.stream_buffer import StreamBuffer
from ui.stream_handlers import (
    STATIC_TEMPLATES,
    TEMPLATE_REGISTRY,
    parse_first_line_value,
    route_stream_item,
)


class OutputPanel:
    """Claude analysis results display with streaming support."""

    def __init__(self, controller: object) -> None:
        with ui.card().classes("w-full"):
            ui.label("Analysis Output").classes(
                "text-sm font-semibold text-gray-500 uppercase tracking-wide"
            )
            with ui.scroll_area().classes("w-full h-96 border rounded") as self._scroll:
                self._content = ui.html("").classes("prose max-w-none p-3")

        # Streaming state
        self._buffer = StreamBuffer()
        self._template_type: str | None = None
        self._first_line_received: bool = False

        # Wire callbacks on controller
        controller.on_stream_chunk = lambda chunk: self.handle_stream_chunk(chunk)  # type: ignore[attr-defined]
        controller.on_processing_complete = lambda result: self._finalize(result)  # type: ignore[attr-defined]

    def setup_template(self, template_type: str) -> None:
        """Install scaffold HTML and configure buffer for a template type.

        Called before streaming begins (from on_template_setup callback).
        """
        self._template_type = template_type
        self._first_line_received = False

        # Get pattern from registry (or default)
        config = TEMPLATE_REGISTRY.get(template_type)
        pattern = config["pattern"] if config else r"<li[^>]*>.*?</li>"

        # Reset buffer with template-specific pattern
        self._buffer = StreamBuffer(pattern=pattern)

        # Install scaffold HTML
        scaffold = STATIC_TEMPLATES.get(template_type, STATIC_TEMPLATES["generic"])
        self._content.set_content(scaffold)

    def handle_stream_chunk(self, chunk: str) -> None:
        """Process a streaming chunk: buffer, extract, route, append.

        Thread-safe: buffer operations are lock-protected internally.
        UI updates use ui.run_javascript() which is safe from any thread.
        """
        if not self._template_type:
            # No template set up — fall back to raw append
            current = self._content.content or ""
            self._content.set_content(current + chunk)
            self._scroll.scroll_to(percent=1.0)
            return

        config = TEMPLATE_REGISTRY.get(self._template_type)
        if not config:
            # Unregistered template type — raw append
            current = self._content.content or ""
            self._content.set_content(current + chunk)
            self._scroll.scroll_to(percent=1.0)
            return

        text = chunk

        # Handle first-line parsing (e.g., sentiment overall value)
        flp = config.get("first_line_parser")
        if flp and not self._first_line_received:
            value, text = parse_first_line_value(text, config)
            if value:
                self._first_line_received = True
                callback_method = flp.get("callback_method")
                if callback_method == "set_overall_sentiment":
                    escaped = json.dumps(value)
                    ui.run_javascript(
                        f'document.getElementById("overall-sentiment-value").innerText = {escaped}'
                    )
                if not text.strip():
                    return

        if not text.strip():
            return

        # Extract complete items from buffer
        items = self._buffer.write_and_extract(text)

        # Route and append each item
        for item in items:
            routed = route_stream_item(item, config)
            if routed:
                list_id, item_html = routed
                self._append_to_dom(list_id, item_html)

        if items:
            self._scroll.scroll_to(percent=1.0)

    def _append_to_dom(self, list_id: str, item_html: str) -> None:
        """Append an HTML item to a target element via JavaScript."""
        # Escape for JS template literal
        escaped = item_html.replace("\\", "\\\\").replace("`", "\\`").replace("$", "\\$")
        ui.run_javascript(
            f'document.getElementById("{list_id}").insertAdjacentHTML("beforeend", `{escaped}`)'
        )

    def _finalize(self, result: dict) -> None:
        """Called when streaming is complete.

        For registered templates: scaffold + streamed items are already
        in the DOM — do NOT replace content (would destroy streamed items).
        For unregistered templates: replace with final result.
        """
        if self._template_type and self._template_type in TEMPLATE_REGISTRY:
            # Streaming already populated the DOM — just scroll
            self._scroll.scroll_to(percent=1.0)
            return

        if "result" in result:
            self._content.set_content(result["result"])
        self._scroll.scroll_to(percent=1.0)

    def clear(self) -> None:
        """Clear the output panel and reset streaming state."""
        self._content.set_content("")
        self._template_type = None
        self._first_line_received = False
        self._buffer.clear()
