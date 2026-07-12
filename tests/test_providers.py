"""Unit tests for api.providers — model registry + OpenAI-compat adapter (F2).

The OpenAI SDK is fully mocked; no real network calls are made.
"""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import MagicMock, Mock, patch

import pytest


sys.path.insert(0, str(Path(__file__).parent.parent))

from api.providers import (
    ModelRegistry,
    ProviderSpec,
    create_cards_openai,
    extract_json_object,
    process_openai,
    to_openai_messages,
)
from storage.app_config import AppConfig, CustomEndpointConfig


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _endpoint(**kw) -> CustomEndpointConfig:
    base = {
        "id": "groq",
        "label": "Groq Llama",
        "base_url": "https://api.groq.com/openai/v1",
        "model_name": "llama-3.3-70b",
        "api_key": "gsk_secret",
    }
    base.update(kw)
    return CustomEndpointConfig(**base)


def _spec(**kw) -> ProviderSpec:
    base = {
        "id": "groq",
        "label": "Groq Llama",
        "provider": "openai_compat",
        "model_name": "llama-3.3-70b",
        "base_url": "https://api.groq.com/openai/v1",
        "api_key": "gsk_secret",
    }
    base.update(kw)
    return ProviderSpec(**base)


def _tool_response(cards: list[dict]) -> Mock:
    import json

    fn = Mock()
    fn.name = "emit_cards"
    fn.arguments = json.dumps({"cards": cards})
    call = Mock()
    call.function = fn
    message = Mock()
    message.tool_calls = [call]
    choice = Mock()
    choice.message = message
    resp = Mock()
    resp.choices = [choice]
    return resp


def _text_response(text: str) -> Mock:
    message = Mock()
    message.tool_calls = []
    message.content = text
    choice = Mock()
    choice.message = message
    resp = Mock()
    resp.choices = [choice]
    return resp


# ---------------------------------------------------------------------------
# ModelRegistry
# ---------------------------------------------------------------------------


class TestModelRegistry:
    def test_list_includes_anthropic_builtins_always_available(self) -> None:
        models = ModelRegistry(AppConfig()).list()
        by_id = {m["id"]: m for m in models}
        assert by_id["claude-sonnet-5"]["label"] == "Claude Sonnet 5"
        assert by_id["claude-sonnet-5"]["provider"] == "anthropic"
        assert by_id["claude-sonnet-5"]["available"] is True
        assert by_id["claude-sonnet-5"]["supports_web_search"] is True
        assert by_id["claude-haiku-4-5"]["label"] == "Claude Haiku 4.5"

    def test_list_includes_custom_endpoints_without_web_search(self) -> None:
        models = ModelRegistry(AppConfig(custom_endpoints=[_endpoint()])).list()
        by_id = {m["id"]: m for m in models}
        assert by_id["groq"]["provider"] == "openai_compat"
        assert by_id["groq"]["model_name"] == "llama-3.3-70b"
        assert by_id["groq"]["supports_web_search"] is False
        assert by_id["groq"]["available"] is True

    def test_list_never_exposes_api_keys(self) -> None:
        models = ModelRegistry(AppConfig(custom_endpoints=[_endpoint()])).list()
        for m in models:
            assert "api_key" not in m

    def test_endpoint_without_base_url_is_unavailable(self) -> None:
        models = ModelRegistry(AppConfig(custom_endpoints=[_endpoint(base_url="")])).list()
        by_id = {m["id"]: m for m in models}
        assert by_id["groq"]["available"] is False

    def test_resolve_anthropic_builtin(self) -> None:
        spec = ModelRegistry(AppConfig()).resolve("claude-sonnet-5")
        assert spec is not None
        assert spec.provider == "anthropic"
        assert spec.model_name == "claude-sonnet-5"

    def test_resolve_custom_endpoint_carries_base_url_and_key(self) -> None:
        spec = ModelRegistry(AppConfig(custom_endpoints=[_endpoint()])).resolve("groq")
        assert spec is not None
        assert spec.provider == "openai_compat"
        assert spec.base_url == "https://api.groq.com/openai/v1"
        assert spec.api_key == "gsk_secret"

    def test_resolve_unknown_returns_none(self) -> None:
        assert ModelRegistry(AppConfig()).resolve("mystery-model") is None

    def test_custom_endpoints_kwarg_overrides_app_config(self) -> None:
        reg = ModelRegistry(custom_endpoints=[_endpoint(id="local")])
        assert reg.resolve("local") is not None
        assert reg.resolve("groq") is None


# ---------------------------------------------------------------------------
# extract_json_object / to_openai_messages
# ---------------------------------------------------------------------------


class TestHelpers:
    def test_extract_plain_json(self) -> None:
        assert extract_json_object('{"cards": []}') == {"cards": []}

    def test_extract_json_from_markdown_fence(self) -> None:
        text = '```json\n{"cards": [{"headline": "hi"}]}\n```'
        assert extract_json_object(text) == {"cards": [{"headline": "hi"}]}

    def test_extract_json_embedded_in_prose(self) -> None:
        text = 'Here you go: {"cards": []} hope that helps'
        assert extract_json_object(text) == {"cards": []}

    def test_extract_json_returns_none_on_garbage(self) -> None:
        assert extract_json_object("no json here") is None
        assert extract_json_object("") is None

    def test_extract_json_rejects_non_object(self) -> None:
        assert extract_json_object("[1, 2, 3]") is None

    def test_to_openai_messages_flattens_blocks(self) -> None:
        system = [{"type": "text", "text": "sys"}]
        messages = [
            {
                "role": "user",
                "content": [{"type": "text", "text": "a"}, {"type": "text", "text": "b"}],
            },
            {"role": "user", "content": [{"type": "text", "text": "do it"}]},
        ]
        out = to_openai_messages(system, messages)
        assert out[0] == {"role": "system", "content": "sys"}
        assert out[1]["content"] == "a\n\nb"
        assert out[2]["content"] == "do it"


# ---------------------------------------------------------------------------
# create_cards_openai
# ---------------------------------------------------------------------------


class TestCreateCardsOpenai:
    @pytest.fixture
    def mock_openai(self):
        with patch("api.providers.OpenAI") as mock_cls:
            client = MagicMock()
            mock_cls.return_value = client
            yield mock_cls, client

    def _system(self):
        return [{"type": "text", "text": "sys"}]

    def _messages(self):
        return [{"role": "user", "content": [{"type": "text", "text": "instruction"}]}]

    def test_function_calling_path_parses_cards(self, mock_openai) -> None:
        _, client = mock_openai
        client.chat.completions.create.return_value = _tool_response(
            [{"type": "answer", "headline": "The answer"}]
        )
        cards = create_cards_openai(
            _spec(),
            lane="reactive",
            card_lane="reactive",
            max_tokens=400,
            system=self._system(),
            messages=self._messages(),
        )
        assert len(cards) == 1
        assert cards[0].headline == "The answer"
        # Forced function tool_choice was used.
        kwargs = client.chat.completions.create.call_args.kwargs
        assert kwargs["tool_choice"]["function"]["name"] == "emit_cards"

    def test_dummy_api_key_when_empty(self, mock_openai) -> None:
        mock_cls, client = mock_openai
        client.chat.completions.create.return_value = _tool_response([])
        create_cards_openai(
            _spec(api_key=""),
            lane="reactive",
            card_lane="reactive",
            max_tokens=400,
            system=self._system(),
            messages=self._messages(),
        )
        assert mock_cls.call_args.kwargs["api_key"] == "dummy"

    def test_watcher_lane_fails_fast(self, mock_openai) -> None:
        import config

        mock_cls, client = mock_openai
        client.chat.completions.create.return_value = _tool_response([])
        create_cards_openai(
            _spec(),
            lane="watcher",
            card_lane="proactive",
            max_tokens=400,
            system=self._system(),
            messages=self._messages(),
        )
        kwargs = mock_cls.call_args.kwargs
        assert kwargs["max_retries"] == config.OPENAI_COMPAT_WATCHER_MAX_RETRIES
        assert kwargs["timeout"] == config.OPENAI_COMPAT_WATCHER_TIMEOUT_S

    def test_falls_back_to_json_mode_on_tool_exception(self, mock_openai) -> None:
        _, client = mock_openai
        client.chat.completions.create.side_effect = [
            RuntimeError("no function calling on this proxy"),
            _text_response('{"cards": [{"type": "answer", "headline": "JSON answer"}]}'),
        ]
        cards = create_cards_openai(
            _spec(),
            lane="reactive",
            card_lane="reactive",
            max_tokens=400,
            system=self._system(),
            messages=self._messages(),
        )
        assert len(cards) == 1
        assert cards[0].headline == "JSON answer"
        assert client.chat.completions.create.call_count == 2

    def test_falls_back_to_json_mode_when_tool_call_absent(self, mock_openai) -> None:
        _, client = mock_openai
        client.chat.completions.create.side_effect = [
            _text_response("no tool call here"),
            _text_response('{"cards": [{"type": "answer", "headline": "recovered"}]}'),
        ]
        cards = create_cards_openai(
            _spec(),
            lane="reactive",
            card_lane="reactive",
            max_tokens=400,
            system=self._system(),
            messages=self._messages(),
        )
        assert len(cards) == 1
        assert cards[0].headline == "recovered"

    def test_json_fallback_unparseable_returns_empty(self, mock_openai) -> None:
        _, client = mock_openai
        client.chat.completions.create.side_effect = [
            RuntimeError("boom"),
            _text_response("still not json"),
        ]
        cards = create_cards_openai(
            _spec(),
            lane="reactive",
            card_lane="reactive",
            max_tokens=400,
            system=self._system(),
            messages=self._messages(),
        )
        assert cards == []


# ---------------------------------------------------------------------------
# process_openai
# ---------------------------------------------------------------------------


class TestProcessOpenai:
    @pytest.fixture
    def mock_openai(self):
        with patch("api.providers.OpenAI") as mock_cls:
            client = MagicMock()
            mock_cls.return_value = client
            yield mock_cls, client

    def _stream_chunk(self, text: str) -> Mock:
        delta = Mock()
        delta.content = text
        choice = Mock()
        choice.delta = delta
        chunk = Mock()
        chunk.choices = [choice]
        return chunk

    def test_streaming_joins_chunks_and_invokes_callback(self, mock_openai) -> None:
        _, client = mock_openai
        client.chat.completions.create.return_value = iter(
            [self._stream_chunk("Hel"), self._stream_chunk("lo")]
        )
        seen: list[str] = []
        result = process_openai(
            _spec(),
            lane="background",
            max_tokens=500,
            system=[{"type": "text", "text": "sys"}],
            messages=[{"role": "user", "content": [{"type": "text", "text": "hi"}]}],
            stream=True,
            callback=seen.append,
        )
        assert result == "Hello"
        assert seen == ["Hel", "lo"]

    def test_non_streaming_returns_message_content(self, mock_openai) -> None:
        _, client = mock_openai
        client.chat.completions.create.return_value = _text_response("full answer")
        result = process_openai(
            _spec(),
            lane="background",
            max_tokens=500,
            system=[{"type": "text", "text": "sys"}],
            messages=[{"role": "user", "content": [{"type": "text", "text": "hi"}]}],
            stream=False,
        )
        assert result == "full answer"
