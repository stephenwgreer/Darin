"""Tests for MeetingStore analysis persistence and segment range."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from storage.meeting_store import MeetingStore


@pytest.fixture
def store(tmp_path: Path) -> MeetingStore:
    return MeetingStore(base_dir=tmp_path / "meetings")


class TestSaveAnalysis:
    def test_save_and_retrieve(self, store: MeetingStore) -> None:
        meeting_id = store.start_meeting()
        store.save_analysis(meeting_id, "meeting_summary", "<li>Key point</li>")
        assert store.get_analysis(meeting_id, "meeting_summary") == "<li>Key point</li>"

    def test_overwrite_on_duplicate(self, store: MeetingStore) -> None:
        meeting_id = store.start_meeting()
        store.save_analysis(meeting_id, "action_items", "first run")
        store.save_analysis(meeting_id, "action_items", "second run")
        assert store.get_analysis(meeting_id, "action_items") == "second run"

    def test_multiple_prompts_same_meeting(self, store: MeetingStore) -> None:
        meeting_id = store.start_meeting()
        store.save_analysis(meeting_id, "meeting_summary", "summary text")
        store.save_analysis(meeting_id, "action_items", "action text")
        store.save_analysis(meeting_id, "key_decisions", "decisions text")
        assert store.get_analysis(meeting_id, "meeting_summary") == "summary text"
        assert store.get_analysis(meeting_id, "action_items") == "action text"
        assert store.get_analysis(meeting_id, "key_decisions") == "decisions text"

    def test_different_meetings_isolated(self, store: MeetingStore) -> None:
        id1 = store.start_meeting()
        id2 = store.start_meeting()
        store.save_analysis(id1, "meeting_summary", "meeting 1 summary")
        store.save_analysis(id2, "meeting_summary", "meeting 2 summary")
        assert store.get_analysis(id1, "meeting_summary") == "meeting 1 summary"
        assert store.get_analysis(id2, "meeting_summary") == "meeting 2 summary"

    def test_saves_as_plain_text_file(self, store: MeetingStore) -> None:
        meeting_id = store.start_meeting()
        store.save_analysis(meeting_id, "key_topics", "the content")
        path = store._analyses_dir(meeting_id) / "key_topics.txt"
        assert path.exists()
        assert path.read_text() == "the content"


class TestGetAnalysis:
    def test_returns_none_when_missing(self, store: MeetingStore) -> None:
        meeting_id = store.start_meeting()
        assert store.get_analysis(meeting_id, "nonexistent_prompt") is None

    def test_nonexistent_meeting_returns_none(self, store: MeetingStore) -> None:
        assert store.get_analysis("no_such_meeting", "meeting_summary") is None


class TestListAnalysesForMeeting:
    def test_lists_all_analyses(self, store: MeetingStore) -> None:
        meeting_id = store.start_meeting()
        store.save_analysis(meeting_id, "meeting_summary", "summary")
        store.save_analysis(meeting_id, "action_items", "actions")
        store.save_analysis(meeting_id, "key_decisions", "decisions")
        result = store.list_analyses_for_meeting(meeting_id)
        assert len(result) == 3
        assert result["meeting_summary"] == "summary"
        assert result["action_items"] == "actions"
        assert result["key_decisions"] == "decisions"

    def test_empty_for_new_meeting(self, store: MeetingStore) -> None:
        meeting_id = store.start_meeting()
        assert store.list_analyses_for_meeting(meeting_id) == {}

    def test_nonexistent_meeting_returns_empty(self, store: MeetingStore) -> None:
        assert store.list_analyses_for_meeting("no_such_meeting") == {}

    def test_only_returns_current_meeting(self, store: MeetingStore) -> None:
        id1 = store.start_meeting()
        id2 = store.start_meeting()
        store.save_analysis(id1, "meeting_summary", "for meeting 1")
        assert store.list_analyses_for_meeting(id2) == {}

    def test_returns_dict_of_strings(self, store: MeetingStore) -> None:
        meeting_id = store.start_meeting()
        store.save_analysis(meeting_id, "meeting_summary", "text")
        result = store.list_analyses_for_meeting(meeting_id)
        assert isinstance(result, dict)
        for k, v in result.items():
            assert isinstance(k, str)
            assert isinstance(v, str)


class TestGetTranscriptSegmentRange:
    def _write_segment_at_offset(
        self,
        store: MeetingStore,
        meeting_id: str,
        start_time: datetime,
        offset_seconds: int,
        text: str,
    ) -> None:
        """Write a segment at a specific time offset directly to segments.tsv."""
        ts = (start_time + timedelta(seconds=offset_seconds)).isoformat()
        with store._segments_path(meeting_id).open("a", encoding="utf-8") as f:
            f.write(f"{ts}\t{text}\n")

    def test_filters_by_minute_range(self, store: MeetingStore) -> None:
        start_time = datetime.now(tz=UTC)
        meeting_id = store.start_meeting()
        # Override meta with a known start time
        store._meta_path(meeting_id).write_text(start_time.isoformat() + "\n")

        self._write_segment_at_offset(
            store, meeting_id, start_time, 0, "intro"
        )  # minute 0 — before range
        self._write_segment_at_offset(
            store, meeting_id, start_time, 310, "in range"
        )  # ~5m10s — in [5,10]
        self._write_segment_at_offset(
            store, meeting_id, start_time, 700, "outro"
        )  # ~11m40s — after range

        result = store.get_transcript_segment_range(meeting_id, 5, 10)
        assert "in range" in result
        assert "intro" not in result
        assert "outro" not in result

    def test_nonexistent_meeting_returns_empty(self, store: MeetingStore) -> None:
        assert store.get_transcript_segment_range("no_such_meeting", 0, 10) == ""

    def test_empty_range_returns_empty_string(self, store: MeetingStore) -> None:
        start_time = datetime.now(tz=UTC)
        meeting_id = store.start_meeting()
        store._meta_path(meeting_id).write_text(start_time.isoformat() + "\n")
        self._write_segment_at_offset(store, meeting_id, start_time, 1800, "late segment")
        assert store.get_transcript_segment_range(meeting_id, 0, 5) == ""


class TestDeleteCascadesToAnalyses:
    def test_delete_removes_analyses(self, store: MeetingStore) -> None:
        meeting_id = store.start_meeting()
        store.save_analysis(meeting_id, "meeting_summary", "text")
        store.delete_meeting(meeting_id)
        assert store.list_analyses_for_meeting(meeting_id) == {}
