"""Unit tests for ApiClient — cache-first request shape, lane clients,
forced-tool-use card path, and usage/cost telemetry.

Also keeps the BUG-2026-02-09-006 regression coverage (client reuse).
No real API calls are made anywhere in this module.
"""

from __future__ import annotations

import sys
from collections.abc import Iterator
from pathlib import Path
from unittest.mock import MagicMock, Mock, patch

import pytest


# Ensure project root is on path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

import config
from api.client import (
    ApiClient,
    build_system_blocks,
    build_transcript_messages,
    build_web_search_tool,
    estimate_cost_usd,
)
from api.providers import ModelRegistry
from storage.app_config import AppConfig, CustomEndpointConfig


# ---------------------------------------------------------------------------
# Fixtures / helpers
# ---------------------------------------------------------------------------


@pytest.fixture
def valid_keys() -> dict[str, str]:
    """Valid API key values for constructing ApiClient in tests."""
    return {
        "anthropic_api_key": "test-anthropic-key-abc123",
        "deepgram_api_key": "test-deepgram-key-xyz789",
    }


@pytest.fixture
def api_client(valid_keys: dict[str, str]) -> ApiClient:
    """Construct an ApiClient with test API keys (no real API calls)."""
    return ApiClient(**valid_keys)


@pytest.fixture
def mock_anthropic_class() -> Iterator[MagicMock]:
    """Patch the Anthropic class to prevent real client construction."""
    with patch("api.client.Anthropic") as mock_cls:
        mock_instance = Mock()
        mock_cls.return_value = mock_instance
        yield mock_cls


def make_usage(
    input_tokens: int = 100,
    output_tokens: int = 10,
    cache_read: int = 0,
    cache_write: int = 0,
) -> Mock:
    usage = Mock()
    usage.input_tokens = input_tokens
    usage.output_tokens = output_tokens
    usage.cache_read_input_tokens = cache_read
    usage.cache_creation_input_tokens = cache_write
    return usage


def make_text_response(text: str = "Hello, world", stop_reason: str = "end_turn") -> Mock:
    block = Mock()
    block.type = "text"
    block.text = text
    response = Mock()
    response.content = [block]
    response.usage = make_usage()
    response.stop_reason = stop_reason
    return response


def make_stream_ctx(chunks: list[str] | None = None) -> MagicMock:
    ctx = MagicMock()
    ctx.__enter__ = Mock(return_value=ctx)
    ctx.__exit__ = Mock(return_value=False)
    ctx.text_stream = iter(chunks or ["Hello", ", ", "world"])
    ctx.get_final_message.return_value = make_text_response("".join(chunks or []))
    return ctx


def make_cards_response(cards: list[dict], stop_reason: str = "tool_use") -> Mock:
    block = Mock()
    block.type = "tool_use"
    block.name = "emit_cards"
    block.input = {"cards": cards}
    response = Mock()
    response.content = [block]
    response.usage = make_usage()
    response.stop_reason = stop_reason
    return response


# ---------------------------------------------------------------------------
# Tests: Client Reuse (regression for BUG-2026-02-09-006)
# ---------------------------------------------------------------------------


class TestAnthropicClientReuse:
    """Verify the Anthropic client is lazy-loaded and reused — BUG-2026-02-09-006."""

    def test_anthropic_client_not_created_at_init(
        self, mock_anthropic_class: MagicMock, valid_keys: dict[str, str]
    ) -> None:
        """Client must NOT be created in __init__ — lazy init only."""
        _ = ApiClient(**valid_keys)

        mock_anthropic_class.assert_not_called()

    def test_anthropic_client_created_on_first_access(
        self, mock_anthropic_class: MagicMock, valid_keys: dict[str, str]
    ) -> None:
        """Accessing anthropic_client for the first time creates the instance."""
        client = ApiClient(**valid_keys)

        _ = client.anthropic_client

        mock_anthropic_class.assert_called_once_with(api_key=valid_keys["anthropic_api_key"])

    def test_anthropic_client_same_instance_on_second_access(
        self, mock_anthropic_class: MagicMock, valid_keys: dict[str, str]
    ) -> None:
        """Second access to anthropic_client returns the same object (identity check)."""
        client = ApiClient(**valid_keys)

        first = client.anthropic_client
        second = client.anthropic_client

        assert first is second

    def test_anthropic_client_created_exactly_once_across_many_accesses(
        self, mock_anthropic_class: MagicMock, valid_keys: dict[str, str]
    ) -> None:
        """Anthropic() constructor is called exactly once no matter how many accesses."""
        client = ApiClient(**valid_keys)

        for _ in range(10):
            _ = client.anthropic_client

        mock_anthropic_class.assert_called_once()


class TestLaneClients:
    """Per-lane Anthropic clients: watcher = fail fast; others = SDK defaults."""

    def test_watcher_client_uses_zero_retries_and_short_timeout(
        self, mock_anthropic_class: MagicMock, valid_keys: dict[str, str]
    ) -> None:
        client = ApiClient(**valid_keys)

        _ = client.watcher_anthropic_client

        mock_anthropic_class.assert_called_once_with(
            api_key=valid_keys["anthropic_api_key"],
            max_retries=config.WATCHER_MAX_RETRIES,
            timeout=config.WATCHER_TIMEOUT_S,
        )
        assert config.WATCHER_MAX_RETRIES == 0
        assert config.WATCHER_TIMEOUT_S == 8.0

    def test_default_client_uses_sdk_defaults(
        self, mock_anthropic_class: MagicMock, valid_keys: dict[str, str]
    ) -> None:
        """Non-watcher lanes must not override max_retries/timeout (SDK defaults)."""
        client = ApiClient(**valid_keys)

        _ = client.anthropic_client

        kwargs = mock_anthropic_class.call_args.kwargs
        assert "max_retries" not in kwargs
        assert "timeout" not in kwargs

    def test_watcher_and_default_clients_are_distinct(
        self, mock_anthropic_class: MagicMock, valid_keys: dict[str, str]
    ) -> None:
        mock_anthropic_class.side_effect = [Mock(), Mock()]
        client = ApiClient(**valid_keys)

        assert client.anthropic_client is not client.watcher_anthropic_client


# ---------------------------------------------------------------------------
# Tests: ApiClient initialisation
# ---------------------------------------------------------------------------


class TestApiClientInit:
    """Verify ApiClient constructor behaviour and validation."""

    def test_init_stores_anthropic_api_key(self, valid_keys: dict[str, str]) -> None:
        client = ApiClient(**valid_keys)
        assert client.anthropic_api_key == valid_keys["anthropic_api_key"]

    def test_init_stores_deepgram_api_key(self, valid_keys: dict[str, str]) -> None:
        client = ApiClient(**valid_keys)
        assert client.deepgram_api_key == valid_keys["deepgram_api_key"]

    def test_init_raises_on_missing_anthropic_key(self) -> None:
        with pytest.raises(ValueError, match="Anthropic API key"):
            ApiClient(anthropic_api_key="", deepgram_api_key="valid-deepgram-key")

    def test_init_raises_on_whitespace_anthropic_key(self) -> None:
        with pytest.raises(ValueError, match="Anthropic API key"):
            ApiClient(anthropic_api_key="   ", deepgram_api_key="valid-deepgram-key")

    def test_init_raises_on_missing_deepgram_key(self) -> None:
        with pytest.raises(ValueError, match="Deepgram API key"):
            ApiClient(anthropic_api_key="valid-anthropic-key", deepgram_api_key="")

    def test_init_raises_on_whitespace_deepgram_key(self) -> None:
        with pytest.raises(ValueError, match="Deepgram API key"):
            ApiClient(anthropic_api_key="valid-anthropic-key", deepgram_api_key="  ")


# ---------------------------------------------------------------------------
# Tests: cache-first request builders
# ---------------------------------------------------------------------------


class TestCacheFirstBuilders:
    """The shared request shape: cached system + transcript, instruction LAST."""

    def test_system_cache_control_on_last_block(self) -> None:
        blocks = build_system_blocks("stable instructions", "context pack text")
        assert len(blocks) == 2
        assert "cache_control" not in blocks[0]
        assert blocks[-1]["cache_control"] == {"type": "ephemeral"}
        assert blocks[-1]["text"] == "context pack text"

    def test_system_without_context_pack_caches_instructions(self) -> None:
        blocks = build_system_blocks("stable instructions", None)
        assert len(blocks) == 1
        assert blocks[0]["cache_control"] == {"type": "ephemeral"}

    def test_empty_context_pack_is_omitted(self) -> None:
        blocks = build_system_blocks("stable instructions", "   ")
        assert len(blocks) == 1

    def test_transcript_messages_cache_breakpoint_on_last_block(self) -> None:
        messages = build_transcript_messages(["block one", "block two"], "do the thing")
        assert len(messages) == 2
        transcript_content = messages[0]["content"]
        assert "cache_control" not in transcript_content[0]
        assert transcript_content[-1]["cache_control"] == {"type": "ephemeral"}
        # Instruction is the FINAL user message and is uncached
        instruction = messages[-1]["content"][0]
        assert instruction["text"] == "do the thing"
        assert "cache_control" not in instruction

    def test_transcript_messages_append_only_prefix_is_stable(self) -> None:
        """Growing the block list must not change earlier blocks (cache prefix)."""
        first = build_transcript_messages(["a", "b"], "i1")
        second = build_transcript_messages(["a", "b", "c"], "i2")
        assert second[0]["content"][0]["text"] == first[0]["content"][0]["text"]
        assert second[0]["content"][1]["text"] == "b"
        assert "cache_control" not in second[0]["content"][1]

    def test_cache_transcript_false_adds_no_breakpoint(self) -> None:
        messages = build_transcript_messages(["a"], "i", cache_transcript=False)
        assert "cache_control" not in messages[0]["content"][0]

    def test_empty_transcript_yields_instruction_only(self) -> None:
        messages = build_transcript_messages([], "just the instruction")
        assert len(messages) == 1
        assert messages[0]["content"][0]["text"] == "just the instruction"


# ---------------------------------------------------------------------------
# Tests: process_with_anthropic (cached long-form lane)
# ---------------------------------------------------------------------------


class TestProcessWithAnthropic:
    """The long-form path routed through the cache-first builder."""

    @pytest.fixture
    def client_with_mock_anthropic(
        self, valid_keys: dict[str, str]
    ) -> Iterator[tuple[ApiClient, MagicMock]]:
        """ApiClient with a fully mocked Anthropic SDK client."""
        with patch("api.client.Anthropic") as mock_cls:
            mock_sdk_client = Mock()
            mock_cls.return_value = mock_sdk_client

            mock_sdk_client.messages.stream.return_value = make_stream_ctx(["Hello", ", ", "world"])
            mock_sdk_client.messages.create.return_value = make_text_response("Hello, world")

            client = ApiClient(**valid_keys)
            yield client, mock_sdk_client

    def test_process_with_anthropic_returns_streamed_text(
        self, client_with_mock_anthropic: tuple[ApiClient, MagicMock]
    ) -> None:
        client, _ = client_with_mock_anthropic
        result = client.process_with_anthropic("test input", stream=True)
        assert result == "Hello, world"

    def test_process_with_anthropic_non_streaming_returns_text(
        self, client_with_mock_anthropic: tuple[ApiClient, MagicMock]
    ) -> None:
        client, _ = client_with_mock_anthropic
        result = client.process_with_anthropic("test input", stream=False)
        assert result == "Hello, world"

    def test_streaming_invokes_callback_per_chunk(
        self, client_with_mock_anthropic: tuple[ApiClient, MagicMock]
    ) -> None:
        client, _ = client_with_mock_anthropic
        chunks: list[str] = []
        client.process_with_anthropic("test input", stream=True, callback=chunks.append)
        assert chunks == ["Hello", ", ", "world"]

    def test_process_with_anthropic_uses_cached_client(self, valid_keys: dict[str, str]) -> None:
        """Multiple process_with_anthropic calls must NOT create new Anthropic instances."""
        with patch("api.client.Anthropic") as mock_cls:
            mock_sdk = Mock()
            mock_cls.return_value = mock_sdk
            mock_sdk.messages.stream.side_effect = [
                make_stream_ctx(["ok"]),
                make_stream_ctx(["ok"]),
            ]

            client = ApiClient(**valid_keys)
            client.process_with_anthropic("first call", stream=True)
            client.process_with_anthropic("second call", stream=True)

            mock_cls.assert_called_once()

    def test_cache_first_shape_transcript_cached_instruction_last(
        self, client_with_mock_anthropic: tuple[ApiClient, MagicMock]
    ) -> None:
        """Transcript rides in a cached block; the instruction is the FINAL message."""
        client, mock_sdk = client_with_mock_anthropic

        client.process_with_anthropic(
            "my transcript",
            prompt_template="Summarise the following:\n{transcript}",
            stream=False,
        )

        kwargs = mock_sdk.messages.create.call_args.kwargs
        # System blocks: stable instructions with cache_control on the LAST block
        system = kwargs["system"]
        assert system[-1]["cache_control"] == {"type": "ephemeral"}
        # Transcript block cached, instruction (template minus placeholder) LAST
        messages = kwargs["messages"]
        transcript_block = messages[0]["content"][-1]
        assert "my transcript" in transcript_block["text"]
        assert transcript_block["cache_control"] == {"type": "ephemeral"}
        instruction_block = messages[-1]["content"][0]
        assert "Summarise the following:" in instruction_block["text"]
        assert "{transcript}" not in instruction_block["text"]
        assert "cache_control" not in instruction_block

    def test_never_sends_temperature(
        self, client_with_mock_anthropic: tuple[ApiClient, MagicMock]
    ) -> None:
        client, mock_sdk = client_with_mock_anthropic
        client.process_with_anthropic("text", stream=False)
        assert "temperature" not in mock_sdk.messages.create.call_args.kwargs

    def test_sonnet5_disables_adaptive_thinking(
        self, client_with_mock_anthropic: tuple[ApiClient, MagicMock]
    ) -> None:
        """claude-sonnet-5 runs ADAPTIVE thinking when the param is omitted —
        long-form/background calls must disable it (latency + max_tokens)."""
        client, mock_sdk = client_with_mock_anthropic
        client.process_with_anthropic("text", stream=False, model="claude-sonnet-5")
        assert mock_sdk.messages.create.call_args.kwargs["thinking"] == {"type": "disabled"}

        client.process_with_anthropic("text", stream=True, model="claude-sonnet-5")
        assert mock_sdk.messages.stream.call_args.kwargs["thinking"] == {"type": "disabled"}

    def test_haiku_omits_thinking_param(
        self, client_with_mock_anthropic: tuple[ApiClient, MagicMock]
    ) -> None:
        """claude-haiku-4-5 runs WITHOUT thinking when the param is omitted."""
        client, mock_sdk = client_with_mock_anthropic
        client.process_with_anthropic("text", stream=False, model="claude-haiku-4-5")
        assert "thinking" not in mock_sdk.messages.create.call_args.kwargs

    def test_cache_transcript_false_skips_cache_write(
        self, client_with_mock_anthropic: tuple[ApiClient, MagicMock]
    ) -> None:
        """One-shot lanes (map-reduce, titles, rolling summary) must not pay
        the cache-write premium on blocks that are never re-read."""
        client, mock_sdk = client_with_mock_anthropic
        client.process_with_anthropic("one-shot text", stream=False, cache_transcript=False)
        messages = mock_sdk.messages.create.call_args.kwargs["messages"]
        transcript_block = messages[0]["content"][-1]
        assert "one-shot text" in transcript_block["text"]
        assert "cache_control" not in transcript_block

    def test_split_template_never_ends_in_dangling_label(
        self, client_with_mock_anthropic: tuple[ApiClient, MagicMock]
    ) -> None:
        """Lifting {transcript} out must not leave the instruction ending in a
        content label pointing at nothing — a pointer to the real location is
        appended instead."""
        client, mock_sdk = client_with_mock_anthropic
        client.process_with_anthropic(
            "the text",
            prompt_template="Summarise this.\n\nText to analyze:\n{transcript}",
            stream=False,
        )
        instruction = mock_sdk.messages.create.call_args.kwargs["messages"][-1]["content"][0]
        assert instruction["text"].endswith("(The transcript is provided in the previous message.)")

    def test_model_and_max_tokens_overrides(
        self, client_with_mock_anthropic: tuple[ApiClient, MagicMock]
    ) -> None:
        client, mock_sdk = client_with_mock_anthropic
        client.process_with_anthropic(
            "text", stream=False, model=config.WATCHER_MODEL, max_tokens=64
        )
        kwargs = mock_sdk.messages.create.call_args.kwargs
        assert kwargs["model"] == config.WATCHER_MODEL
        assert kwargs["max_tokens"] == 64

    def test_defaults_to_post_meeting_tier(
        self, client_with_mock_anthropic: tuple[ApiClient, MagicMock]
    ) -> None:
        client, mock_sdk = client_with_mock_anthropic
        client.process_with_anthropic("text", stream=False)
        kwargs = mock_sdk.messages.create.call_args.kwargs
        assert kwargs["model"] == config.POST_MEETING_MODEL
        assert kwargs["max_tokens"] == config.POST_MEETING_MAX_TOKENS

    def test_template_with_stray_braces_does_not_raise(
        self, client_with_mock_anthropic: tuple[ApiClient, MagicMock]
    ) -> None:
        """partition (not format) — user templates with { } must not crash."""
        client, _ = client_with_mock_anthropic
        result = client.process_with_anthropic(
            "text",
            prompt_template="Weird {braces} here:\n{transcript}",
            stream=False,
        )
        assert result == "Hello, world"

    def test_process_with_anthropic_raises_on_empty_key(self, valid_keys: dict[str, str]) -> None:
        with patch("api.client.Anthropic"):
            client = ApiClient(**valid_keys)
            client.anthropic_api_key = ""

            with pytest.raises(ValueError, match="Anthropic API key not set"):
                client.process_with_anthropic("test")

    def test_no_hand_rolled_retry_loop(self, valid_keys: dict[str, str]) -> None:
        """API errors propagate immediately — retries are SDK-only now."""
        with patch("api.client.Anthropic") as mock_cls:
            mock_sdk = Mock()
            mock_cls.return_value = mock_sdk
            mock_sdk.messages.create.side_effect = RuntimeError("boom")

            client = ApiClient(**valid_keys)
            with pytest.raises(RuntimeError, match="boom"):
                client.process_with_anthropic("text", stream=False)
            assert mock_sdk.messages.create.call_count == 1


# ---------------------------------------------------------------------------
# Tests: create_cards (forced tool use)
# ---------------------------------------------------------------------------


class TestCreateCards:
    """Forced emit_cards tool use — the JSON card path for both live lanes."""

    @pytest.fixture
    def client_with_mock_anthropic(
        self, valid_keys: dict[str, str]
    ) -> Iterator[tuple[ApiClient, Mock]]:
        with patch("api.client.Anthropic") as mock_cls:
            mock_sdk = Mock()
            mock_cls.return_value = mock_sdk
            client = ApiClient(**valid_keys)
            yield client, mock_sdk

    def _call(self, client: ApiClient, lane: str = "reactive") -> list:
        return client.create_cards(
            lane=lane,
            model=config.REACTIVE_MODEL if lane == "reactive" else config.WATCHER_MODEL,
            max_tokens=400,
            system=build_system_blocks("sys"),
            messages=build_transcript_messages(["t"], "instruction"),
        )

    def test_forced_tool_choice_emit_cards(
        self, client_with_mock_anthropic: tuple[ApiClient, Mock]
    ) -> None:
        client, mock_sdk = client_with_mock_anthropic
        mock_sdk.messages.create.return_value = make_cards_response([])

        self._call(client)

        kwargs = mock_sdk.messages.create.call_args.kwargs
        assert kwargs["tool_choice"] == {"type": "tool", "name": "emit_cards"}
        assert kwargs["tools"][0]["name"] == "emit_cards"

    def test_reactive_lane_disables_thinking(
        self, client_with_mock_anthropic: tuple[ApiClient, Mock]
    ) -> None:
        client, mock_sdk = client_with_mock_anthropic
        mock_sdk.messages.create.return_value = make_cards_response([])

        self._call(client, lane="reactive")

        assert mock_sdk.messages.create.call_args.kwargs["thinking"] == {"type": "disabled"}

    def test_watcher_lane_omits_thinking(
        self, client_with_mock_anthropic: tuple[ApiClient, Mock]
    ) -> None:
        client, mock_sdk = client_with_mock_anthropic
        mock_sdk.messages.create.return_value = make_cards_response([])

        self._call(client, lane="watcher")

        assert "thinking" not in mock_sdk.messages.create.call_args.kwargs

    def test_empty_cards_is_valid_nothing_to_say(
        self, client_with_mock_anthropic: tuple[ApiClient, Mock]
    ) -> None:
        client, mock_sdk = client_with_mock_anthropic
        mock_sdk.messages.create.return_value = make_cards_response([])

        assert self._call(client) == []

    def test_cards_parsed_with_lane_attribution(
        self, client_with_mock_anthropic: tuple[ApiClient, Mock]
    ) -> None:
        client, mock_sdk = client_with_mock_anthropic
        mock_sdk.messages.create.return_value = make_cards_response(
            [{"type": "answer", "headline": "The answer", "bullets": ["one"]}]
        )

        watcher_cards = self._call(client, lane="watcher")
        assert len(watcher_cards) == 1
        assert watcher_cards[0].lane == "proactive"

        mock_sdk.messages.create.return_value = make_cards_response(
            [{"type": "answer", "headline": "The answer"}]
        )
        reactive_cards = self._call(client, lane="reactive")
        assert reactive_cards[0].lane == "reactive"

    def test_missing_tool_use_block_returns_empty(
        self, client_with_mock_anthropic: tuple[ApiClient, Mock]
    ) -> None:
        client, mock_sdk = client_with_mock_anthropic
        mock_sdk.messages.create.return_value = make_text_response("not a tool call")

        assert self._call(client) == []


# ---------------------------------------------------------------------------
# Tests: usage / cost telemetry
# ---------------------------------------------------------------------------


class TestUsageTelemetry:
    """Per-call usage logging and per-meeting cost accumulation."""

    def test_estimate_cost_includes_cache_tiers(self) -> None:
        usage = make_usage(input_tokens=1_000_000, output_tokens=0, cache_read=0, cache_write=0)
        assert estimate_cost_usd("claude-haiku-4-5", usage) == pytest.approx(1.00)

        usage = make_usage(input_tokens=0, output_tokens=0, cache_read=1_000_000)
        assert estimate_cost_usd("claude-haiku-4-5", usage) == pytest.approx(0.10)

        usage = make_usage(input_tokens=0, output_tokens=0, cache_write=1_000_000)
        assert estimate_cost_usd("claude-haiku-4-5", usage) == pytest.approx(1.25)

        usage = make_usage(input_tokens=0, output_tokens=1_000_000)
        assert estimate_cost_usd("claude-sonnet-5", usage) == pytest.approx(15.00)

    def test_meeting_cost_accumulates_and_resets(self, valid_keys: dict[str, str]) -> None:
        with patch("api.client.Anthropic") as mock_cls:
            mock_sdk = Mock()
            mock_cls.return_value = mock_sdk
            mock_sdk.messages.create.return_value = make_text_response("ok")

            client = ApiClient(**valid_keys)
            assert client.meeting_cost_usd == 0.0

            client.process_with_anthropic("t", stream=False)
            after_one = client.meeting_cost_usd
            assert after_one > 0.0

            client.process_with_anthropic("t", stream=False)
            assert client.meeting_cost_usd == pytest.approx(after_one * 2)

            client.reset_meeting_cost()
            assert client.meeting_cost_usd == 0.0

    def test_on_usage_callback_receives_meeting_cost(self, valid_keys: dict[str, str]) -> None:
        with patch("api.client.Anthropic") as mock_cls:
            mock_sdk = Mock()
            mock_cls.return_value = mock_sdk
            mock_sdk.messages.create.return_value = make_text_response("ok")

            client = ApiClient(**valid_keys)
            events: list[dict] = []
            client.on_usage = events.append

            client.process_with_anthropic("t", stream=False)

            assert len(events) == 1
            assert events[0]["meeting_cost_usd"] == pytest.approx(client.meeting_cost_usd)

    def test_max_tokens_truncation_is_flagged(self, valid_keys: dict[str, str]) -> None:
        """stop_reason == max_tokens must be logged as a warning."""
        with patch("api.client.Anthropic") as mock_cls, patch("api.client.logger") as mock_logger:
            mock_sdk = Mock()
            mock_cls.return_value = mock_sdk
            mock_sdk.messages.create.return_value = make_text_response(
                "truncated", stop_reason="max_tokens"
            )

            client = ApiClient(**valid_keys)
            client.process_with_anthropic("t", stream=False)

            warning_msgs = [str(c.args[0]) for c in mock_logger.warning.call_args_list]
            assert any("truncated" in m or "max_tokens" in m for m in warning_msgs)

    def test_on_usage_failure_does_not_break_call(self, valid_keys: dict[str, str]) -> None:
        with patch("api.client.Anthropic") as mock_cls:
            mock_sdk = Mock()
            mock_cls.return_value = mock_sdk
            mock_sdk.messages.create.return_value = make_text_response("ok")

            client = ApiClient(**valid_keys)
            client.on_usage = Mock(side_effect=RuntimeError("bad consumer"))

            assert client.process_with_anthropic("t", stream=False) == "ok"


def make_web_search_cards_response(
    cards: list[dict], *, stop_reason: str = "end_turn", text: str = ""
) -> Mock:
    """A response mixing a text block + an emit_cards tool_use (web-search shape)."""
    content: list[Mock] = []
    if text:
        tb = Mock()
        tb.type = "text"
        tb.text = text
        content.append(tb)
    if cards is not None:
        block = Mock()
        block.type = "tool_use"
        block.name = "emit_cards"
        block.input = {"cards": cards}
        content.append(block)
    response = Mock()
    response.content = content
    response.usage = make_usage()
    response.stop_reason = stop_reason
    return response


def make_pause_turn_response() -> Mock:
    """A server-tool pause_turn response (no emit_cards yet)."""
    stu = Mock()
    stu.type = "server_tool_use"
    stu.name = "web_search"
    response = Mock()
    response.content = [stu]
    response.usage = make_usage()
    response.stop_reason = "pause_turn"
    return response


# ---------------------------------------------------------------------------
# Tests: provider routing (F2)
# ---------------------------------------------------------------------------


def _openai_registry() -> ModelRegistry:
    return ModelRegistry(
        AppConfig(
            custom_endpoints=[
                CustomEndpointConfig(
                    id="groq",
                    label="Groq",
                    base_url="https://api.groq.com/openai/v1",
                    model_name="llama-3.3-70b",
                    api_key="gsk_x",
                )
            ]
        )
    )


class TestProviderRouting:
    """create_cards / process_with_anthropic route by model id via the registry."""

    def test_create_cards_routes_openai_compat_to_adapter(
        self, mock_anthropic_class: MagicMock, valid_keys: dict[str, str]
    ) -> None:
        client = ApiClient(**valid_keys, model_registry=_openai_registry())
        with patch("api.client.create_cards_openai") as mock_adapter:
            mock_adapter.return_value = []
            client.create_cards(
                lane="reactive",
                model="groq",
                max_tokens=400,
                system=build_system_blocks("sys"),
                messages=build_transcript_messages(["t"], "i"),
            )
        mock_adapter.assert_called_once()
        assert mock_adapter.call_args.kwargs["card_lane"] == "reactive"

    def test_create_cards_openai_compat_ignores_web_search(
        self, mock_anthropic_class: MagicMock, valid_keys: dict[str, str]
    ) -> None:
        client = ApiClient(**valid_keys, model_registry=_openai_registry())
        with (
            patch("api.client.create_cards_openai") as mock_adapter,
            patch("api.client.logger") as mock_logger,
        ):
            mock_adapter.return_value = []
            client.create_cards(
                lane="reactive",
                model="groq",
                max_tokens=400,
                system=build_system_blocks("sys"),
                messages=build_transcript_messages(["t"], "i"),
                web_search=True,
            )
        warnings = [str(c.args[0]) for c in mock_logger.warning.call_args_list]
        assert any("web_search" in m for m in warnings)

    def test_anthropic_model_still_uses_native_forced_tool(
        self, valid_keys: dict[str, str]
    ) -> None:
        with patch("api.client.Anthropic") as mock_cls:
            mock_sdk = Mock()
            mock_cls.return_value = mock_sdk
            mock_sdk.messages.create.return_value = make_cards_response([])
            client = ApiClient(**valid_keys, model_registry=ModelRegistry(AppConfig()))
            client.create_cards(
                lane="reactive",
                model="claude-sonnet-5",
                max_tokens=400,
                system=build_system_blocks("sys"),
                messages=build_transcript_messages(["t"], "i"),
            )
            kwargs = mock_sdk.messages.create.call_args.kwargs
            assert kwargs["tool_choice"] == {"type": "tool", "name": "emit_cards"}

    def test_unknown_model_with_no_registry_uses_native(self, valid_keys: dict[str, str]) -> None:
        with patch("api.client.Anthropic") as mock_cls:
            mock_sdk = Mock()
            mock_cls.return_value = mock_sdk
            mock_sdk.messages.create.return_value = make_cards_response([])
            client = ApiClient(**valid_keys)  # no registry
            cards = client.create_cards(
                lane="reactive",
                model="anything",
                max_tokens=400,
                system=build_system_blocks("sys"),
                messages=build_transcript_messages(["t"], "i"),
            )
            assert cards == []
            mock_sdk.messages.create.assert_called_once()

    def test_process_with_anthropic_routes_openai_compat(self, valid_keys: dict[str, str]) -> None:
        with patch("api.client.Anthropic") as mock_cls:
            mock_cls.return_value = Mock()
            client = ApiClient(**valid_keys, model_registry=_openai_registry())
            with patch("api.client.process_openai") as mock_proc:
                mock_proc.return_value = "openai text"
                out = client.process_with_anthropic("t", stream=False, model="groq")
            assert out == "openai text"
            mock_proc.assert_called_once()


# ---------------------------------------------------------------------------
# Tests: web search (F3)
# ---------------------------------------------------------------------------


class TestWebSearch:
    @pytest.fixture
    def client_with_mock_anthropic(
        self, valid_keys: dict[str, str]
    ) -> Iterator[tuple[ApiClient, Mock]]:
        with patch("api.client.Anthropic") as mock_cls:
            mock_sdk = Mock()
            mock_cls.return_value = mock_sdk
            client = ApiClient(**valid_keys, model_registry=ModelRegistry(AppConfig()))
            yield client, mock_sdk

    def test_build_web_search_tool_variant_by_model(self) -> None:
        assert (
            build_web_search_tool("claude-sonnet-5")["type"]
            == config.ANTHROPIC_WEB_SEARCH_TOOL_TYPE
        )
        assert (
            build_web_search_tool("claude-haiku-4-5")["type"]
            == config.ANTHROPIC_WEB_SEARCH_TOOL_TYPE_BASIC
        )

    def test_web_search_attaches_tool_and_unforced_choice(
        self, client_with_mock_anthropic: tuple[ApiClient, Mock]
    ) -> None:
        client, mock_sdk = client_with_mock_anthropic
        mock_sdk.messages.create.return_value = make_web_search_cards_response(
            [{"type": "answer", "headline": "hi"}]
        )
        client.create_cards(
            lane="reactive",
            model="claude-sonnet-5",
            max_tokens=400,
            system=build_system_blocks("sys"),
            messages=build_transcript_messages(["t"], "i"),
            web_search=True,
        )
        kwargs = mock_sdk.messages.create.call_args.kwargs
        tool_types = {t.get("type") for t in kwargs["tools"]}
        assert "web_search_20260209" in tool_types
        # emit_cards must NOT be force-selected (model needs to search first).
        assert "tool_choice" not in kwargs
        # thinking stays adaptive (not disabled) when searching.
        assert "thinking" not in kwargs

    def test_web_search_cards_marked_knowledge(
        self, client_with_mock_anthropic: tuple[ApiClient, Mock]
    ) -> None:
        client, mock_sdk = client_with_mock_anthropic
        mock_sdk.messages.create.return_value = make_web_search_cards_response(
            [{"type": "answer", "headline": "searched", "source": "transcript"}]
        )
        cards = client.create_cards(
            lane="reactive",
            model="claude-sonnet-5",
            max_tokens=400,
            system=build_system_blocks("sys"),
            messages=build_transcript_messages(["t"], "i"),
            web_search=True,
        )
        assert cards[0].source == "knowledge"

    def test_web_search_kb_grounded_source_preserved(
        self, client_with_mock_anthropic: tuple[ApiClient, Mock]
    ) -> None:
        client, mock_sdk = client_with_mock_anthropic
        mock_sdk.messages.create.return_value = make_web_search_cards_response(
            [{"type": "answer", "headline": "kb", "source": "kb"}]
        )
        cards = client.create_cards(
            lane="reactive",
            model="claude-sonnet-5",
            max_tokens=400,
            system=build_system_blocks("sys"),
            messages=build_transcript_messages(["t"], "i"),
            web_search=True,
        )
        assert cards[0].source == "kb"

    def test_web_search_resumes_on_pause_turn(
        self, client_with_mock_anthropic: tuple[ApiClient, Mock]
    ) -> None:
        client, mock_sdk = client_with_mock_anthropic
        mock_sdk.messages.create.side_effect = [
            make_pause_turn_response(),
            make_web_search_cards_response([{"type": "answer", "headline": "done"}]),
        ]
        cards = client.create_cards(
            lane="reactive",
            model="claude-sonnet-5",
            max_tokens=400,
            system=build_system_blocks("sys"),
            messages=build_transcript_messages(["t"], "i"),
            web_search=True,
        )
        assert mock_sdk.messages.create.call_count == 2
        assert cards[0].headline == "done"

    def test_web_search_text_json_fallback(
        self, client_with_mock_anthropic: tuple[ApiClient, Mock]
    ) -> None:
        """No emit_cards tool_use → parse the text block as JSON."""
        client, mock_sdk = client_with_mock_anthropic
        mock_sdk.messages.create.return_value = make_web_search_cards_response(
            None,  # no tool_use block
            text='{"cards": [{"type": "answer", "headline": "from text"}]}',
        )
        cards = client.create_cards(
            lane="reactive",
            model="claude-sonnet-5",
            max_tokens=400,
            system=build_system_blocks("sys"),
            messages=build_transcript_messages(["t"], "i"),
            web_search=True,
        )
        assert len(cards) == 1
        assert cards[0].headline == "from text"

    def test_process_with_anthropic_web_search_attaches_tool(
        self, valid_keys: dict[str, str]
    ) -> None:
        with patch("api.client.Anthropic") as mock_cls:
            mock_sdk = Mock()
            mock_cls.return_value = mock_sdk
            mock_sdk.messages.create.return_value = make_text_response("ok")
            client = ApiClient(**valid_keys, model_registry=ModelRegistry(AppConfig()))
            client.process_with_anthropic(
                "text", stream=False, model="claude-sonnet-5", web_search=True
            )
            kwargs = mock_sdk.messages.create.call_args.kwargs
            assert kwargs["tools"][0]["name"] == "web_search"
            # thinking not disabled while searching
            assert "thinking" not in kwargs


# ---------------------------------------------------------------------------
# Tests: transcribe_with_deepgram — regression
# ---------------------------------------------------------------------------


class TestTranscribeWithDeeepgram:
    """Regression tests for transcribe_with_deepgram."""

    def test_transcribe_raises_on_empty_audio(self, api_client: ApiClient) -> None:
        with pytest.raises(ValueError, match="Audio data cannot be empty"):
            api_client.transcribe_with_deepgram(audio_data=b"", sample_rate=16000)

    def test_transcribe_raises_on_missing_deepgram_key(self, valid_keys: dict[str, str]) -> None:
        client = ApiClient(**valid_keys)
        client.deepgram_api_key = ""

        with pytest.raises(ValueError, match="Deepgram API key not set"):
            client.transcribe_with_deepgram(audio_data=b"\x00\x01", sample_rate=16000)

    def test_transcribe_delegates_to_deepgram_utils(self, api_client: ApiClient) -> None:
        with patch("api.client.transcribe_with_deepgram") as mock_transcribe:
            mock_transcribe.return_value = "hello world"

            result = api_client.transcribe_with_deepgram(
                audio_data=b"\x00\x01\x02",
                sample_rate=44100,
            )

        assert result == "hello world"
        mock_transcribe.assert_called_once_with(
            api_client.deepgram_api_key,
            b"\x00\x01\x02",
            44100,
        )
