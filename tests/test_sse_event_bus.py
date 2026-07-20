"""Unit tests for SSEEventBus (multi-client fan-out rewrite).

Covers: per-client queues, thread-safe publish via call_soon_threadsafe,
SSE wire format, keepalive comments, slow-client drop-oldest, the card
event round-trip, and the streaming pipeline callbacks.
"""

from __future__ import annotations

import asyncio
import json
from collections.abc import Awaitable, Callable

import pytest

import web.sse_event_bus as sse_module
from web.sse_event_bus import SSEEventBus


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _parse_frame(frame: str) -> tuple[str, dict]:
    """Parse an 'event: X\\ndata: {...}\\n\\n' SSE frame."""
    lines = frame.strip().split("\n")
    event = lines[0][len("event: ") :]
    data = json.loads(lines[1][len("data: ") :])
    return event, data


def _drive(
    bus: SSEEventBus,
    actions: Callable[[], Awaitable[None]],
    *,
    n_clients: int = 1,
    settle: float = 0.05,
) -> list[list[str]]:
    """Run n_clients stream() consumers, execute actions, close, return frames.

    Keepalive comment frames are filtered out.
    """

    async def _run() -> list[list[str]]:
        frames: list[list[str]] = [[] for _ in range(n_clients)]

        async def consume(i: int) -> None:
            async for frame in bus.stream():
                frames[i].append(frame)

        tasks = [asyncio.create_task(consume(i)) for i in range(n_clients)]
        while bus.client_count < n_clients:
            await asyncio.sleep(0.001)
        await actions()
        await asyncio.sleep(settle)
        bus.close()
        await asyncio.wait_for(asyncio.gather(*tasks), timeout=5)
        return [[f for f in client if not f.startswith(":")] for client in frames]

    return asyncio.run(_run())


# ---------------------------------------------------------------------------
# put_event — publish safety
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_put_event_without_loop_is_dropped_not_crashed() -> None:
    """SSE is a live channel: publishing before any loop is bound must no-op."""
    bus = SSEEventBus()
    bus.put_event("state_change", {"state": "active"})  # must not raise
    bus.close()  # must not raise either


@pytest.mark.unit
def test_put_event_with_no_clients_is_dropped() -> None:
    """Loop bound but nobody connected: event is dropped silently."""

    async def _run() -> None:
        bus = SSEEventBus()
        bus.bind_loop(asyncio.get_running_loop())
        bus.put_event("progress", {"message": "nobody home"})
        await asyncio.sleep(0.01)
        assert bus.client_count == 0

    asyncio.run(_run())


# ---------------------------------------------------------------------------
# stream() — wire format and lifecycle
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_stream_yields_sse_formatted_string() -> None:
    bus = SSEEventBus()

    async def actions() -> None:
        bus.put_event("state_change", {"state": "active"})

    frames = _drive(bus, actions)[0]
    assert len(frames) == 1
    assert frames[0].startswith("event: state_change\n")
    assert '"state": "active"' in frames[0]
    assert frames[0].endswith("\n\n")


@pytest.mark.unit
def test_stream_data_is_valid_json() -> None:
    bus = SSEEventBus()

    async def actions() -> None:
        bus.put_event("timer_tick", {"elapsed": 42})

    frames = _drive(bus, actions)[0]
    event, data = _parse_frame(frames[0])
    assert event == "timer_tick"
    assert data == {"elapsed": 42}


@pytest.mark.unit
def test_stream_terminates_on_close() -> None:
    bus = SSEEventBus()

    async def actions() -> None:
        bus.put_event("progress", {"message": "hello"})
        bus.put_event("progress", {"message": "world"})

    frames = _drive(bus, actions)[0]  # _drive calls bus.close() and joins
    assert len(frames) == 2
    assert bus.client_count == 0


@pytest.mark.unit
def test_stream_preserves_event_order() -> None:
    bus = SSEEventBus()

    async def actions() -> None:
        for i in range(10):
            bus.put_event("timer_tick", {"elapsed": i})

    frames = _drive(bus, actions)[0]
    elapsed = [_parse_frame(f)[1]["elapsed"] for f in frames]
    assert elapsed == list(range(10))


@pytest.mark.unit
def test_client_count_tracks_connect_and_disconnect() -> None:
    bus = SSEEventBus()
    assert bus.client_count == 0

    async def actions() -> None:
        assert bus.client_count == 2

    _drive(bus, actions, n_clients=2)
    assert bus.client_count == 0


# ---------------------------------------------------------------------------
# Multi-client fan-out
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_two_clients_both_receive_every_event() -> None:
    bus = SSEEventBus()

    async def actions() -> None:
        bus.put_event("state_change", {"state": "active"})
        bus.put_event("timer_tick", {"elapsed": 7})

    frames = _drive(bus, actions, n_clients=2)
    for client_frames in frames:
        parsed = [_parse_frame(f) for f in client_frames]
        assert parsed == [
            ("state_change", {"state": "active"}),
            ("timer_tick", {"elapsed": 7}),
        ]


@pytest.mark.unit
def test_publish_from_worker_thread_reaches_all_clients() -> None:
    """put_event must be callable from a non-loop thread (controller callbacks)."""
    bus = SSEEventBus()

    async def actions() -> None:
        await asyncio.to_thread(bus.put_event, "watcher_status", {"state": "watching"})

    frames = _drive(bus, actions, n_clients=2)
    for client_frames in frames:
        assert _parse_frame(client_frames[0]) == (
            "watcher_status",
            {"state": "watching"},
        )


# ---------------------------------------------------------------------------
# New Wave-3 events: card round-trip, card_dismissed, usage, speaker payloads
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_card_event_round_trip() -> None:
    """A full card dict published from a worker thread arrives intact."""
    card = {
        "id": "card_ab12cd34ef56",
        "lane": "proactive",
        "type": "fact_check",
        "trigger": "factual_claim",
        "headline": "Latency claim is outdated",
        "bullets": ["v2 shipped in March", "p99 is now 120 ms"],
        "say_this": "Actually, the v2 numbers are much better.",
        "confidence": "high",
        "urgency": "now",
        "source": "kb",
        "expires_in_s": 45,
        "topic_key": "latency_claim",
    }
    bus = SSEEventBus()

    async def actions() -> None:
        await asyncio.to_thread(bus.put_event, "card", card)

    frames = _drive(bus, actions)[0]
    event, data = _parse_frame(frames[0])
    assert event == "card"
    assert data == card


@pytest.mark.unit
def test_card_dismissed_and_usage_events() -> None:
    bus = SSEEventBus()

    async def actions() -> None:
        bus.put_event("card_dismissed", {"id": "card_ab12cd34ef56"})
        bus.put_event("usage", {"meeting_cost_usd": 0.0412})

    frames = _drive(bus, actions)[0]
    assert _parse_frame(frames[0]) == ("card_dismissed", {"id": "card_ab12cd34ef56"})
    assert _parse_frame(frames[1]) == ("usage", {"meeting_cost_usd": 0.0412})


@pytest.mark.unit
def test_transcript_events_carry_text_and_speaker() -> None:
    bus = SSEEventBus()

    async def actions() -> None:
        bus.put_event("interim_transcript", {"text": "so the plan", "speaker": "THEM"})
        bus.put_event("final_transcript", {"text": "So the plan is set.", "speaker": "THEM"})

    frames = _drive(bus, actions)[0]
    event, data = _parse_frame(frames[0])
    assert event == "interim_transcript"
    assert data == {"text": "so the plan", "speaker": "THEM"}
    event, data = _parse_frame(frames[1])
    assert event == "final_transcript"
    assert data == {"text": "So the plan is set.", "speaker": "THEM"}


# ---------------------------------------------------------------------------
# Keepalive
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_keepalive_comment_emitted_when_idle(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(sse_module, "_KEEPALIVE_SECONDS", 0.02)
    bus = SSEEventBus()

    async def _run() -> list[str]:
        frames: list[str] = []

        async def consume() -> None:
            async for frame in bus.stream():
                frames.append(frame)

        task = asyncio.create_task(consume())
        while bus.client_count < 1:
            await asyncio.sleep(0.001)
        await asyncio.sleep(0.08)  # idle — several keepalive windows pass
        bus.close()
        await asyncio.wait_for(task, timeout=5)
        return frames

    frames = asyncio.run(_run())
    assert any(f.startswith(": keepalive") for f in frames)


# ---------------------------------------------------------------------------
# Slow client: drop-oldest, never block publishers
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_slow_client_drops_oldest_event() -> None:
    async def _run() -> None:
        bus = SSEEventBus()
        bus.bind_loop(asyncio.get_running_loop())
        # Inject a tiny stalled client queue directly (never consumed).
        tiny: asyncio.Queue = asyncio.Queue(maxsize=2)
        with bus._lock:
            bus._clients[999] = tiny

        for i in range(4):
            bus.put_event("timer_tick", {"elapsed": i})
        await asyncio.sleep(0.02)

        items = []
        while not tiny.empty():
            items.append(tiny.get_nowait())
        # Oldest events (0, 1) dropped; newest (2, 3) kept.
        assert [it["data"]["elapsed"] for it in items] == [2, 3]

    asyncio.run(_run())


# ---------------------------------------------------------------------------
# handle_stream_chunk — plain text path
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_handle_stream_chunk_no_template_emits_stream_text() -> None:
    bus = SSEEventBus()

    async def actions() -> None:
        bus.handle_stream_chunk("hello world")

    frames = _drive(bus, actions)[0]
    event, data = _parse_frame(frames[0])
    assert event == "stream_text"
    assert data["chunk"] == "hello world"


# ---------------------------------------------------------------------------
# section_header detection
# ---------------------------------------------------------------------------


def _activate_generic_template(bus: SSEEventBus) -> None:
    from web.stream_buffer import StreamBuffer

    bus._template_type = "generic"
    bus._template_config = {}
    bus._stream_buffer = StreamBuffer()


@pytest.mark.unit
def test_section_header_detected_for_all_caps_line() -> None:
    bus = SSEEventBus()
    _activate_generic_template(bus)

    async def actions() -> None:
        bus.handle_stream_chunk("CORE THINKING\nSome detail here")

    frames = _drive(bus, actions)[0]
    headers = [_parse_frame(f)[1]["text"] for f in frames if _parse_frame(f)[0] == "section_header"]
    assert headers == ["CORE THINKING"]


@pytest.mark.unit
def test_section_header_not_fired_for_html_line() -> None:
    bus = SSEEventBus()
    _activate_generic_template(bus)

    async def actions() -> None:
        bus.handle_stream_chunk("<LI>ITEM</LI>")

    frames = _drive(bus, actions)[0]
    assert all(_parse_frame(f)[0] != "section_header" for f in frames)


@pytest.mark.unit
def test_section_header_not_fired_for_single_uppercase_letter() -> None:
    bus = SSEEventBus()
    _activate_generic_template(bus)

    async def actions() -> None:
        bus.handle_stream_chunk("A\nOK\nI")

    frames = _drive(bus, actions)[0]
    headers = [_parse_frame(f)[1]["text"] for f in frames if _parse_frame(f)[0] == "section_header"]
    # "A" and "I" are single letters (< 2 chars) — never headers
    assert "A" not in headers
    assert "I" not in headers


# ---------------------------------------------------------------------------
# make_template_setup_callback
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_template_setup_callback_emits_event() -> None:
    bus = SSEEventBus()

    async def actions() -> None:
        cb = bus.make_template_setup_callback("generic", "My Title")
        cb("dummy_template_string")

    frames = _drive(bus, actions)[0]
    event, data = _parse_frame(frames[0])
    assert event == "template_setup"
    assert data["template_type"] == "generic"
    assert data["output_title"] == "My Title"
    assert "scaffold_html" in data


@pytest.mark.unit
def test_template_setup_callback_returns_template_type() -> None:
    bus = SSEEventBus()
    cb = bus.make_template_setup_callback("action-items", "Actions")
    result = cb("dummy")
    assert result == "action-items"


# ---------------------------------------------------------------------------
# reset()
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_reset_clears_streaming_state() -> None:
    bus = SSEEventBus()
    _activate_generic_template(bus)
    bus.reset()
    assert bus._template_type is None
    assert bus._stream_buffer is None
    assert bus._template_config == {}
