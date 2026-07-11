"""Tests for AppController <-> MeetingStore integration (DAR2-25)."""

import asyncio
from pathlib import Path
from unittest.mock import Mock, patch

import pytest

from app_controller import AppController
from storage.meeting_store import MeetingStore


@pytest.fixture
def tmp_store(tmp_path: Path) -> MeetingStore:
    """Create a MeetingStore with a temporary directory."""
    return MeetingStore(base_dir=tmp_path / "meetings")


@pytest.fixture
def controller(tmp_store: MeetingStore):
    """Create an AppController with mocked recorder and a temp MeetingStore."""
    with (
        patch("app_controller.ContinuousRecorder") as mock_rec_cls,
        patch("app_controller.ApiClient"),
    ):
        mock_rec = Mock()
        mock_rec.is_recording = False
        mock_rec.sample_rate = 16000
        mock_rec.start_recording.return_value = True
        mock_rec.stop_recording.return_value = True
        mock_rec_cls.return_value = mock_rec

        ctrl = AppController()
        ctrl._meeting_store = tmp_store
        yield ctrl


class TestMeetingLifecycle:
    """Test that streaming start/stop creates and finalizes meetings."""

    def test_start_streaming_creates_meeting(
        self, controller: AppController, tmp_store: MeetingStore
    ):
        """start_streaming should create a meeting row when store is set."""
        controller._streaming_client = None

        with patch("app_controller.DeepgramStreamingClient") as mock_dg_cls:
            mock_dg = Mock()
            mock_dg.is_connected = True
            mock_dg_cls.return_value = mock_dg

            controller.start_streaming()

            assert controller._active_meeting_id is not None
            meeting = tmp_store.get_meeting(controller._active_meeting_id)
            assert meeting is not None
            assert meeting.end_time is None

    def test_stop_streaming_ends_meeting(self, controller: AppController, tmp_store: MeetingStore):
        """stop_streaming should set end_time on the active meeting."""
        meeting_id = tmp_store.start_meeting(title="Test")
        controller._active_meeting_id = meeting_id

        mock_client = Mock()
        mock_client.get_full_transcript.return_value = "Hello world"
        controller._streaming_client = mock_client

        controller.stop_streaming()

        meeting = tmp_store.get_meeting(meeting_id)
        assert meeting is not None
        assert meeting.end_time is not None
        assert controller._active_meeting_id is None

    def test_stop_streaming_without_meeting_is_safe(self, controller: AppController):
        """stop_streaming without a meeting ID should not crash."""
        controller._active_meeting_id = None
        controller._streaming_client = None
        result = controller.stop_streaming()
        assert result == ""

    def test_failed_connect_disconnects_client(self, controller: AppController):
        """A failed WebSocket connect must call disconnect() (no thread leak)."""
        with patch("app_controller.DeepgramStreamingClient") as mock_dg_cls:
            mock_dg = Mock()
            mock_dg.is_connected = False
            mock_dg_cls.return_value = mock_dg

            assert controller.start_streaming() is False
            mock_dg.disconnect.assert_called_once()
            assert controller._streaming_client is None


class TestSessionScopedCapture:
    """Capture is session-scoped: recorder + streaming tied to the meeting."""

    def test_start_meeting_clears_stale_transcript(self, controller: AppController):
        """The stale-transcript bug: start_meeting must clear old content."""
        controller.start_streaming = Mock(return_value=True)
        controller.current_transcript = "stale text from last meeting"

        loop = asyncio.new_event_loop()
        loop.run_until_complete(controller.start_meeting())
        assert controller.current_transcript == ""
        if controller._timer_task:
            controller._timer_task.cancel()
        loop.close()

    def test_stop_meeting_stops_streaming_and_recorder(self, controller: AppController):
        controller.start_streaming = Mock(return_value=True)
        controller.stop_streaming = Mock(return_value="")
        controller.recorder.is_recording = True

        loop = asyncio.new_event_loop()
        loop.run_until_complete(controller.start_meeting())
        loop.run_until_complete(controller.stop_meeting())
        loop.close()

        controller.stop_streaming.assert_called_once()
        controller.recorder.stop_recording.assert_called_once()

    def test_reset_to_idle_clears_transcript(self, controller: AppController):
        controller.current_transcript = "stale"
        loop = asyncio.new_event_loop()
        loop.run_until_complete(controller.reset_to_idle())
        loop.close()
        assert controller.current_transcript == ""


class TestSegmentAppend:
    """Test that final transcript callbacks append speaker-prefixed segments."""

    def test_final_transcript_stores_speaker_prefixed_segment(
        self, controller: AppController, tmp_store: MeetingStore
    ):
        """Final transcripts are stored WITH the ME:/THEM: speaker prefix."""
        meeting_id = tmp_store.start_meeting()
        controller._active_meeting_id = meeting_id

        controller._on_final_transcript_with_storage("Hello world", "ME")
        controller._on_final_transcript_with_storage("Hi back", "THEM")

        meeting = tmp_store.get_meeting(meeting_id)
        assert len(meeting.segments) == 2
        assert meeting.segments[0].text == "ME: Hello world"
        assert meeting.segments[1].text == "THEM: Hi back"

    def test_final_transcript_without_speaker_stores_raw_text(
        self, controller: AppController, tmp_store: MeetingStore
    ):
        meeting_id = tmp_store.start_meeting()
        controller._active_meeting_id = meeting_id

        controller._on_final_transcript_with_storage("Unattributed text", None)

        meeting = tmp_store.get_meeting(meeting_id)
        assert meeting.segments[0].text == "Unattributed text"

    def test_final_transcript_forwards_text_and_speaker_to_ui(
        self, controller: AppController, tmp_store: MeetingStore
    ):
        received = []
        controller._on_final_transcript = lambda text, speaker: received.append((text, speaker))
        controller._active_meeting_id = tmp_store.start_meeting()

        controller._on_final_transcript_with_storage("Hello", "THEM")

        assert received == [("Hello", "THEM")]

    def test_handle_final_transcript_no_meeting_is_noop(self, controller: AppController):
        """_handle_meeting_segment without active meeting should not crash."""
        controller._active_meeting_id = None
        controller._handle_meeting_segment("text")  # should not raise

    def test_multiple_segments_accumulated(
        self, controller: AppController, tmp_store: MeetingStore
    ):
        meeting_id = tmp_store.start_meeting()
        controller._active_meeting_id = meeting_id

        controller._handle_meeting_segment("ME: First.")
        controller._handle_meeting_segment("THEM: Second.")
        controller._handle_meeting_segment("ME: Third.")

        transcript = tmp_store.get_full_transcript(meeting_id)
        assert transcript == "ME: First. THEM: Second. ME: Third."
