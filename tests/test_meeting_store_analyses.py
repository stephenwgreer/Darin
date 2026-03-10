"""Tests for MeetingStore analysis persistence and segment range (DAR2-27)."""

from __future__ import annotations

import sqlite3
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from storage.meeting_store import MeetingStore


@pytest.fixture
def tmp_db(tmp_path: Path) -> Path:
    """Return a temporary database path."""
    return tmp_path / "test_analyses.db"


@pytest.fixture
def store(tmp_db: Path) -> MeetingStore:
    """Create a MeetingStore with a temporary database."""
    s = MeetingStore(db_path=tmp_db)
    yield s
    s.close()


class TestMeetingAnalysesSchema:
    """Test that the meeting_analyses table is created correctly."""

    def test_creates_meeting_analyses_table(self, store: MeetingStore) -> None:
        conn = sqlite3.connect(str(store._db_path))
        cursor = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='meeting_analyses'"
        )
        assert cursor.fetchone() is not None
        conn.close()


class TestSaveAnalysis:
    """Test saving analysis results."""

    def test_save_and_retrieve_analysis(self, store: MeetingStore) -> None:
        meeting_id = store.start_meeting()
        store.save_analysis(meeting_id, "meeting_summary", "<li>Key point</li>")
        result = store.get_analysis(meeting_id, "meeting_summary")
        assert result == "<li>Key point</li>"

    def test_save_overwrites_on_duplicate(self, store: MeetingStore) -> None:
        meeting_id = store.start_meeting()
        store.save_analysis(meeting_id, "action_items", "first run")
        store.save_analysis(meeting_id, "action_items", "second run")
        result = store.get_analysis(meeting_id, "action_items")
        assert result == "second run"

    def test_save_multiple_prompts_for_same_meeting(self, store: MeetingStore) -> None:
        meeting_id = store.start_meeting()
        store.save_analysis(meeting_id, "meeting_summary", "summary text")
        store.save_analysis(meeting_id, "action_items", "action text")
        store.save_analysis(meeting_id, "key_decisions", "decisions text")
        assert store.get_analysis(meeting_id, "meeting_summary") == "summary text"
        assert store.get_analysis(meeting_id, "action_items") == "action text"
        assert store.get_analysis(meeting_id, "key_decisions") == "decisions text"

    def test_save_analyses_for_different_meetings_are_isolated(
        self, store: MeetingStore
    ) -> None:
        id1 = store.start_meeting()
        id2 = store.start_meeting()
        store.save_analysis(id1, "meeting_summary", "meeting 1 summary")
        store.save_analysis(id2, "meeting_summary", "meeting 2 summary")
        assert store.get_analysis(id1, "meeting_summary") == "meeting 1 summary"
        assert store.get_analysis(id2, "meeting_summary") == "meeting 2 summary"


class TestGetAnalysis:
    """Test retrieving individual analyses."""

    def test_get_analysis_returns_none_when_missing(self, store: MeetingStore) -> None:
        meeting_id = store.start_meeting()
        result = store.get_analysis(meeting_id, "nonexistent_prompt")
        assert result is None

    def test_get_analysis_nonexistent_meeting_returns_none(
        self, store: MeetingStore
    ) -> None:
        result = store.get_analysis(99999, "meeting_summary")
        assert result is None


class TestListAnalysesForMeeting:
    """Test listing all analyses for a meeting."""

    def test_list_analyses_for_meeting(self, store: MeetingStore) -> None:
        meeting_id = store.start_meeting()
        store.save_analysis(meeting_id, "meeting_summary", "summary")
        store.save_analysis(meeting_id, "action_items", "actions")
        store.save_analysis(meeting_id, "key_decisions", "decisions")
        result = store.list_analyses_for_meeting(meeting_id)
        assert len(result) == 3
        assert result["meeting_summary"] == "summary"
        assert result["action_items"] == "actions"
        assert result["key_decisions"] == "decisions"

    def test_list_analyses_empty_for_new_meeting(self, store: MeetingStore) -> None:
        meeting_id = store.start_meeting()
        result = store.list_analyses_for_meeting(meeting_id)
        assert result == {}

    def test_list_analyses_nonexistent_meeting_returns_empty(
        self, store: MeetingStore
    ) -> None:
        result = store.list_analyses_for_meeting(99999)
        assert result == {}

    def test_list_analyses_only_returns_current_meeting(
        self, store: MeetingStore
    ) -> None:
        id1 = store.start_meeting()
        id2 = store.start_meeting()
        store.save_analysis(id1, "meeting_summary", "for meeting 1")
        result = store.list_analyses_for_meeting(id2)
        assert result == {}

    def test_list_analyses_returns_dict_type(self, store: MeetingStore) -> None:
        meeting_id = store.start_meeting()
        store.save_analysis(meeting_id, "meeting_summary", "text")
        result = store.list_analyses_for_meeting(meeting_id)
        assert isinstance(result, dict)
        for k, v in result.items():
            assert isinstance(k, str)
            assert isinstance(v, str)


class TestGetTranscriptSegmentRange:
    """Test time-range filtered transcript retrieval."""

    def _insert_segment_at_offset(
        self,
        store: MeetingStore,
        meeting_id: int,
        start_time: datetime,
        offset_seconds: int,
        text: str,
    ) -> None:
        """Helper: insert a segment at a specific time offset from meeting start."""
        ts = (start_time + timedelta(seconds=offset_seconds)).isoformat()
        conn = sqlite3.connect(str(store._db_path))
        conn.execute(
            "INSERT INTO transcript_segments (meeting_id, timestamp, text, is_final) VALUES (?, ?, ?, ?)",
            (meeting_id, ts, text, 1),
        )
        conn.commit()
        conn.close()

    def test_get_transcript_segment_range_filters_correctly(
        self, store: MeetingStore
    ) -> None:
        """Segments in the range are returned; segments outside are excluded."""
        start_time = datetime.now(tz=UTC)
        meeting_id = store.start_meeting()
        # Override start_time in DB to a known value
        conn = sqlite3.connect(str(store._db_path))
        conn.execute(
            "UPDATE meetings SET start_time = ? WHERE id = ?",
            (start_time.isoformat(), meeting_id),
        )
        conn.commit()
        conn.close()

        # Segment at 0s (minute 0) — before range
        self._insert_segment_at_offset(store, meeting_id, start_time, 0, "intro")
        # Segment at 310s (~5 min 10s) — in range [5, 10]
        self._insert_segment_at_offset(store, meeting_id, start_time, 310, "in range")
        # Segment at 700s (~11 min 40s) — after range
        self._insert_segment_at_offset(store, meeting_id, start_time, 700, "outro")

        result = store.get_transcript_segment_range(meeting_id, 5, 10)
        assert "in range" in result
        assert "intro" not in result
        assert "outro" not in result

    def test_get_transcript_segment_range_nonexistent_meeting(
        self, store: MeetingStore
    ) -> None:
        result = store.get_transcript_segment_range(99999, 0, 10)
        assert result == ""

    def test_get_transcript_segment_range_empty_range(
        self, store: MeetingStore
    ) -> None:
        """Range with no matching segments returns empty string."""
        start_time = datetime.now(tz=UTC)
        meeting_id = store.start_meeting()
        conn = sqlite3.connect(str(store._db_path))
        conn.execute(
            "UPDATE meetings SET start_time = ? WHERE id = ?",
            (start_time.isoformat(), meeting_id),
        )
        conn.commit()
        conn.close()
        # Insert segment at minute 30 — outside range 0-5
        self._insert_segment_at_offset(
            store, meeting_id, start_time, 1800, "late segment"
        )
        result = store.get_transcript_segment_range(meeting_id, 0, 5)
        assert result == ""


class TestDeleteCascadesToAnalyses:
    """Verify ON DELETE CASCADE removes analyses when meeting is deleted."""

    def test_delete_meeting_removes_analyses(self, store: MeetingStore) -> None:
        meeting_id = store.start_meeting()
        store.save_analysis(meeting_id, "meeting_summary", "text")
        store.delete_meeting(meeting_id)
        result = store.list_analyses_for_meeting(meeting_id)
        assert result == {}
