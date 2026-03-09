"""Unit tests for ApiClient — BUG-2026-02-09-006.

Verifies that the Anthropic client is lazy-loaded and reused across
multiple calls, rather than being recreated on every API call.

Bug: No client reuse - new Anthropic client created for every API call
Fix: Lazy-loaded @property anthropic_client on ApiClient
"""

from __future__ import annotations

import sys
from collections.abc import Iterator
from pathlib import Path
from unittest.mock import MagicMock, Mock, patch

import pytest


# Ensure project root is on path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from api.client import ApiClient


# ---------------------------------------------------------------------------
# Fixtures
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

        assert first is second, (
            "anthropic_client must return the same instance on every call "
            "(client reuse), not create a new Anthropic() each time."
        )

    def test_anthropic_client_created_exactly_once_across_many_accesses(
        self, mock_anthropic_class: MagicMock, valid_keys: dict[str, str]
    ) -> None:
        """Anthropic() constructor is called exactly once no matter how many accesses."""
        client = ApiClient(**valid_keys)

        for _ in range(10):
            _ = client.anthropic_client

        mock_anthropic_class.assert_called_once()

    def test_internal_anthropic_client_none_before_first_access(
        self, valid_keys: dict[str, str]
    ) -> None:
        """_anthropic_client private attribute must be None right after __init__."""
        client = ApiClient(**valid_keys)

        assert client._anthropic_client is None, (
            "_anthropic_client should be None until first property access "
            "(lazy initialisation confirms no per-call instantiation)."
        )

    def test_internal_anthropic_client_set_after_first_access(
        self, mock_anthropic_class: MagicMock, valid_keys: dict[str, str]
    ) -> None:
        """_anthropic_client must be populated after the first property access."""
        client = ApiClient(**valid_keys)

        _ = client.anthropic_client

        assert client._anthropic_client is not None

    def test_anthropic_client_uses_correct_api_key(
        self, mock_anthropic_class: MagicMock, valid_keys: dict[str, str]
    ) -> None:
        """Client must be constructed with the key passed to ApiClient.__init__."""
        client = ApiClient(**valid_keys)

        _ = client.anthropic_client

        mock_anthropic_class.assert_called_once_with(api_key="test-anthropic-key-abc123")


# ---------------------------------------------------------------------------
# Tests: ApiClient initialisation
# ---------------------------------------------------------------------------


class TestApiClientInit:
    """Verify ApiClient constructor behaviour and validation."""

    def test_init_stores_anthropic_api_key(self, valid_keys: dict[str, str]) -> None:
        """anthropic_api_key attribute must match the provided value."""
        client = ApiClient(**valid_keys)

        assert client.anthropic_api_key == valid_keys["anthropic_api_key"]

    def test_init_stores_deepgram_api_key(self, valid_keys: dict[str, str]) -> None:
        """deepgram_api_key attribute must match the provided value."""
        client = ApiClient(**valid_keys)

        assert client.deepgram_api_key == valid_keys["deepgram_api_key"]

    def test_init_raises_on_missing_anthropic_key(self) -> None:
        """ValueError raised when Anthropic key is empty."""
        with pytest.raises(ValueError, match="Anthropic API key"):
            ApiClient(anthropic_api_key="", deepgram_api_key="valid-deepgram-key")

    def test_init_raises_on_whitespace_anthropic_key(self) -> None:
        """ValueError raised when Anthropic key is whitespace-only."""
        with pytest.raises(ValueError, match="Anthropic API key"):
            ApiClient(anthropic_api_key="   ", deepgram_api_key="valid-deepgram-key")

    def test_init_raises_on_missing_deepgram_key(self) -> None:
        """ValueError raised when Deepgram key is empty."""
        with pytest.raises(ValueError, match="Deepgram API key"):
            ApiClient(anthropic_api_key="valid-anthropic-key", deepgram_api_key="")

    def test_init_raises_on_whitespace_deepgram_key(self) -> None:
        """ValueError raised when Deepgram key is whitespace-only."""
        with pytest.raises(ValueError, match="Deepgram API key"):
            ApiClient(anthropic_api_key="valid-anthropic-key", deepgram_api_key="  ")


# ---------------------------------------------------------------------------
# Tests: process_with_anthropic — regression
# ---------------------------------------------------------------------------


class TestProcessWithAnthropic:
    """Regression tests for process_with_anthropic using the reused client."""

    @pytest.fixture
    def client_with_mock_anthropic(
        self, valid_keys: dict[str, str]
    ) -> Iterator[tuple[ApiClient, MagicMock]]:
        """ApiClient with a fully mocked Anthropic SDK client."""
        with patch("api.client.Anthropic") as mock_cls:
            mock_sdk_client = Mock()
            mock_cls.return_value = mock_sdk_client

            # Configure streaming context manager
            mock_stream_ctx = MagicMock()
            mock_stream_ctx.__enter__ = Mock(return_value=mock_stream_ctx)
            mock_stream_ctx.__exit__ = Mock(return_value=False)
            mock_stream_ctx.text_stream = iter(["Hello", ", ", "world"])
            mock_sdk_client.messages.stream.return_value = mock_stream_ctx

            # Configure non-streaming response
            mock_content_block = Mock()
            mock_content_block.text = "Hello, world"
            mock_response = Mock()
            mock_response.content = [mock_content_block]
            mock_sdk_client.messages.create.return_value = mock_response

            client = ApiClient(**valid_keys)
            yield client, mock_sdk_client

    def test_process_with_anthropic_returns_streamed_text(
        self, client_with_mock_anthropic: tuple[ApiClient, MagicMock]
    ) -> None:
        """process_with_anthropic streams and returns concatenated response text."""
        client, _ = client_with_mock_anthropic

        result = client.process_with_anthropic("test input", stream=True)

        assert result == "Hello, world"

    def test_process_with_anthropic_non_streaming_returns_text(
        self, client_with_mock_anthropic: tuple[ApiClient, MagicMock]
    ) -> None:
        """process_with_anthropic non-streaming returns first content block text."""
        client, _ = client_with_mock_anthropic

        result = client.process_with_anthropic("test input", stream=False)

        assert result == "Hello, world"

    def test_process_with_anthropic_uses_cached_client(self, valid_keys: dict[str, str]) -> None:
        """Multiple process_with_anthropic calls must NOT create new Anthropic instances."""
        with patch("api.client.Anthropic") as mock_cls:
            mock_sdk = Mock()
            mock_cls.return_value = mock_sdk

            # Setup streaming context each call
            def make_stream_ctx() -> MagicMock:
                ctx = MagicMock()
                ctx.__enter__ = Mock(return_value=ctx)
                ctx.__exit__ = Mock(return_value=False)
                ctx.text_stream = iter(["ok"])
                return ctx

            mock_sdk.messages.stream.side_effect = [
                make_stream_ctx(),
                make_stream_ctx(),
            ]

            client = ApiClient(**valid_keys)
            client.process_with_anthropic("first call", stream=True)
            client.process_with_anthropic("second call", stream=True)

            # Anthropic() constructor called exactly once despite two API calls
            mock_cls.assert_called_once()

    def test_process_with_anthropic_applies_prompt_template(
        self, client_with_mock_anthropic: tuple[ApiClient, MagicMock]
    ) -> None:
        """prompt_template is formatted with transcript before sending to API."""
        client, mock_sdk = client_with_mock_anthropic

        client.process_with_anthropic(
            "my transcript",
            prompt_template="Summarise: {transcript}",
            stream=False,
        )

        call_args = mock_sdk.messages.create.call_args
        messages = call_args.kwargs["messages"]
        assert messages[0]["content"] == "Summarise: my transcript"

    def test_process_with_anthropic_raises_on_empty_key(self, valid_keys: dict[str, str]) -> None:
        """ValueError raised when anthropic_api_key is cleared after construction."""
        with patch("api.client.Anthropic"):
            client = ApiClient(**valid_keys)
            client.anthropic_api_key = ""  # Simulate key removal

            with pytest.raises(ValueError, match="Anthropic API key not set"):
                client.process_with_anthropic("test")


# ---------------------------------------------------------------------------
# Tests: transcribe_with_deepgram — regression
# ---------------------------------------------------------------------------


class TestTranscribeWithDeeepgram:
    """Regression tests for transcribe_with_deepgram."""

    def test_transcribe_raises_on_empty_audio(self, api_client: ApiClient) -> None:
        """ValueError raised when audio_data is empty bytes."""
        with pytest.raises(ValueError, match="Audio data cannot be empty"):
            api_client.transcribe_with_deepgram(audio_data=b"", sample_rate=16000)

    def test_transcribe_raises_on_missing_deepgram_key(self, valid_keys: dict[str, str]) -> None:
        """ValueError raised when deepgram_api_key is cleared after construction."""
        client = ApiClient(**valid_keys)
        client.deepgram_api_key = ""  # Simulate key removal

        with pytest.raises(ValueError, match="Deepgram API key not set"):
            client.transcribe_with_deepgram(audio_data=b"\x00\x01", sample_rate=16000)

    def test_transcribe_delegates_to_deepgram_utils(self, api_client: ApiClient) -> None:
        """transcribe_with_deepgram passes key, audio, and sample_rate correctly."""
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
