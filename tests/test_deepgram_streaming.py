"""Tests for the Deepgram WebSocket streaming client (DAR2-23, SDK v4).

Tests DeepgramStreamingClient with the Deepgram SDK fully mocked, verifying:
- nova-3 live options (multichannel, endpointing, utterance_end_ms, keyterms)
- int16 multichannel PCM pass-through in send_audio
- ME/THEM speaker attribution and prefixed transcript accumulation
- UtteranceEnd fired from the real UtteranceEnd event
- connection lifecycle (connect, failed connect, disconnect, reconnect)
- drop-OLDEST reconnect queue behavior
"""

import queue
import threading
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import numpy as np
import pytest

import config
from api.deepgram_streaming import DeepgramStreamingClient, _build_live_options


API_KEY = "test-api-key-1234567890abcdef1234567890abcdef12345678"


def _result(
    transcript: str,
    *,
    is_final: bool = False,
    channel: int = 0,
    total_channels: int = 2,
    start: float = 0.0,
    duration: float = 0.0,
    words: list[SimpleNamespace] | None = None,
) -> SimpleNamespace:
    """Build a fake SDK v4 LiveResultResponse."""
    return SimpleNamespace(
        is_final=is_final,
        speech_final=False,
        start=start,
        duration=duration,
        channel_index=[channel, total_channels],
        channel=SimpleNamespace(
            alternatives=[SimpleNamespace(transcript=transcript, words=words)]
        ),
    )


@pytest.fixture
def client() -> DeepgramStreamingClient:
    """Create a DeepgramStreamingClient without connecting."""
    return DeepgramStreamingClient(api_key=API_KEY)


@pytest.fixture
def mock_sdk():
    """Mock the Deepgram v4 SDK client factory."""
    with patch("api.deepgram_streaming.DeepgramClient") as mock_dg_cls:
        mock_ws = MagicMock()
        mock_ws.start.return_value = True
        mock_ws.send.return_value = True
        mock_ws.finish.return_value = True

        mock_dg = MagicMock()
        mock_dg.listen.websocket.v.return_value = mock_ws
        mock_dg_cls.return_value = mock_dg

        yield {"class": mock_dg_cls, "instance": mock_dg, "ws": mock_ws}


# ============================================================================
# Live options
# ============================================================================


class TestLiveOptions:
    """The exact nova-3 option set required by the STT contract."""

    def test_options_match_contract(self):
        opts = _build_live_options(
            sample_rate=16000, channels=2, keyterms=["Redis", "OpenShift"]
        ).to_dict()

        assert opts["model"] == "nova-3"
        assert opts["language"] == "en-US"
        assert opts["encoding"] == "linear16"
        assert opts["sample_rate"] == 16000
        assert opts["channels"] == 2
        assert opts["multichannel"] is True
        assert opts["interim_results"] is True
        assert opts["smart_format"] is True
        assert opts["punctuate"] is True
        assert opts["endpointing"] == 300
        assert opts["utterance_end_ms"] == "1000"
        assert opts["keyterm"] == ["Redis", "OpenShift"]

    def test_no_keyterms_omits_param(self):
        opts = _build_live_options(sample_rate=16000, channels=2, keyterms=None)
        assert opts.keyterm is None

    def test_mono_disables_multichannel(self):
        opts = _build_live_options(sample_rate=16000, channels=1, keyterms=None)
        assert opts.multichannel is False
        assert opts.channels == 1


# ============================================================================
# Audio conversion
# ============================================================================


class TestAudioConversion:
    """int16 multichannel pass-through and float fallback."""

    def test_int16_stereo_interleaved_passthrough(self):
        """int16 (frames, 2) chunks are sent as interleaved PCM, both channels."""
        chunk = np.array([[1, -1], [2, -2], [3, -3]], dtype=np.int16)
        result = DeepgramStreamingClient._to_pcm_bytes(chunk)

        decoded = np.frombuffer(result, dtype=np.int16)
        np.testing.assert_array_equal(decoded, [1, -1, 2, -2, 3, -3])

    def test_int16_mono_passthrough(self):
        chunk = np.array([10, 20, -30], dtype=np.int16)
        result = DeepgramStreamingClient._to_pcm_bytes(chunk)
        decoded = np.frombuffer(result, dtype=np.int16)
        np.testing.assert_array_equal(decoded, chunk)

    def test_float_input_scaled_and_clipped(self):
        chunk = np.array([0.0, 0.5, -0.5, 2.0, -3.0], dtype=np.float32)
        result = DeepgramStreamingClient._to_pcm_bytes(chunk)
        decoded = np.frombuffer(result, dtype=np.int16)
        assert decoded[0] == 0
        assert decoded[1] == 16383
        assert decoded[2] == -16383
        assert decoded[3] == 32767  # clipped
        assert decoded[4] == -32767  # clipped

    def test_typical_recorder_chunk_size(self):
        """A (1600, 2) int16 chunk produces 1600*2*2 bytes."""
        chunk = np.zeros((1600, 2), dtype=np.int16)
        assert len(DeepgramStreamingClient._to_pcm_bytes(chunk)) == 6400

    def test_empty_array(self):
        assert DeepgramStreamingClient._to_pcm_bytes(np.array([], dtype=np.int16)) == b""


# ============================================================================
# Transcript callbacks + speaker attribution
# ============================================================================


class TestTranscriptCallbacks:
    def test_final_transcript_channel0_is_me(self, client):
        received = []
        client._on_final_transcript = (
            lambda text, speaker, start, duration: received.append((text, speaker))
        )

        client._handle_transcript(None, result=_result("Hello", is_final=True, channel=0))

        assert received == [("Hello", "ME")]
        assert client._final_segments == ["ME: Hello"]

    def test_final_transcript_channel1_is_them(self, client):
        received = []
        client._on_final_transcript = (
            lambda text, speaker, start, duration: received.append((text, speaker))
        )

        client._handle_transcript(None, result=_result("Hi there", is_final=True, channel=1))

        assert received == [("Hi there", "THEM")]
        assert client._final_segments == ["THEM: Hi there"]

    def test_interim_transcript_carries_speaker(self, client):
        received = []
        client._on_interim_transcript = lambda text, speaker: received.append((text, speaker))

        client._handle_transcript(None, result=_result("Hello wor", channel=1))

        assert received == [("Hello wor", "THEM")]
        assert client._final_segments == []  # interim not accumulated

    def test_mono_client_reports_no_speaker(self):
        mono = DeepgramStreamingClient(api_key=API_KEY, channels=1)
        received = []
        mono._on_final_transcript = (
            lambda text, speaker, start, duration: received.append((text, speaker))
        )

        mono._handle_transcript(
            None, result=_result("Hello", is_final=True, channel=0, total_channels=1)
        )

        assert received == [("Hello", None)]
        assert mono._final_segments == ["Hello"]  # no prefix without attribution

    def test_empty_transcript_ignored(self, client):
        client._handle_transcript(None, result=_result("", is_final=True))
        assert client._final_segments == []

    def test_malformed_result_ignored(self, client):
        client._handle_transcript(None, result=SimpleNamespace())  # no channel attr
        client._handle_transcript(
            None, result=SimpleNamespace(channel=SimpleNamespace(alternatives=[]))
        )
        assert client._final_segments == []

    def test_no_callbacks_set_still_accumulates(self, client):
        client._handle_transcript(None, result=_result("Test", is_final=True, channel=0))
        assert client._final_segments == ["ME: Test"]


class TestUtteranceEnd:
    """UtteranceEnd fires from the REAL Deepgram UtteranceEnd event."""

    def test_utterance_end_delivers_full_transcript(self, client):
        received = []
        client._on_utterance_end = received.append

        client._handle_transcript(
            None, result=_result("How does it work?", is_final=True, channel=1)
        )
        client._handle_transcript(None, result=_result("Let me explain.", is_final=True, channel=0))
        client._handle_utterance_end(None, utterance_end=SimpleNamespace(last_word_end=4.2))

        assert received == ["THEM: How does it work?\nME: Let me explain."]

    def test_speech_final_does_not_fire_utterance_end(self, client):
        """speech_final on a transcript result must NOT trigger the callback."""
        received = []
        client._on_utterance_end = received.append

        result = _result("Hello", is_final=True)
        result.speech_final = True
        client._handle_transcript(None, result=result)

        assert received == []


class TestResultTiming:
    """Widened on_final_transcript carries (start, duration) seconds."""

    def test_top_level_start_duration_passed_through(self, client):
        received = []
        client._on_final_transcript = (
            lambda text, speaker, start, duration: received.append((start, duration))
        )

        client._handle_transcript(
            None, result=_result("Hello", is_final=True, channel=0, start=12.5, duration=1.5)
        )

        assert received == [(12.5, 1.5)]

    def test_falls_back_to_word_timings_when_top_level_absent(self, client):
        received = []
        client._on_final_transcript = (
            lambda text, speaker, start, duration: received.append((start, duration))
        )
        words = [
            SimpleNamespace(word="hello", start=3.0, end=3.4),
            SimpleNamespace(word="there", start=3.4, end=4.1),
        ]

        client._handle_transcript(
            None,
            result=_result("hello there", is_final=True, channel=0, words=words),
        )

        assert len(received) == 1
        start, duration = received[0]
        assert start == pytest.approx(3.0)
        assert duration == pytest.approx(1.1)

    def test_no_timing_available_defaults_to_zero(self, client):
        received = []
        client._on_final_transcript = (
            lambda text, speaker, start, duration: received.append((start, duration))
        )

        client._handle_transcript(None, result=_result("Hello", is_final=True, channel=0))

        assert received == [(0.0, 0.0)]

    def test_interim_transcript_does_not_require_timing(self, client):
        """Interim callback keeps its original 2-arg shape — no timing needed."""
        received = []
        client._on_interim_transcript = lambda text, speaker: received.append((text, speaker))

        client._handle_transcript(None, result=_result("Hello wor", channel=1))

        assert received == [("Hello wor", "THEM")]


# ============================================================================
# Transcript accumulation
# ============================================================================


class TestTranscriptAccumulation:
    def test_get_full_transcript_joins_with_newlines(self, client):
        client._final_segments = ["ME: First.", "THEM: Second."]
        assert client.get_full_transcript() == "ME: First.\nTHEM: Second."

    def test_get_full_transcript_empty(self, client):
        assert client.get_full_transcript() == ""

    def test_clear_transcript(self, client):
        client._final_segments = ["ME: Some text"]
        client.clear_transcript()
        assert client.get_full_transcript() == ""

    def test_thread_safe_accumulation(self, client):
        errors = []

        def add_segments():
            try:
                for i in range(100):
                    client._handle_transcript(None, result=_result(f"Segment {i}", is_final=True))
            except Exception as e:
                errors.append(e)

        def read_transcript():
            try:
                for _ in range(100):
                    _ = client.get_full_transcript()
            except Exception as e:
                errors.append(e)

        threads = [
            threading.Thread(target=add_segments),
            threading.Thread(target=read_transcript),
        ]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert len(errors) == 0
        assert len(client._final_segments) == 100


# ============================================================================
# Connection lifecycle
# ============================================================================


class TestConnectionLifecycle:
    def test_initial_state(self, client):
        assert not client.is_connected
        assert client._ws is None

    def test_connect_starts_sdk_client(self, mock_sdk):
        client = DeepgramStreamingClient(api_key=API_KEY)
        client.connect()

        assert client.is_connected
        mock_sdk["ws"].start.assert_called_once()
        # All five events registered: Open, Transcript, UtteranceEnd, Close, Error
        assert mock_sdk["ws"].on.call_count == 5
        client.disconnect()

    def test_connect_passes_nova3_options(self, mock_sdk):
        client = DeepgramStreamingClient(api_key=API_KEY, keyterms=["Redis"])
        client.connect()

        options = mock_sdk["ws"].start.call_args[0][0]
        opts = options.to_dict()
        assert opts["model"] == config.DEEPGRAM_MODEL
        assert opts["multichannel"] is True
        assert opts["keyterm"] == ["Redis"]
        client.disconnect()

    def test_failed_connect_fires_error_and_stays_disconnected(self, mock_sdk):
        mock_sdk["ws"].start.return_value = False
        errors = []
        client = DeepgramStreamingClient(api_key=API_KEY, on_error=errors.append)

        client.connect()

        assert not client.is_connected
        assert len(errors) == 1
        # disconnect() after a failed connect must be safe (no leaked threads)
        client.disconnect()
        assert not client.is_connected

    def test_disconnect_finishes_ws(self, mock_sdk):
        client = DeepgramStreamingClient(api_key=API_KEY)
        client.connect()
        assert client.is_connected

        client.disconnect()

        assert not client.is_connected
        assert client._ws is None
        mock_sdk["ws"].finish.assert_called_once()

    def test_double_connect_warns(self, mock_sdk):
        client = DeepgramStreamingClient(api_key=API_KEY)
        client.connect()

        with patch("api.deepgram_streaming.logger") as mock_logger:
            client.connect()
            mock_logger.warning.assert_called()

        client.disconnect()

    def test_connection_state_callbacks(self, mock_sdk):
        states = []
        client = DeepgramStreamingClient(api_key=API_KEY, on_connection_state=states.append)
        client.connect()
        client.disconnect()
        assert states == ["connected", "disconnected"]

    def test_close_while_running_triggers_reconnect(self, mock_sdk):
        client = DeepgramStreamingClient(api_key=API_KEY)
        client.connect()

        with patch.object(client, "_start_reconnect") as mock_reconnect:
            client._handle_close(None, close=SimpleNamespace())
            mock_reconnect.assert_called_once()
        assert not client.is_connected
        client.disconnect()

    def test_close_during_shutdown_does_not_reconnect(self, mock_sdk):
        client = DeepgramStreamingClient(api_key=API_KEY)
        client.connect()
        client._should_stop.set()

        with patch.object(client, "_start_reconnect") as mock_reconnect:
            client._handle_close(None, close=SimpleNamespace())
            mock_reconnect.assert_not_called()
        client.disconnect()


# ============================================================================
# send_audio + reconnect queue
# ============================================================================


class TestSendAudio:
    def test_send_audio_when_connected_sends_bytes(self, mock_sdk):
        client = DeepgramStreamingClient(api_key=API_KEY)
        client.connect()

        chunk = np.ones((1600, 2), dtype=np.int16)
        client.send_audio(chunk)

        mock_sdk["ws"].send.assert_called_with(chunk.tobytes())
        client.disconnect()

    def test_send_audio_when_disconnected_queues(self, client):
        client.send_audio(np.zeros((1600, 2), dtype=np.int16))
        assert not client._reconnect_queue.empty()

    def test_send_audio_when_stopped_drops(self, client):
        client._should_stop.set()
        client.send_audio(np.zeros((1600, 2), dtype=np.int16))
        assert client._reconnect_queue.empty()

    def test_reconnect_queue_drops_oldest_on_overflow(self, client):
        """True drop-OLDEST: newest audio is always kept."""
        client._reconnect_queue = queue.Queue(maxsize=3)

        for i in range(5):
            client._queue_audio(f"chunk-{i}".encode())

        remaining = []
        while not client._reconnect_queue.empty():
            remaining.append(client._reconnect_queue.get_nowait())
        assert remaining == [b"chunk-2", b"chunk-3", b"chunk-4"]

    def test_reconnect_queue_sized_for_30_seconds(self, client):
        """~30 s of audio at 100 ms chunks."""
        assert client._reconnect_queue.maxsize == 300

    def test_drain_reconnect_queue_after_connect(self, mock_sdk):
        client = DeepgramStreamingClient(api_key=API_KEY)
        for i in range(3):
            client._queue_audio(b"audio_" + str(i).encode())

        client.connect()

        # 3 queued chunks flushed on connect
        assert mock_sdk["ws"].send.call_count == 3
        assert client._reconnect_queue.empty()
        client.disconnect()


# ============================================================================
# Error handling
# ============================================================================


class TestErrorHandling:
    def test_ws_error_fires_callback(self, client):
        errors = []
        client._on_error = errors.append

        client._handle_error(None, error="Connection reset by peer")

        assert len(errors) == 1
        assert "Connection reset" in errors[0]

    def test_state_notify(self, client):
        states = []
        client._on_connection_state = states.append
        client._notify_state("connected")
        client._notify_state("reconnecting")
        assert states == ["connected", "reconnecting"]
