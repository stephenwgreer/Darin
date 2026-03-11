"""Claude analysis results display with streaming buffer pipeline (DAR2-37).

Displays Claude analysis output with bullet-by-bullet streaming:
1. setup_template() installs scaffold HTML with empty <ul> containers
2. handle_stream_chunk() buffers text, extracts complete <li> items,
   routes them via TEMPLATE_REGISTRY, and appends to DOM via JavaScript
3. _finalize() handles completion — skips content replace for registered
   templates (scaffold + streamed items are already correct)

Section-header detection: when a line in the markdown stream matches
^[A-Z][A-Z\\s]+$ (all-caps, possibly with spaces) the card title label
is updated to that value via _call_on_ui_thread.
"""

from __future__ import annotations

import asyncio
import functools
import json
import re
from collections.abc import Callable

from nicegui import Client, ui

from ui.stream_buffer import StreamBuffer
from ui.stream_handlers import (
    STATIC_TEMPLATES,
    TEMPLATE_REGISTRY,
    parse_first_line_value,
    route_stream_item,
)


_SECTION_HEADER_RE = re.compile(r"^[A-Z][A-Z\s]+$")


class OutputPanel:
    """Claude analysis results display with streaming support."""

    def __init__(self, controller: object, client: Client | None = None) -> None:
        with ui.card().classes("w-full"):
            self._title_label = ui.label("Analysis Output").classes(
                "text-sm font-semibold text-gray-500 uppercase tracking-wide"
            )
            with ui.scroll_area().classes("w-full h-96 border rounded") as self._scroll:
                self._content = ui.html("").classes("prose max-w-none p-3")
                self._md_content = ui.markdown("").classes("prose max-w-none p-3 output-panel-md")

        # Streaming state
        self._buffer = StreamBuffer()
        self._template_type: str | None = None
        self._first_line_received: bool = False
        self._raw_text: str = ""  # accumulates text for non-template (markdown) responses

        # Store the NiceGUI Client for context-free run_javascript calls.
        # Client.run_javascript() holds its own WebSocket reference and does
        # NOT require a contextvars context — safe to call from any thread.
        self._client = client

        # Scope heading sizes within the prose markdown area so H1/H2/H3
        # don't render at full typographic scale in the output box
        ui.add_css(
            ".output-panel-md h1, .output-panel-md h2 { "
            "font-size: 1rem !important; font-weight: 600; margin: 0.4rem 0; }"
            ".output-panel-md h3 { "
            "font-size: 0.9rem !important; font-weight: 600; margin: 0.3rem 0; }"
        )

        # Capture the event loop for thread-safe UI marshalling.
        # handle_stream_chunk() and _finalize() are called from a background
        # thread; all NiceGUI UI operations must be scheduled on this loop.
        self._loop = asyncio.get_event_loop()

        # Wire callbacks on controller
        controller.on_stream_chunk = lambda chunk: self.handle_stream_chunk(chunk)  # type: ignore[attr-defined]
        controller.on_processing_complete = lambda result: self._finalize(result)  # type: ignore[attr-defined]

    def _call_on_ui_thread(self, fn: Callable[..., object], *args: object) -> None:
        """Schedule a synchronous UI callback on the event loop (thread-safe).

        When called from a background thread (streaming callbacks), pushes the
        call onto the running NiceGUI event loop via call_soon_threadsafe so
        NiceGUI can deliver the WebSocket push on the correct thread.

        When no loop is running (unit tests, synchronous call sites), the
        function is invoked directly — this keeps test assertions working.

        For run_javascript calls use _run_javascript() instead — NiceGUI's
        Client.run_javascript() is a coroutine and must NOT be passed here.
        """
        try:
            if self._loop.is_running():
                self._loop.call_soon_threadsafe(functools.partial(fn, *args))
            else:
                fn(*args)
        except RuntimeError:
            fn(*args)

    def _run_javascript(self, js_code: str) -> None:
        """Schedule a run_javascript call using the stored Client reference.

        Client.run_javascript() holds its own WebSocket reference and is safe
        to call from background threads without a NiceGUI context variable.
        Falls back silently when no client is available (e.g. unit tests).
        """
        if self._client is not None:
            asyncio.run_coroutine_threadsafe(
                self._client.run_javascript(js_code), self._loop
            )

    def setup_template(self, template_type: str, output_title: str | None = None) -> None:
        """Install scaffold HTML and configure buffer for a template type.

        Called before streaming begins (from on_template_setup callback, which
        runs on a background thread). The set_content call is marshalled to the
        event loop via _call_on_ui_thread.

        If output_title is provided it is applied to the card title label
        immediately; otherwise the label is left unchanged.
        """
        self._template_type = template_type
        self._first_line_received = False
        self._raw_text = ""
        self._call_on_ui_thread(self._md_content.set_content, "")
        if output_title is not None:
            self._call_on_ui_thread(self._title_label.set_text, output_title)

        # Get pattern from registry (or default)
        config = TEMPLATE_REGISTRY.get(template_type)
        pattern = config["pattern"] if config else r"<li[^>]*>.*?</li>"

        # Reset buffer with template-specific pattern
        self._buffer = StreamBuffer(pattern=pattern)

        # Install scaffold HTML (marshal to UI thread — may be called from background)
        scaffold = STATIC_TEMPLATES.get(template_type, STATIC_TEMPLATES["generic"])
        self._call_on_ui_thread(self._content.set_content, scaffold)

    def handle_stream_chunk(self, chunk: str) -> None:
        """Process a streaming chunk: buffer, extract, route, append.

        Called from a background thread. Buffer operations are lock-protected
        internally. All NiceGUI UI calls are marshalled to the event loop via
        _call_on_ui_thread to prevent races on the WebSocket connection.
        """
        if not self._template_type:
            # No template set up — accumulate markdown for final render
            # Filter out ALL-CAPS section headers — they update the card title via
            # _detect_and_apply_section_header, so we don't need to render them in content
            filtered_lines = [
                line for line in chunk.splitlines(keepends=True)
                if not (line.strip() and _SECTION_HEADER_RE.match(line.strip()))
            ]
            self._raw_text += "".join(filtered_lines)
            self._call_on_ui_thread(self._md_content.set_content, self._raw_text)
            self._call_on_ui_thread(lambda: self._scroll.scroll_to(percent=1.0))
            self._detect_and_apply_section_header(chunk)
            return

        config = TEMPLATE_REGISTRY.get(self._template_type)
        if not config:
            # Unregistered template type — accumulate markdown for final render
            # Filter out ALL-CAPS section headers — they update the card title via
            # _detect_and_apply_section_header, so we don't need to render them in content
            filtered_lines = [
                line for line in chunk.splitlines(keepends=True)
                if not (line.strip() and _SECTION_HEADER_RE.match(line.strip()))
            ]
            self._raw_text += "".join(filtered_lines)
            self._call_on_ui_thread(self._md_content.set_content, self._raw_text)
            self._call_on_ui_thread(lambda: self._scroll.scroll_to(percent=1.0))
            self._detect_and_apply_section_header(chunk)
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
                    js_code = (
                        f'document.getElementById("overall-sentiment-value").innerText = {escaped}'
                    )
                    self._run_javascript(js_code)
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
            self._call_on_ui_thread(lambda: self._scroll.scroll_to(percent=1.0))

    def _append_to_dom(self, list_id: str, item_html: str) -> None:
        """Append an HTML item to a target element via JavaScript.

        list_id is sanitized before interpolation (defense-in-depth): characters
        that could break out of the double-quoted JS string are stripped.
        item_html is escaped for use inside a JS template literal.
        Called from handle_stream_chunk which runs on a background thread, so
        the actual ui.run_javascript call is marshalled via _call_on_ui_thread.
        """
        # Sanitize list_id — strip chars that could escape the double-quoted string
        safe_id = list_id.replace('"', "").replace("\\", "")
        # Escape item_html for JS template literal
        escaped = item_html.replace("\\", "\\\\").replace("`", "\\`").replace("$", "\\$")
        js_code = (
            f'document.getElementById("{safe_id}").insertAdjacentHTML("beforeend", `{escaped}`)'
        )
        self._run_javascript(js_code)

    def _detect_and_apply_section_header(self, chunk: str) -> None:
        """Scan completed lines in chunk for ALL-CAPS section headers.

        If a line matches ^[A-Z][A-Z\\s]+$ it is treated as a section header
        and the card title label is updated to that value on the UI thread.
        Only complete lines (terminated by newline) are checked so that a
        partial line arriving across two chunks is not misclassified.
        """
        for line in chunk.splitlines():
            stripped = line.strip()
            if stripped and _SECTION_HEADER_RE.match(stripped):
                self._call_on_ui_thread(self._title_label.set_text, stripped)
                return  # Use the first header found in this chunk

    def _finalize(self, result: dict[str, object]) -> None:
        """Called when streaming is complete.

        Called from a background thread via on_processing_complete. All UI
        operations are marshalled to the event loop via _call_on_ui_thread.

        For registered templates: scaffold + streamed items are already
        in the DOM — do NOT replace content (would destroy streamed items).
        For unregistered templates: replace with final result.
        """
        if self._template_type and self._template_type in TEMPLATE_REGISTRY:
            # Streaming already populated the DOM — just scroll
            self._call_on_ui_thread(lambda: self._scroll.scroll_to(percent=1.0))
            return

        if "result" in result:
            self._call_on_ui_thread(self._md_content.set_content, result["result"])
        self._call_on_ui_thread(lambda: self._scroll.scroll_to(percent=1.0))

    def clear(self) -> None:
        """Clear the output panel and reset streaming state (thread-safe)."""
        # Reset Python state first so any in-flight chunk sees _template_type=None
        self._template_type = None
        self._first_line_received = False
        self._raw_text = ""
        self._buffer.clear()
        # Marshal UI operations to event loop (safe from background threads)
        self._call_on_ui_thread(self._content.set_content, "")
        self._call_on_ui_thread(self._md_content.set_content, "")
        self._call_on_ui_thread(self._title_label.set_text, "Analysis Output")
