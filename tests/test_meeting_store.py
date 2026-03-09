"""Tests for MeetingStore SQLite operations (DAR2-25)."""

import sqlite3
from datetime import UTC, datetime
from pathlib import Path

import pytest

from storage.meeting_store import MeetingStore


@pytest.fixture
def tmp_db(tmp_path: Path) -> Path:
    """Return a temporary database path."""
    return tmp_path / "test_meetings.db"


@pytest.fixture
def store(tmp_db: Path) -> MeetingStore:
    """Create a MeetingStore with a temporary database."""
    s = MeetingStore(db_path=tmp_db)
    yield s
    s.close()


class TestSchemaCreation:
    """Test database initialization."""

    def test_creates_database_file(self, tmp_db: Path):
        store = MeetingStore(db_path=tmp_db)
        assert tmp_db.exists()
        store.close()

    def test_creates_meetings_table(self, store: MeetingStore):
        conn = sqlite3.connect(str(store._db_path))
        cursor = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='meetings'"
        )
        assert cursor.fetchone() is not None
        conn.close()

    def test_creates_transcript_segments_table(self, store: MeetingStore):
        conn = sqlite3.connect(str(store._db_path))
        cursor = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='transcript_segments'"
        )
        assert cursor.fetchone() is not None
        conn.close()

    def test_wal_mode_enabled(self, store: MeetingStore):
        conn = sqlite3.connect(str(store._db_path))
        mode = conn.execute("PRAGMA journal_mode").fetchone()[0]
        assert mode == "wal"
        conn.close()

    def test_creates_parent_directory(self, tmp_path: Path):
        nested = tmp_path / "deep" / "nested" / "meetings.db"
        store = MeetingStore(db_path=nested)
        assert nested.exists()
        store.close()


class TestStartMeeting:
    """Test meeting creation."""

    def test_start_meeting_returns_id(self, store: MeetingStore):
        meeting_id = store.start_meeting()
        assert isinstance(meeting_id, int)
        assert meeting_id > 0

    def test_start_meeting_with_title(self, store: MeetingStore):
        meeting_id = store.start_meeting(title="Standup")
        meeting = store.get_meeting(meeting_id)
        assert meeting is not None
        assert meeting.title == "Standup"

    def test_start_meeting_sets_start_time(self, store: MeetingStore):
        before = datetime.now(tz=UTC)
        meeting_id = store.start_meeting()
        after = datetime.now(tz=UTC)
        meeting = store.get_meeting(meeting_id)
        assert meeting is not None
        assert before <= meeting.start_time <= after


class TestEndMeeting:
    """Test meeting finalization."""

    def test_end_meeting_sets_end_time(self, store: MeetingStore):
        meeting_id = store.start_meeting()
        store.end_meeting(meeting_id)
        meeting = store.get_meeting(meeting_id)
        assert meeting is not None
        assert meeting.end_time is not None

    def test_end_meeting_nonexistent_is_noop(self, store: MeetingStore):
        store.end_meeting(99999)  # should not raise


class TestAppendSegment:
    """Test real-time segment insertion."""

    def test_append_segment(self, store: MeetingStore):
        meeting_id = store.start_meeting()
        store.append_segment(meeting_id, "Hello world")
        meeting = store.get_meeting(meeting_id)
        assert len(meeting.segments) == 1
        assert meeting.segments[0].text == "Hello world"

    def test_append_multiple_segments_preserves_order(self, store: MeetingStore):
        meeting_id = store.start_meeting()
        texts = ["First.", "Second.", "Third."]
        for text in texts:
            store.append_segment(meeting_id, text)
        meeting = store.get_meeting(meeting_id)
        assert [s.text for s in meeting.segments] == texts

    def test_append_segment_sets_timestamp(self, store: MeetingStore):
        meeting_id = store.start_meeting()
        before = datetime.now(tz=UTC)
        store.append_segment(meeting_id, "test")
        after = datetime.now(tz=UTC)
        meeting = store.get_meeting(meeting_id)
        seg = meeting.segments[0]
        assert before <= seg.timestamp <= after

    def test_append_empty_segment_is_ignored(self, store: MeetingStore):
        meeting_id = store.start_meeting()
        store.append_segment(meeting_id, "")
        store.append_segment(meeting_id, "   ")
        meeting = store.get_meeting(meeting_id)
        assert len(meeting.segments) == 0


class TestGetMeeting:
    """Test meeting retrieval."""

    def test_get_meeting_includes_segments(self, store: MeetingStore):
        meeting_id = store.start_meeting(title="Test")
        store.append_segment(meeting_id, "Hello")
        store.append_segment(meeting_id, "World")
        meeting = store.get_meeting(meeting_id)
        assert meeting.full_transcript == "Hello World"

    def test_get_nonexistent_meeting_returns_none(self, store: MeetingStore):
        assert store.get_meeting(99999) is None


class TestGetFullTranscript:
    """Test efficient transcript retrieval."""

    def test_get_full_transcript(self, store: MeetingStore):
        meeting_id = store.start_meeting()
        store.append_segment(meeting_id, "One.")
        store.append_segment(meeting_id, "Two.")
        store.append_segment(meeting_id, "Three.")
        transcript = store.get_full_transcript(meeting_id)
        assert transcript == "One. Two. Three."

    def test_get_full_transcript_nonexistent_returns_empty(self, store: MeetingStore):
        assert store.get_full_transcript(99999) == ""


class TestListMeetings:
    """Test meeting listing."""

    def test_list_meetings_reverse_chronological(self, store: MeetingStore):
        id1 = store.start_meeting(title="First")
        id2 = store.start_meeting(title="Second")
        meetings = store.list_meetings()
        assert len(meetings) == 2
        assert meetings[0].id == id2  # newest first
        assert meetings[1].id == id1

    def test_list_meetings_excludes_segments(self, store: MeetingStore):
        meeting_id = store.start_meeting()
        store.append_segment(meeting_id, "text")
        meetings = store.list_meetings()
        assert len(meetings[0].segments) == 0

    def test_list_meetings_empty(self, store: MeetingStore):
        assert store.list_meetings() == []


class TestDeleteMeeting:
    """Test meeting deletion."""

    def test_delete_meeting(self, store: MeetingStore):
        meeting_id = store.start_meeting()
        store.append_segment(meeting_id, "text")
        store.delete_meeting(meeting_id)
        assert store.get_meeting(meeting_id) is None

    def test_delete_cascades_segments(self, store: MeetingStore):
        meeting_id = store.start_meeting()
        store.append_segment(meeting_id, "text")
        store.delete_meeting(meeting_id)
        # Verify segments are gone too
        conn = sqlite3.connect(str(store._db_path))
        count = conn.execute(
            "SELECT COUNT(*) FROM transcript_segments WHERE meeting_id = ?",
            (meeting_id,),
        ).fetchone()[0]
        conn.close()
        assert count == 0

    def test_delete_nonexistent_is_noop(self, store: MeetingStore):
        store.delete_meeting(99999)  # should not raise


class TestPerformance:
    """Test performance requirements from acceptance criteria."""

    def test_60_minute_meeting_retrieval_under_1_second(self, store: MeetingStore):
        """Simulate a 60-minute meeting: ~1 segment per second = 3600 segments."""
        import time

        meeting_id = store.start_meeting()

        # Insert 3600 segments (one per second of a 60-min meeting)
        # Use executemany for speed in test setup
        conn = sqlite3.connect(str(store._db_path))
        now = datetime.now(tz=UTC).isoformat()
        conn.executemany(
            "INSERT INTO transcript_segments (meeting_id, timestamp, text, is_final) VALUES (?, ?, ?, ?)",
            [
                (meeting_id, now, f"Segment number {i} with some realistic text content.", True)
                for i in range(3600)
            ],
        )
        conn.commit()
        conn.close()

        # Measure retrieval time
        start = time.perf_counter()
        transcript = store.get_full_transcript(meeting_id)
        elapsed = time.perf_counter() - start

        assert elapsed < 1.0, f"Transcript retrieval took {elapsed:.3f}s (must be < 1s)"
        assert "Segment number 0" in transcript
        assert "Segment number 3599" in transcript
