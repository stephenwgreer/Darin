"""Tests for meeting storage data models."""

from datetime import UTC, datetime

from storage.models import MeetingRecord, TranscriptSegment


def test_duration_seconds() -> None:
    start = datetime(2026, 3, 4, 10, 0, 0, tzinfo=UTC)
    end = datetime(2026, 3, 4, 10, 45, 30, tzinfo=UTC)
    meeting = MeetingRecord(start_time=start, end_time=end)
    assert meeting.duration_seconds == 2730


def test_duration_none_when_no_end_time() -> None:
    meeting = MeetingRecord(start_time=datetime.now(tz=UTC))
    assert meeting.duration_seconds is None


def test_word_count() -> None:
    now = datetime.now(tz=UTC)
    meeting = MeetingRecord(
        start_time=now,
        segments=[
            TranscriptSegment(timestamp=now, text="Hello world"),
            TranscriptSegment(timestamp=now, text="How are you doing today"),
        ],
    )
    assert meeting.word_count == 7


def test_full_transcript() -> None:
    now = datetime.now(tz=UTC)
    meeting = MeetingRecord(
        start_time=now,
        segments=[
            TranscriptSegment(timestamp=now, text="Hello."),
            TranscriptSegment(timestamp=now, text="How are you?"),
            TranscriptSegment(timestamp=now, text="I'm fine."),
        ],
    )
    assert meeting.full_transcript == "Hello. How are you? I'm fine."
