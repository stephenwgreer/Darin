"""Tests for atomic_write_text and the store durability guarantees built on it.

Covers review findings H7/M1 (a failed write must never destroy the prior good
file) and M3 (a truncated meta.txt must not crash reads).
"""

from __future__ import annotations

from pathlib import Path

import pytest

from storage.atomic import atomic_write_text
from storage.meeting_store import MeetingMetaError, MeetingStore


class TestAtomicWriteText:
    def test_writes_content(self, tmp_path: Path) -> None:
        target = tmp_path / "out.txt"
        atomic_write_text(target, "hello")
        assert target.read_text(encoding="utf-8") == "hello"

    def test_creates_parent_dirs(self, tmp_path: Path) -> None:
        target = tmp_path / "nested" / "deep" / "out.txt"
        atomic_write_text(target, "x")
        assert target.read_text(encoding="utf-8") == "x"

    def test_overwrite_replaces_content(self, tmp_path: Path) -> None:
        target = tmp_path / "out.txt"
        atomic_write_text(target, "first")
        atomic_write_text(target, "second")
        assert target.read_text(encoding="utf-8") == "second"

    def test_failed_write_preserves_existing_file(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """The core guarantee: a crash mid-write leaves the prior good file intact."""
        target = tmp_path / "out.txt"
        atomic_write_text(target, "GOOD")

        # Simulate the process dying during the write (after truncate would have
        # happened with the naive write_text, before the atomic replace lands).
        def boom(*_a: object, **_k: object) -> None:
            raise OSError("disk full")

        monkeypatch.setattr("storage.atomic.os.replace", boom)
        with pytest.raises(OSError, match="disk full"):
            atomic_write_text(target, "BAD-PARTIAL")

        # The original content survives; no empty/partial file.
        assert target.read_text(encoding="utf-8") == "GOOD"

    def test_failed_write_leaves_no_temp_files(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        target = tmp_path / "out.txt"

        def boom(*_a: object, **_k: object) -> None:
            raise OSError("io error")

        monkeypatch.setattr("storage.atomic.os.replace", boom)
        with pytest.raises(OSError):
            atomic_write_text(target, "data")

        leftovers = [p for p in tmp_path.iterdir() if p.name != "out.txt"]
        assert leftovers == []


@pytest.fixture
def store(tmp_path: Path) -> MeetingStore:
    return MeetingStore(base_dir=tmp_path / "meetings")


class TestSaveAnalysisDurability:
    def test_failed_save_preserves_prior_analysis(
        self, store: MeetingStore, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        mid = store.start_meeting()
        store.save_analysis(mid, "summary", "GOOD SUMMARY")

        def boom(*_a: object, **_k: object) -> None:
            raise OSError("disk full")

        monkeypatch.setattr("storage.atomic.os.replace", boom)
        with pytest.raises(OSError):
            store.save_analysis(mid, "summary", "PARTIAL")

        assert store.get_analysis(mid, "summary") == "GOOD SUMMARY"


class TestCorruptMeta:
    def test_read_meta_raises_typed_error_on_empty(self, store: MeetingStore) -> None:
        mid = store.start_meeting()
        (store._meeting_dir(mid) / "meta.txt").write_text("", encoding="utf-8")
        with pytest.raises(MeetingMetaError):
            store._read_meta(mid)

    def test_get_meeting_returns_none_on_corrupt_meta(self, store: MeetingStore) -> None:
        mid = store.start_meeting()
        (store._meeting_dir(mid) / "meta.txt").write_text("", encoding="utf-8")
        assert store.get_meeting(mid) is None

    def test_segment_range_returns_empty_on_corrupt_meta(self, store: MeetingStore) -> None:
        mid = store.start_meeting()
        (store._meeting_dir(mid) / "meta.txt").write_text("", encoding="utf-8")
        assert store.get_transcript_segment_range(mid, 0, 5) == ""

    def test_list_meetings_skips_corrupt_meta(self, store: MeetingStore) -> None:
        good = store.start_meeting()
        bad = store.start_meeting()
        (store._meeting_dir(bad) / "meta.txt").write_text("", encoding="utf-8")
        ids = {m.id for m in store.list_meetings()}
        assert good in ids
        assert bad not in ids

    def test_end_meeting_survives_truncated_meta(self, store: MeetingStore) -> None:
        mid = store.start_meeting()
        (store._meeting_dir(mid) / "meta.txt").write_text("", encoding="utf-8")
        # Must not raise IndexError; writes a best-effort end-stamped record.
        store.end_meeting(mid)
        meta = (store._meeting_dir(mid) / "meta.txt").read_text(encoding="utf-8")
        assert len(meta.splitlines()) == 2
