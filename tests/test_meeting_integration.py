"""Tests for AppController <-> MeetingStore integration (DAR2-25)."""

from pathlib import Path
from unittest.mock import Mock, patch

import pytest

from app_controller import AppController
from storage.meeting_store import MeetingStore


@pytest.fixture
def tmp_store(tmp_path: Path) -> MeetingStore:
    """Create a MeetingStore with a temporary database."""
    s = MeetingStore(db_path=tmp_path / "test.db")
    yield s
    s.close()


@pytest.fixture
def controller(tmp_store: MeetingStore):
    """Create an AppController with mocked recorder and a temp MeetingStore."""
    with (
        patch("app_controller.ContinuousRecorder") as mock_rec_cls,
        patch("app_controller.ApiClient"),
    ):
        mock_rec = Mock()
        mock_rec.is_recording = False
        mock_rec.sample_rate = 48000
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


class TestSegmentAppend:
    """Test that final transcript callbacks append segments."""

    def test_handle_final_transcript_appends_segment(
        self, controller: AppController, tmp_store: MeetingStore
    ):
        """_handle_meeting_segment should append to the active meeting."""
        meeting_id = tmp_store.start_meeting()
        controller._active_meeting_id = meeting_id

        controller._handle_meeting_segment("Hello world")

        meeting = tmp_store.get_meeting(meeting_id)
        assert len(meeting.segments) == 1
        assert meeting.segments[0].text == "Hello world"

    def test_handle_final_transcript_no_meeting_is_noop(self, controller: AppController):
        """_handle_meeting_segment without active meeting should not crash."""
        controller._active_meeting_id = None
        controller._handle_meeting_segment("text")  # should not raise

    def test_multiple_segments_accumulated(
        self, controller: AppController, tmp_store: MeetingStore
    ):
        meeting_id = tmp_store.start_meeting()
        controller._active_meeting_id = meeting_id

        controller._handle_meeting_segment("First.")
        controller._handle_meeting_segment("Second.")
        controller._handle_meeting_segment("Third.")

        transcript = tmp_store.get_full_transcript(meeting_id)
        assert transcript == "First. Second. Third."
