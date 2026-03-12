"""Tests for file-based MeetingStore."""

from __future__ import annotations

import time
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from storage.meeting_store import MeetingStore


@pytest.fixture
def store(tmp_path: Path) -> MeetingStore:
    return MeetingStore(base_dir=tmp_path / "meetings")


class TestInit:
    def test_creates_base_directory(self, tmp_path: Path) -> None:
        base = tmp_path / "deep" / "nested" / "meetings"
        MeetingStore(base_dir=base)
        assert base.exists()


class TestStartMeeting:
    def test_returns_string_id(self, store: MeetingStore) -> None:
        meeting_id = store.start_meeting()
        assert isinstance(meeting_id, str)
        assert len(meeting_id) > 0

    def test_creates_meeting_directory(self, store: MeetingStore) -> None:
        meeting_id = store.start_meeting()
        assert (store._base_dir / meeting_id).is_dir()

    def test_creates_meta_file(self, store: MeetingStore) -> None:
        meeting_id = store.start_meeting()
        assert store._meta_path(meeting_id).exists()

    def test_creates_analyses_directory(self, store: MeetingStore) -> None:
        meeting_id = store.start_meeting()
        assert store._analyses_dir(meeting_id).is_dir()

    def test_meta_contains_start_time(self, store: MeetingStore) -> None:
        before = datetime.now(tz=UTC)
        meeting_id = store.start_meeting()
        after = datetime.now(tz=UTC)
        start_time, _ = store._read_meta(meeting_id)
        assert before <= start_time <= after

    def test_collision_handling_same_second(self, store: MeetingStore) -> None:
        """Two meetings started in the same second get distinct IDs."""
        id1 = store.start_meeting()
        # Patch: temporarily make the second start produce the same base name
        from unittest.mock import patch
        from datetime import timezone
        fixed = datetime.fromisoformat(id1.replace("_", "T", 1).replace("_", ":", 1) if "_" in id1 else id1)
        # Simpler: just start two meetings very quickly
        id2 = store.start_meeting()
        assert id1 != id2


class TestEndMeeting:
    def test_sets_end_time(self, store: MeetingStore) -> None:
        meeting_id = store.start_meeting()
        before = datetime.now(tz=UTC)
        store.end_meeting(meeting_id)
        after = datetime.now(tz=UTC)
        _, end_time = store._read_meta(meeting_id)
        assert end_time is not None
        assert before <= end_time <= after

    def test_nonexistent_meeting_is_noop(self, store: MeetingStore) -> None:
        store.end_meeting("no_such_meeting")  # must not raise


class TestAppendSegment:
    def test_appends_to_transcript_file(self, store: MeetingStore) -> None:
        meeting_id = store.start_meeting()
        store.append_segment(meeting_id, "Hello world")
        assert "Hello world" in store._transcript_path(meeting_id).read_text()

    def test_multiple_segments_in_order(self, store: MeetingStore) -> None:
        meeting_id = store.start_meeting()
        for text in ["First.", "Second.", "Third."]:
            store.append_segment(meeting_id, text)
        meeting = store.get_meeting(meeting_id)
        assert [s.text for s in meeting.segments] == ["First.", "Second.", "Third."]

    def test_empty_segment_ignored(self, store: MeetingStore) -> None:
        meeting_id = store.start_meeting()
        store.append_segment(meeting_id, "")
        store.append_segment(meeting_id, "   ")
        meeting = store.get_meeting(meeting_id)
        assert len(meeting.segments) == 0

    def test_segment_timestamp_recorded(self, store: MeetingStore) -> None:
        meeting_id = store.start_meeting()
        before = datetime.now(tz=UTC)
        store.append_segment(meeting_id, "test")
        after = datetime.now(tz=UTC)
        meeting = store.get_meeting(meeting_id)
        assert before <= meeting.segments[0].timestamp <= after


class TestGetMeeting:
    def test_returns_none_for_unknown_id(self, store: MeetingStore) -> None:
        assert store.get_meeting("no_such_meeting") is None

    def test_includes_all_segments(self, store: MeetingStore) -> None:
        meeting_id = store.start_meeting()
        store.append_segment(meeting_id, "Hello")
        store.append_segment(meeting_id, "World")
        meeting = store.get_meeting(meeting_id)
        assert meeting.full_transcript == "Hello World"


class TestGetFullTranscript:
    def test_returns_space_joined_segments(self, store: MeetingStore) -> None:
        meeting_id = store.start_meeting()
        store.append_segment(meeting_id, "One.")
        store.append_segment(meeting_id, "Two.")
        store.append_segment(meeting_id, "Three.")
        assert store.get_full_transcript(meeting_id) == "One. Two. Three."

    def test_unknown_meeting_returns_empty(self, store: MeetingStore) -> None:
        assert store.get_full_transcript("no_such_meeting") == ""


class TestListMeetings:
    def test_reverse_chronological(self, store: MeetingStore) -> None:
        id1 = store.start_meeting()
        id2 = store.start_meeting()
        meetings = store.list_meetings()
        ids = [m.id for m in meetings]
        assert ids.index(id2) < ids.index(id1)  # newer first

    def test_excludes_segments(self, store: MeetingStore) -> None:
        meeting_id = store.start_meeting()
        store.append_segment(meeting_id, "text")
        meetings = store.list_meetings()
        assert len(meetings[0].segments) == 0

    def test_empty_store(self, store: MeetingStore) -> None:
        assert store.list_meetings() == []


class TestDeleteMeeting:
    def test_removes_directory(self, store: MeetingStore) -> None:
        meeting_id = store.start_meeting()
        store.delete_meeting(meeting_id)
        assert not store._meeting_dir(meeting_id).exists()

    def test_get_returns_none_after_delete(self, store: MeetingStore) -> None:
        meeting_id = store.start_meeting()
        store.delete_meeting(meeting_id)
        assert store.get_meeting(meeting_id) is None

    def test_nonexistent_is_noop(self, store: MeetingStore) -> None:
        store.delete_meeting("no_such_meeting")  # must not raise


class TestMeetingTitle:
    @pytest.mark.unit
    def test_save_and_load_title(self, tmp_path: Path) -> None:
        store = MeetingStore(base_dir=tmp_path)
        mid = store.start_meeting()
        store.end_meeting(mid)
        store.save_title(mid, "Acme Q2 renewal call")
        record = store.get_meeting(mid)
        assert record is not None
        assert record.title == "Acme Q2 renewal call"

    @pytest.mark.unit
    def test_list_meetings_includes_title(self, tmp_path: Path) -> None:
        store = MeetingStore(base_dir=tmp_path)
        mid = store.start_meeting()
        store.end_meeting(mid)
        store.save_title(mid, "My Meeting Title")
        meetings = store.list_meetings()
        assert meetings[0].title == "My Meeting Title"

    @pytest.mark.unit
    def test_meeting_without_title_returns_none(self, tmp_path: Path) -> None:
        store = MeetingStore(base_dir=tmp_path)
        mid = store.start_meeting()
        store.end_meeting(mid)
        record = store.get_meeting(mid)
        assert record is not None
        assert record.title is None


class TestTranscriptFile:
    def test_transcript_is_plain_text(self, store: MeetingStore) -> None:
        """transcript.txt is human-readable — no metadata, one segment per line."""
        meeting_id = store.start_meeting()
        store.append_segment(meeting_id, "This is a sentence.")
        store.append_segment(meeting_id, "And another one.")
        content = store._transcript_path(meeting_id).read_text(encoding="utf-8")
        assert content == "This is a sentence.\nAnd another one.\n"

    def test_performance_large_meeting(self, store: MeetingStore) -> None:
        """3600 segments (60-min meeting) retrieved in under 1 second."""
        import time
        meeting_id = store.start_meeting()
        # Write directly to avoid slow per-call locking in test setup
        now = datetime.now(tz=UTC).isoformat()
        with store._transcript_path(meeting_id).open("a") as tf, \
             store._segments_path(meeting_id).open("a") as sf:
            for i in range(3600):
                line = f"Segment number {i} with some realistic text content."
                tf.write(line + "\n")
                sf.write(f"{now}\t{line}\n")

        start = time.perf_counter()
        transcript = store.get_full_transcript(meeting_id)
        elapsed = time.perf_counter() - start

        assert elapsed < 1.0, f"Transcript retrieval took {elapsed:.3f}s (must be < 1s)"
        assert "Segment number 0" in transcript
        assert "Segment number 3599" in transcript
