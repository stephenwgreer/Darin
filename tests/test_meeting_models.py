"""Tests for meeting storage data models (DAR2-25)."""

from datetime import UTC, datetime

from storage.models import MeetingRecord, TranscriptSegment


class TestMeetingRecord:
    """Test MeetingRecord dataclass."""

    def test_create_meeting_record(self):
        now = datetime.now(tz=UTC)
        meeting = MeetingRecord(
            start_time=now,
            title="Test Meeting",
        )
        assert meeting.start_time == now
        assert meeting.title == "Test Meeting"
        assert meeting.end_time is None
        assert meeting.id is None

    def test_duration_property_with_end_time(self):
        start = datetime(2026, 3, 4, 10, 0, 0, tzinfo=UTC)
        end = datetime(2026, 3, 4, 10, 45, 30, tzinfo=UTC)
        meeting = MeetingRecord(start_time=start, end_time=end)
        assert meeting.duration_seconds == 2730

    def test_duration_property_without_end_time(self):
        start = datetime(2026, 3, 4, 10, 0, 0, tzinfo=UTC)
        meeting = MeetingRecord(start_time=start)
        assert meeting.duration_seconds is None

    def test_word_count_no_segments(self):
        meeting = MeetingRecord(
            start_time=datetime.now(tz=UTC),
        )
        assert meeting.word_count == 0

    def test_word_count_with_segments(self):
        meeting = MeetingRecord(
            start_time=datetime.now(tz=UTC),
            segments=[
                TranscriptSegment(
                    timestamp=datetime.now(tz=UTC),
                    text="Hello world",
                    is_final=True,
                ),
                TranscriptSegment(
                    timestamp=datetime.now(tz=UTC),
                    text="How are you doing today",
                    is_final=True,
                ),
            ],
        )
        assert meeting.word_count == 7

    def test_full_transcript_reconstruction(self):
        now = datetime.now(tz=UTC)
        meeting = MeetingRecord(
            start_time=now,
            segments=[
                TranscriptSegment(timestamp=now, text="Hello.", is_final=True),
                TranscriptSegment(timestamp=now, text="How are you?", is_final=True),
                TranscriptSegment(timestamp=now, text="I'm fine.", is_final=True),
            ],
        )
        assert meeting.full_transcript == "Hello. How are you? I'm fine."


class TestTranscriptSegment:
    """Test TranscriptSegment dataclass."""

    def test_create_segment(self):
        now = datetime.now(tz=UTC)
        seg = TranscriptSegment(
            timestamp=now,
            text="Hello world",
            is_final=True,
        )
        assert seg.timestamp == now
        assert seg.text == "Hello world"
        assert seg.is_final is True
        assert seg.meeting_id is None
        assert seg.id is None
