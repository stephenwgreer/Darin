"""SSE event bus: bridges AppController background-thread callbacks to async SSE stream.

AppController fires callbacks from background threads.  queue.Queue is used (not
asyncio.Queue) because it is thread-safe without requiring a running event loop.
The async SSE generator drains the queue via run_in_executor with a 50 ms timeout.
"""

from __future__ import annotations

import asyncio
import json
import queue
import re
from collections.abc import AsyncIterator, Callable
from typing import Any

from ui.stream_buffer import StreamBuffer
from ui.stream_handlers import (
    STATIC_TEMPLATES,
    TEMPLATE_REGISTRY,
    parse_first_line_value,
    route_stream_item,
)


class SSEEventBus:
    """Thread-safe bridge between AppController callbacks and the SSE stream."""

    def __init__(self) -> None:
        self._queue: queue.Queue[dict[str, Any] | None] = queue.Queue()
        self._stream_buffer: StreamBuffer | None = None
        self._template_type: str | None = None
        self._template_config: dict[str, Any] = {}
        self._first_line_received: bool = False

    # ------------------------------------------------------------------
    # Thread-safe event emission
    # ------------------------------------------------------------------

    def put_event(self, event_type: str, data: dict[str, Any]) -> None:
        """Enqueue an SSE event.  Safe to call from any thread."""
        self._queue.put({"event": event_type, "data": data})

    # ------------------------------------------------------------------
    # Async SSE generator
    # ------------------------------------------------------------------

    async def stream(self) -> AsyncIterator[str]:
        """Async generator consumed by the SSE endpoint.

        Polls the queue every 5 ms so the event loop stays responsive.
        Yields SSE-formatted strings.  Terminates on a None sentinel.
        Sends a keepalive comment every 15 s to prevent TCP timeouts.
        """
        loop = asyncio.get_running_loop()
        last_keepalive = loop.time()
        while True:
            try:
                item = await loop.run_in_executor(
                    None, lambda: self._queue.get(timeout=0.005)
                )
                if item is None:
                    return
                yield f"event: {item['event']}\ndata: {json.dumps(item['data'])}\n\n"
                last_keepalive = loop.time()
            except queue.Empty:
                if loop.time() - last_keepalive >= 15:
                    yield ": keepalive\n\n"
                    last_keepalive = loop.time()
                continue

    # ------------------------------------------------------------------
    # Streaming pipeline callbacks (called from AppController threads)
    # ------------------------------------------------------------------

    def make_template_setup_callback(
        self, template_type: str, output_title: str
    ) -> Callable[[str], str | None]:
        """Return an on_template_setup callback for controller.run_prompt().

        The returned callback:
        - Configures the StreamBuffer with the correct regex pattern
        - Emits a template_setup SSE event with scaffold HTML
        - Returns template_type to AppController (same call stack — no async needed)

        thread-safety: put_event() uses queue.Queue.put() — safe from any thread.
        """

        def on_template_setup(prompt_template: str) -> str | None:  # noqa: ARG001
            # Reset streaming state for this new prompt
            self._first_line_received = False
            self._template_type = template_type

            config = TEMPLATE_REGISTRY.get(template_type, {})
            self._template_config = config

            if config:
                self._stream_buffer = StreamBuffer(pattern=config["pattern"])
            else:
                self._stream_buffer = StreamBuffer()

            scaffold_html = STATIC_TEMPLATES.get(
                template_type, STATIC_TEMPLATES.get("generic", "")
            )

            self.put_event(
                "template_setup",
                {
                    "template_type": template_type,
                    "output_title": output_title,
                    "scaffold_html": scaffold_html,
                },
            )
            return template_type

        return on_template_setup

    def handle_stream_chunk(self, chunk: str) -> None:
        """on_stream_chunk callback wired to AppController.

        Runs the StreamBuffer extraction pipeline and routes items to SSE events:
        - stream_item   — a complete <li> routed to a named list
        - stream_text   — plain text chunk (no active template)
        - first_line_value — e.g. sentiment "Positive" / "Negative" / "Neutral"
        - section_header   — ALL-CAPS line detected in the chunk
        """
        if self._template_type is None or self._stream_buffer is None:
            self.put_event("stream_text", {"chunk": chunk})
            return

        config = self._template_config
        remaining = chunk

        # First-line value extraction (e.g. sentiment-analysis)
        if not self._first_line_received and config.get("first_line_parser"):
            value, remaining = parse_first_line_value(chunk, config)
            if value is not None:
                self._first_line_received = True
                flp = config["first_line_parser"]
                self.put_event(
                    "first_line_value",
                    {"callback_method": flp["callback_method"], "value": value},
                )

        # Extract complete HTML <li> items and route them
        items = self._stream_buffer.write_and_extract(remaining)
        for item in items:
            result = route_stream_item(item, config)
            if result:
                list_id, item_html = result
                self.put_event("stream_item", {"list_id": list_id, "item_html": item_html})

        # Section header detection: ALL-CAPS lines (e.g. "CORE THINKING")
        for line in remaining.splitlines():
            stripped = line.strip()
            if stripped and "<" not in stripped and re.match(r"^[A-Z]{2,}[A-Z\s]*$", stripped):
                self.put_event("section_header", {"text": stripped})

    # ------------------------------------------------------------------
    # State management
    # ------------------------------------------------------------------

    def reset(self) -> None:
        """Reset streaming state between prompts."""
        self._stream_buffer = None
        self._template_type = None
        self._template_config = {}
        self._first_line_received = False
