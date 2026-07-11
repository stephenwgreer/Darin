"""SSE event bus: multi-client fan-out from worker threads to SSE streams.

AppController fires callbacks from background threads. Each connected SSE
client owns a private ``asyncio.Queue``; publishers hand events to the event
loop via ``loop.call_soon_threadsafe`` — zero polling. The stream generator
blocks on its queue and wakes only for an event or the 15 s keepalive.

Events published before the event loop is bound (or with no clients
connected) are dropped: SSE is a live push channel, not a mailbox — clients
re-sync state via GET /api/state on connect.
"""

from __future__ import annotations

import asyncio
import json
import re
import threading
from collections.abc import AsyncIterator, Callable
from typing import Any

from loguru import logger

from web.stream_buffer import StreamBuffer
from web.stream_handlers import (
    STATIC_TEMPLATES,
    TEMPLATE_REGISTRY,
    route_stream_item,
)


# Per-client queue bound: if a client stops reading, drop its OLDEST events
# rather than blocking publishers or growing without bound.
_CLIENT_QUEUE_MAXSIZE = 512

# Keepalive comment interval (seconds) — prevents idle TCP/proxy timeouts.
_KEEPALIVE_SECONDS = 15.0


class SSEEventBus:
    """Thread-safe, multi-client bridge between AppController callbacks and SSE.

    Existing event names are preserved: state_change, timer_tick,
    transcription_complete, processing_complete, progress, stream_text,
    stream_item, section_header, template_setup, interim_transcript,
    final_transcript. New events (Wave 3): card, card_dismissed,
    watcher_status, usage.
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._loop: asyncio.AbstractEventLoop | None = None
        self._clients: dict[int, asyncio.Queue[dict[str, Any] | None]] = {}
        self._next_client_id = 0

        # Streaming pipeline state (post-meeting long-form path)
        self._stream_buffer: StreamBuffer | None = None
        self._template_type: str | None = None
        self._template_config: dict[str, Any] = {}

    # ------------------------------------------------------------------
    # Loop binding / client registry
    # ------------------------------------------------------------------

    def bind_loop(self, loop: asyncio.AbstractEventLoop) -> None:
        """Bind the event loop used for thread-safe fan-out.

        Called from the FastAPI lifespan handler; stream() also (re)binds as a
        safety net so a bus used outside the app factory still works.
        """
        with self._lock:
            self._loop = loop

    @property
    def client_count(self) -> int:
        """Number of currently connected SSE clients."""
        with self._lock:
            return len(self._clients)

    # ------------------------------------------------------------------
    # Thread-safe event emission
    # ------------------------------------------------------------------

    def put_event(self, event_type: str, data: dict[str, Any]) -> None:
        """Publish an SSE event to every connected client. Safe from any thread."""
        self._publish({"event": event_type, "data": data})

    def close(self) -> None:
        """Terminate all client streams (None sentinel). Safe from any thread."""
        self._publish(None)

    def _publish(self, item: dict[str, Any] | None) -> None:
        with self._lock:
            loop = self._loop
        if loop is None or loop.is_closed():
            logger.debug("SSE event dropped: no event loop bound")
            return
        try:
            loop.call_soon_threadsafe(self._fanout, item)
        except RuntimeError:  # loop closed between the check and the call
            logger.debug("SSE event dropped: event loop closed")

    def _fanout(self, item: dict[str, Any] | None) -> None:
        """Deliver one event to every client queue. Runs ON the event loop."""
        with self._lock:
            queues = list(self._clients.values())
        for q in queues:
            try:
                q.put_nowait(item)
            except asyncio.QueueFull:
                # Slow client: drop its oldest event, keep the stream alive.
                try:
                    q.get_nowait()
                except asyncio.QueueEmpty:  # pragma: no cover — racy edge
                    pass
                try:
                    q.put_nowait(item)
                except asyncio.QueueFull:  # pragma: no cover — racy edge
                    logger.warning("SSE client queue still full — event dropped")

    # ------------------------------------------------------------------
    # Async SSE generator (one per connected client)
    # ------------------------------------------------------------------

    async def stream(self) -> AsyncIterator[str]:
        """Async generator consumed by the SSE endpoint — one per client.

        Registers a private queue, then blocks on it (event-driven, zero
        polling). Emits a keepalive comment every 15 s of silence. Terminates
        on a None sentinel (bus.close()) or client disconnect (GeneratorExit).
        """
        loop = asyncio.get_running_loop()
        q: asyncio.Queue[dict[str, Any] | None] = asyncio.Queue(maxsize=_CLIENT_QUEUE_MAXSIZE)
        with self._lock:
            self._loop = loop
            client_id = self._next_client_id
            self._next_client_id += 1
            self._clients[client_id] = q
        logger.info("SSE client connected", client_id=client_id, clients=len(self._clients))
        try:
            while True:
                try:
                    item = await asyncio.wait_for(q.get(), timeout=_KEEPALIVE_SECONDS)
                except TimeoutError:
                    yield ": keepalive\n\n"
                    continue
                if item is None:
                    return
                yield f"event: {item['event']}\ndata: {json.dumps(item['data'])}\n\n"
        finally:
            with self._lock:
                self._clients.pop(client_id, None)
            logger.info("SSE client disconnected", client_id=client_id)

    # ------------------------------------------------------------------
    # Streaming pipeline callbacks (called from AppController threads)
    # ------------------------------------------------------------------

    def make_template_setup_callback(
        self, template_type: str, output_title: str
    ) -> Callable[[str], str | None]:
        """Return an on_template_setup callback for controller prompt runs.

        The returned callback:
        - Configures the StreamBuffer with the correct regex pattern
        - Emits a template_setup SSE event with scaffold HTML
        - Returns template_type to AppController (same call stack — no async needed)
        """

        def on_template_setup(prompt_template: str) -> str | None:  # noqa: ARG001
            self._template_type = template_type

            config = TEMPLATE_REGISTRY.get(template_type, {})
            self._template_config = config

            if config:
                self._stream_buffer = StreamBuffer(pattern=config["pattern"])
            else:
                self._stream_buffer = StreamBuffer()

            scaffold_html = STATIC_TEMPLATES.get(template_type, STATIC_TEMPLATES.get("generic", ""))

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
        - stream_item    — a complete <li> routed to a named list
        - stream_text    — plain text chunk (no active template)
        - section_header — ALL-CAPS line detected in the chunk
        """
        if self._template_type is None or self._stream_buffer is None:
            self.put_event("stream_text", {"chunk": chunk})
            return

        config = self._template_config

        # Extract complete HTML <li> items and route them
        items = self._stream_buffer.write_and_extract(chunk)
        for item in items:
            result = route_stream_item(item, config)
            if result:
                list_id, item_html = result
                self.put_event("stream_item", {"list_id": list_id, "item_html": item_html})

        # Section header detection: ALL-CAPS lines (e.g. "CORE THINKING")
        for line in chunk.splitlines():
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
