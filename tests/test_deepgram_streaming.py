"""Tests for Deepgram WebSocket streaming client (DAR2-23).

Tests the DeepgramStreamingClient with mocked Deepgram SDK, verifying:
- Audio format conversion (float32 → int16 PCM)
- Transcript callback dispatch (interim, final, utterance_end)
- Connection lifecycle (connect, disconnect, reconnect)
- Thread safety of send_audio
- Error handling
"""

import sys
import threading
import time
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import numpy as np
import pytest  # noqa: I001


# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from api.deepgram_streaming import DeepgramStreamingClient


# ============================================================================
# Fixtures
# ============================================================================


@pytest.fixture
def mock_deepgram():
    """Mock the Deepgram SDK client."""
    with patch("api.deepgram_streaming.Deepgram") as mock_dg_class:
        mock_dg = MagicMock()
        mock_dg_class.return_value = mock_dg

        # Mock LiveTranscription connection
        mock_connection = MagicMock()
        mock_connection.done = False
        mock_connection.send = MagicMock()
        mock_connection.keep_alive = MagicMock()
        mock_connection.finish = AsyncMock()
        mock_connection.register_handler = MagicMock()

        # Make transcription.live() return the mock connection
        mock_dg.transcription = MagicMock()
        mock_dg.transcription.live = AsyncMock(return_value=mock_connection)

        yield {
            "class": mock_dg_class,
            "instance": mock_dg,
            "connection": mock_connection,
        }


@pytest.fixture
def client():
    """Create a DeepgramStreamingClient without connecting."""
    return DeepgramStreamingClient(
        api_key="test-api-key-1234567890abcdef1234567890abcdef12345678",
        sample_rate=48000,
    )


# ============================================================================
# Audio Format Conversion Tests
# ============================================================================


class TestAudioConversion:
    """Test float32 → int16 PCM byte conversion."""

    def test_mono_float32_to_int16(self):
        """Test mono float32 array converts to int16 bytes."""
        audio = np.array([0.0, 0.5, -0.5, 1.0, -1.0], dtype=np.float32)
        result = DeepgramStreamingClient._to_pcm_bytes(audio)

        assert isinstance(result, bytes)
        # 5 samples * 2 bytes per int16 = 10 bytes
        assert len(result) == 10

        # Verify values
        decoded = np.frombuffer(result, dtype=np.int16)
        assert decoded[0] == 0  # 0.0 → 0
        assert decoded[1] == 16383  # 0.5 * 32767 ≈ 16383
        assert decoded[2] == -16383  # -0.5 * 32767 ≈ -16383
        assert decoded[3] == 32767  # 1.0 → 32767
        assert decoded[4] == -32767  # -1.0 → -32767

    def test_multichannel_takes_first_channel(self):
        """Test multichannel audio extracts first channel only."""
        # 3 frames, 2 channels
        audio = np.array([[0.5, -0.5], [0.25, -0.25], [0.75, -0.75]], dtype=np.float32)
        result = DeepgramStreamingClient._to_pcm_bytes(audio)

        # Should be 3 samples (mono)
        decoded = np.frombuffer(result, dtype=np.int16)
        assert len(decoded) == 3
        # First channel values
        assert decoded[0] == int(0.5 * 32767)
        assert decoded[1] == int(0.25 * 32767)
        assert decoded[2] == int(0.75 * 32767)

    def test_clipping_beyond_range(self):
        """Test values beyond [-1, 1] are clipped."""
        audio = np.array([2.0, -3.0, 1.5], dtype=np.float32)
        result = DeepgramStreamingClient._to_pcm_bytes(audio)

        decoded = np.frombuffer(result, dtype=np.int16)
        assert decoded[0] == 32767  # clipped to 1.0
        assert decoded[1] == -32767  # clipped to -1.0
        assert decoded[2] == 32767  # clipped to 1.0

    def test_empty_array(self):
        """Test empty array returns empty bytes."""
        audio = np.array([], dtype=np.float32)
        result = DeepgramStreamingClient._to_pcm_bytes(audio)
        assert result == b""

    def test_typical_recorder_chunk(self):
        """Test with a chunk similar to ContinuousRecorder output."""
        # 48000 frames (1 second at 48kHz), 2 channels
        audio = np.random.uniform(-0.1, 0.1, (48000, 2)).astype(np.float32)
        result = DeepgramStreamingClient._to_pcm_bytes(audio)

        # 48000 mono samples * 2 bytes = 96000 bytes
        assert len(result) == 96000


# ============================================================================
# Transcript Callback Tests
# ============================================================================


class TestTranscriptCallbacks:
    """Test transcript message parsing and callback dispatch."""

    def test_final_transcript_callback(self, client):
        """Test final transcript fires on_final_transcript callback."""
        received = []
        client._on_final_transcript = lambda text: received.append(text)

        result = {
            "is_final": True,
            "speech_final": False,
            "channel": {"alternatives": [{"transcript": "Hello world"}]},
        }
        client._on_message(result)

        assert received == ["Hello world"]
        assert client._final_segments == ["Hello world"]

    def test_interim_transcript_callback(self, client):
        """Test interim transcript fires on_interim_transcript callback."""
        received = []
        client._on_interim_transcript = lambda text: received.append(text)

        result = {
            "is_final": False,
            "speech_final": False,
            "channel": {"alternatives": [{"transcript": "Hello wor"}]},
        }
        client._on_message(result)

        assert received == ["Hello wor"]
        # Interim should NOT be added to final segments
        assert client._final_segments == []

    def test_utterance_end_callback(self, client):
        """Test speech_final fires on_utterance_end with accumulated text."""
        received = []
        client._on_utterance_end = lambda text: received.append(text)
        client._on_final_transcript = lambda text: None  # suppress

        # Simulate multiple final segments
        for text in ["Hello world.", "How are you?"]:
            client._on_message(
                {
                    "is_final": True,
                    "speech_final": False,
                    "channel": {"alternatives": [{"transcript": text}]},
                }
            )

        # Now speech_final fires
        client._on_message(
            {
                "is_final": True,
                "speech_final": True,
                "channel": {"alternatives": [{"transcript": "I am fine."}]},
            }
        )

        assert len(received) == 1
        assert received[0] == "Hello world. How are you? I am fine."

    def test_empty_transcript_ignored(self, client):
        """Test empty transcript strings are ignored."""
        received = []
        client._on_final_transcript = lambda text: received.append(text)

        client._on_message(
            {
                "is_final": True,
                "speech_final": False,
                "channel": {"alternatives": [{"transcript": ""}]},
            }
        )

        assert received == []
        assert client._final_segments == []

    def test_malformed_result_ignored(self, client):
        """Test malformed result dict doesn't crash."""
        client._on_final_transcript = lambda text: None

        # Missing channel key
        client._on_message({"is_final": True})

        # Missing alternatives
        client._on_message({"is_final": True, "channel": {}})

        # Empty alternatives
        client._on_message({"is_final": True, "channel": {"alternatives": []}})

        # All should be silently ignored
        assert client._final_segments == []

    def test_no_callbacks_set(self, client):
        """Test messages are handled gracefully when no callbacks set."""
        # All callbacks are None by default
        result = {
            "is_final": True,
            "speech_final": True,
            "channel": {"alternatives": [{"transcript": "Test"}]},
        }
        # Should not raise
        client._on_message(result)

        # But segments should still accumulate
        assert client._final_segments == ["Test"]


# ============================================================================
# Transcript Accumulation Tests
# ============================================================================


class TestTranscriptAccumulation:
    """Test transcript segment accumulation and retrieval."""

    def test_get_full_transcript(self, client):
        """Test get_full_transcript returns all segments joined."""
        client._final_segments = ["First segment.", "Second segment."]
        assert client.get_full_transcript() == "First segment. Second segment."

    def test_get_full_transcript_empty(self, client):
        """Test get_full_transcript returns empty string when no segments."""
        assert client.get_full_transcript() == ""

    def test_clear_transcript(self, client):
        """Test clear_transcript empties segments."""
        client._final_segments = ["Some text"]
        client.clear_transcript()
        assert client._final_segments == []
        assert client.get_full_transcript() == ""

    def test_thread_safe_accumulation(self, client):
        """Test segment accumulation is thread-safe."""
        errors = []

        def add_segments():
            try:
                for i in range(100):
                    client._on_message(
                        {
                            "is_final": True,
                            "speech_final": False,
                            "channel": {"alternatives": [{"transcript": f"Segment {i}"}]},
                        }
                    )
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
# Connection State Tests
# ============================================================================


class TestConnectionState:
    """Test connection state management."""

    def test_initial_state(self, client):
        """Test initial state is disconnected."""
        assert not client.is_connected
        assert client._connection is None
        assert client._loop_thread is None

    def test_send_audio_when_disconnected(self, client):
        """Test send_audio queues audio when not connected."""
        audio = np.zeros(4800, dtype=np.float32)
        client.send_audio(audio)

        # Audio should be queued
        assert not client._reconnect_queue.empty()

    def test_send_audio_when_stopped(self, client):
        """Test send_audio does nothing when stopped."""
        client._should_stop.set()
        audio = np.zeros(4800, dtype=np.float32)
        client.send_audio(audio)

        # Audio should NOT be queued
        assert client._reconnect_queue.empty()


# ============================================================================
# Connection Lifecycle Tests (with mocked SDK)
# ============================================================================


class TestConnectionLifecycle:
    """Test connect/disconnect with mocked Deepgram SDK."""

    def test_connect_creates_thread(self, mock_deepgram):
        """Test connect() starts a daemon thread."""
        client = DeepgramStreamingClient(
            api_key="test-api-key-1234567890abcdef1234567890abcdef12345678",
        )

        # Simulate immediate connection success
        original_run_loop = client._run_loop

        def mock_run_loop():
            client._connected.set()
            # Keep running briefly
            time.sleep(0.5)

        client._run_loop = mock_run_loop
        client.connect()

        assert client._loop_thread is not None
        assert client._loop_thread.daemon is True
        assert client._loop_thread.is_alive()

        # Cleanup
        client._should_stop.set()
        client._loop_thread.join(timeout=2)

    def test_disconnect_stops_thread(self, mock_deepgram):
        """Test disconnect() stops the event loop thread."""
        client = DeepgramStreamingClient(
            api_key="test-api-key-1234567890abcdef1234567890abcdef12345678",
        )

        # Mock a running state
        def mock_run_loop():
            client._connected.set()
            while not client._should_stop.is_set():
                time.sleep(0.05)

        client._run_loop = mock_run_loop
        client.connect()
        assert client.is_connected

        client.disconnect()
        assert not client.is_connected
        assert client._connection is None

    def test_double_connect_warns(self, mock_deepgram):
        """Test calling connect() twice logs a warning."""
        client = DeepgramStreamingClient(
            api_key="test-api-key-1234567890abcdef1234567890abcdef12345678",
        )

        def mock_run_loop():
            client._connected.set()
            while not client._should_stop.is_set():
                time.sleep(0.05)

        client._run_loop = mock_run_loop
        client.connect()

        # Second connect should warn and return early
        with patch("api.deepgram_streaming.logger") as mock_logger:
            client.connect()
            mock_logger.warning.assert_called()

        client.disconnect()


# ============================================================================
# Error Handling Tests
# ============================================================================


class TestErrorHandling:
    """Test error handling paths."""

    def test_on_ws_error_fires_callback(self, client):
        """Test WebSocket error fires on_error callback."""
        errors = []
        client._on_error = lambda err: errors.append(err)

        client._on_ws_error("Connection reset by peer")

        assert len(errors) == 1
        assert "Connection reset" in errors[0]

    def test_on_close_clears_connected(self, client):
        """Test on_close clears the connected event."""
        client._connected.set()
        client._on_close(1000)
        assert not client.is_connected

    def test_connection_state_callback(self, client):
        """Test connection state changes fire the callback."""
        states = []
        client._on_connection_state = lambda state: states.append(state)

        client._notify_state("connected")
        client._notify_state("disconnected")
        client._notify_state("reconnecting")

        assert states == ["connected", "disconnected", "reconnecting"]


# ============================================================================
# Reconnect Queue Tests
# ============================================================================


class TestReconnectQueue:
    """Test audio queuing during reconnection."""

    def test_drain_reconnect_queue(self, client):
        """Test queued audio is drained after reconnect."""
        # Queue some audio
        for i in range(3):
            client._reconnect_queue.put(b"audio_chunk_" + str(i).encode())

        # Mock connection
        mock_conn = MagicMock()
        client._connection = mock_conn

        client._drain_reconnect_queue()

        # All chunks should have been sent
        assert mock_conn.send.call_count == 3
        assert client._reconnect_queue.empty()

    def test_send_audio_queues_when_disconnected(self, client):
        """Test audio is queued when connection is not ready."""
        audio = np.array([0.5, -0.5], dtype=np.float32)
        client.send_audio(audio)

        assert not client._reconnect_queue.empty()
        queued = client._reconnect_queue.get_nowait()
        assert isinstance(queued, bytes)


# ============================================================================
# Main
# ============================================================================

if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])
