"""Unit tests for SSEEventBus.

Tests thread-safe event queuing, SSE formatting, streaming generator,
and streaming pipeline callbacks.
"""

from __future__ import annotations

import asyncio
import json
import queue
from unittest.mock import MagicMock

import pytest

from web.sse_event_bus import SSEEventBus


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


async def _collect_all(gen) -> list[str]:
    """Collect all items from an async generator."""
    return [item async for item in gen]


# ---------------------------------------------------------------------------
# put_event / queue
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_put_event_enqueues_item() -> None:
    bus = SSEEventBus()
    bus.put_event("state_change", {"state": "active"})
    item = bus._queue.get_nowait()
    assert item == {"event": "state_change", "data": {"state": "active"}}


@pytest.mark.unit
def test_put_event_thread_safe_multiple() -> None:
    bus = SSEEventBus()
    for i in range(5):
        bus.put_event("tick", {"i": i})
    items = []
    while not bus._queue.empty():
        items.append(bus._queue.get_nowait())
    assert len(items) == 5
    assert all(item["event"] == "tick" for item in items)


# ---------------------------------------------------------------------------
# stream()
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_stream_yields_sse_formatted_string() -> None:
    bus = SSEEventBus()
    bus.put_event("state_change", {"state": "active"})
    bus._queue.put(None)  # sentinel to stop

    results = asyncio.run(_collect_all(bus.stream()))

    assert len(results) == 1
    assert results[0].startswith("event: state_change\n")
    assert '"state": "active"' in results[0]
    assert results[0].endswith("\n\n")


@pytest.mark.unit
def test_stream_stops_on_none_sentinel() -> None:
    bus = SSEEventBus()
    bus.put_event("progress", {"message": "hello"})
    bus.put_event("progress", {"message": "world"})
    bus._queue.put(None)

    results = asyncio.run(_collect_all(bus.stream()))

    assert len(results) == 2


@pytest.mark.unit
def test_stream_data_is_valid_json() -> None:
    bus = SSEEventBus()
    bus.put_event("timer_tick", {"elapsed": 42})
    bus._queue.put(None)

    results = asyncio.run(_collect_all(bus.stream()))
    data_line = [line for line in results[0].split("\n") if line.startswith("data:")][0]
    parsed = json.loads(data_line[len("data: "):])
    assert parsed == {"elapsed": 42}


# ---------------------------------------------------------------------------
# handle_stream_chunk — no template (plain text path)
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_handle_stream_chunk_no_template_emits_stream_text() -> None:
    bus = SSEEventBus()
    bus.handle_stream_chunk("hello world")
    item = bus._queue.get_nowait()
    assert item["event"] == "stream_text"
    assert item["data"]["chunk"] == "hello world"


# ---------------------------------------------------------------------------
# section_header detection
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_section_header_detected_for_all_caps_line() -> None:
    bus = SSEEventBus()
    # Simulate a template being active so we go through the buffer path
    bus._template_type = "generic"
    bus._template_config = {}
    from ui.stream_buffer import StreamBuffer
    bus._stream_buffer = StreamBuffer()

    bus.handle_stream_chunk("CORE THINKING\nSome detail here")

    events = []
    while not bus._queue.empty():
        events.append(bus._queue.get_nowait())

    header_events = [e for e in events if e["event"] == "section_header"]
    assert len(header_events) == 1
    assert header_events[0]["data"]["text"] == "CORE THINKING"


@pytest.mark.unit
def test_section_header_not_fired_for_html_line() -> None:
    bus = SSEEventBus()
    bus._template_type = "generic"
    bus._template_config = {}
    from ui.stream_buffer import StreamBuffer
    bus._stream_buffer = StreamBuffer()

    bus.handle_stream_chunk("<LI>ITEM</LI>")

    events = []
    while not bus._queue.empty():
        events.append(bus._queue.get_nowait())

    header_events = [e for e in events if e["event"] == "section_header"]
    assert len(header_events) == 0


@pytest.mark.unit
def test_section_header_not_fired_for_single_uppercase_letter() -> None:
    bus = SSEEventBus()
    bus._template_type = "generic"
    bus._template_config = {}
    from ui.stream_buffer import StreamBuffer
    bus._stream_buffer = StreamBuffer()

    bus.handle_stream_chunk("A\nOK\nI")

    events = []
    while not bus._queue.empty():
        events.append(bus._queue.get_nowait())

    header_events = [e for e in events if e["event"] == "section_header"]
    # "A" and "I" are single letters (< 2), "OK" has 2 letters — only OK matches
    texts = [e["data"]["text"] for e in header_events]
    assert "A" not in texts
    assert "I" not in texts


# ---------------------------------------------------------------------------
# make_template_setup_callback
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_template_setup_callback_emits_event() -> None:
    bus = SSEEventBus()
    cb = bus.make_template_setup_callback("generic", "My Title")
    cb("dummy_template_string")

    item = bus._queue.get_nowait()
    assert item["event"] == "template_setup"
    assert item["data"]["template_type"] == "generic"
    assert item["data"]["output_title"] == "My Title"


@pytest.mark.unit
def test_template_setup_callback_returns_template_type() -> None:
    bus = SSEEventBus()
    cb = bus.make_template_setup_callback("action_items", "Actions")
    result = cb("dummy")
    assert result == "action_items"


# ---------------------------------------------------------------------------
# reset()
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_reset_clears_streaming_state() -> None:
    bus = SSEEventBus()
    bus._template_type = "generic"
    bus._first_line_received = True
    bus.reset()
    assert bus._template_type is None
    assert bus._stream_buffer is None
    assert bus._first_line_received is False
