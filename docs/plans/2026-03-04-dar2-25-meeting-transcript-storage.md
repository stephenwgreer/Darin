# DAR2-25: Meeting Transcript Storage — Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Create a SQLite storage layer that persists meeting transcripts in real-time as segments arrive from the Deepgram WebSocket, with meeting lifecycle management and full transcript reconstruction.

**Architecture:** A new `storage/` package with two layers: (1) `MeetingStore` — a thread-safe SQLite wrapper that creates `meetings` and `transcript_segments` tables with WAL mode for concurrent read/write, and (2) integration into `AppController` so that `start_streaming()` creates a meeting row and each `on_final_transcript` callback appends a segment. No UI changes — this is pure backend storage.

**Tech Stack:** Python 3.11 stdlib `sqlite3`, `dataclasses`, `threading`, `pathlib`. No new dependencies.

---

## Context for the Implementer

### Codebase orientation

- **Root:** `/mnt/c/Users/stwgre/Github/Darin_AA/claude-redesign/`
- **Tests run from root:** `.venv/bin/python -m pytest tests/ --no-cov -v`
- **Linter:** `.venv/bin/ruff check .`
- **Ruff config:** `ruff.toml` — uses isort (`I` rules), `known-first-party` list must include `storage`
- **Test config:** `pyproject.toml` `[tool.pytest.ini_options]` — uses `--cov-fail-under=80` by default, use `--no-cov` during development
- **conftest.py:** `tests/conftest.py` stubs `soundcard` for WSL/CI
- **Git wrapper:** From engineering-manager dir, use `./scripts/wsl-git.sh -C /mnt/c/Users/stwgre/Github/Darin_AA/claude-redesign <cmd>`

### Key existing files

| File | What it does | Relevant to this task |
|------|-------------|----------------------|
| `app_controller.py` | Framework-agnostic orchestrator. Owns recording, streaming, transcription lifecycle. | We add meeting storage hooks here in Task 4. |
| `api/deepgram_streaming.py` | WebSocket client to Deepgram. Fires `on_final_transcript(segment_text)` callbacks. | We consume these callbacks — don't modify this file. |
| `audio/recorder.py` | Audio capture with consumer fan-out (DAR2-24). | No changes needed. |
| `config.py` | App configuration constants. | No changes needed — DB path is self-contained in `MeetingStore`. |
| `storage/` | Directory exists but has NO `.py` source files (only stale `.pyc`). | We create all files fresh. |
| `ruff.toml:67` | `known-first-party = ["api", "audio", "processing", "prompts", "ui"]` | Must add `"storage"` in Task 1. |

### What DeepgramStreamingClient gives us

From `api/deepgram_streaming.py`, the streaming client accumulates final segments in `_final_segments: list[str]` and fires callbacks:
- `on_final_transcript(segment_text: str)` — each finalized segment from Deepgram
- `on_utterance_end(full_transcript: str)` — full accumulated text at utterance boundary

In `AppController`:
- `start_streaming()` creates the Deepgram client and starts recording
- `stop_streaming()` disconnects and returns the accumulated transcript
- `_handle_utterance_end(full_transcript)` is called on utterance end
- `_on_final_transcript` callback is passed directly to the Deepgram client

### Design decisions (pre-made — do not deviate)

1. **DB location:** `~/.darin-audio-assistant/meetings.db` — separate from any future session DB
2. **WAL mode:** Enabled for concurrent reads during writes (segments appended while meeting is live)
3. **Append-only segments:** Never update segments — only INSERT. This is critical for write performance during long meetings.
4. **Thread safety:** `MeetingStore` uses a `threading.Lock` around all writes. Connection uses `check_same_thread=False`.
5. **No UI changes in this ticket** — storage is consumed by AppController only.

---

## Task 1: Create storage package with data models

**Files:**
- Modify: `ruff.toml:67` (add `"storage"` to known-first-party)
- Create: `storage/__init__.py`
- Create: `storage/models.py`
- Test: `tests/test_meeting_models.py`

### Step 1: Add `storage` to ruff known-first-party

In `ruff.toml`, line 67, change:
```toml
known-first-party = ["api", "audio", "processing", "prompts", "ui"]
```
to:
```toml
known-first-party = ["api", "audio", "processing", "prompts", "storage", "ui"]
```

Keep alphabetical order.

### Step 2: Write the test file

Create `tests/test_meeting_models.py`:

```python
"""Tests for meeting storage data models (DAR2-25)."""

from datetime import datetime, timezone

from storage.models import MeetingRecord, TranscriptSegment


class TestMeetingRecord:
    """Test MeetingRecord dataclass."""

    def test_create_meeting_record(self):
        now = datetime.now(tz=timezone.utc)
        meeting = MeetingRecord(
            start_time=now,
            title="Test Meeting",
        )
        assert meeting.start_time == now
        assert meeting.title == "Test Meeting"
        assert meeting.end_time is None
        assert meeting.id is None

    def test_duration_property_with_end_time(self):
        start = datetime(2026, 3, 4, 10, 0, 0, tzinfo=timezone.utc)
        end = datetime(2026, 3, 4, 10, 45, 30, tzinfo=timezone.utc)
        meeting = MeetingRecord(start_time=start, end_time=end)
        assert meeting.duration_seconds == 2730

    def test_duration_property_without_end_time(self):
        start = datetime(2026, 3, 4, 10, 0, 0, tzinfo=timezone.utc)
        meeting = MeetingRecord(start_time=start)
        assert meeting.duration_seconds is None

    def test_word_count_no_segments(self):
        meeting = MeetingRecord(
            start_time=datetime.now(tz=timezone.utc),
        )
        assert meeting.word_count == 0

    def test_word_count_with_segments(self):
        meeting = MeetingRecord(
            start_time=datetime.now(tz=timezone.utc),
            segments=[
                TranscriptSegment(
                    timestamp=datetime.now(tz=timezone.utc),
                    text="Hello world",
                    is_final=True,
                ),
                TranscriptSegment(
                    timestamp=datetime.now(tz=timezone.utc),
                    text="How are you doing today",
                    is_final=True,
                ),
            ],
        )
        assert meeting.word_count == 7

    def test_full_transcript_reconstruction(self):
        now = datetime.now(tz=timezone.utc)
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
        now = datetime.now(tz=timezone.utc)
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
```

### Step 3: Run tests to verify they fail

```bash
cd /mnt/c/Users/stwgre/Github/Darin_AA/claude-redesign
.venv/bin/python -m pytest tests/test_meeting_models.py --no-cov -v
```

Expected: `ModuleNotFoundError: No module named 'storage'` or `ImportError`

### Step 4: Create the storage package

Create `storage/__init__.py`:

```python
"""Meeting transcript storage package (DAR2-25)."""
```

Create `storage/models.py`:

```python
"""Data models for meeting transcript storage (DAR2-25)."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime


@dataclass
class TranscriptSegment:
    """A single finalized transcript segment from Deepgram."""

    timestamp: datetime
    text: str
    is_final: bool = True
    meeting_id: int | None = None
    id: int | None = None


@dataclass
class MeetingRecord:
    """A meeting session with metadata and transcript segments."""

    start_time: datetime
    title: str | None = None
    end_time: datetime | None = None
    segments: list[TranscriptSegment] = field(default_factory=list)
    id: int | None = None

    @property
    def duration_seconds(self) -> int | None:
        """Meeting duration in seconds, or None if still in progress."""
        if self.end_time is None:
            return None
        return int((self.end_time - self.start_time).total_seconds())

    @property
    def word_count(self) -> int:
        """Total word count across all segments."""
        return sum(len(seg.text.split()) for seg in self.segments)

    @property
    def full_transcript(self) -> str:
        """Reconstruct the full transcript from all segments."""
        return " ".join(seg.text for seg in self.segments)
```

### Step 5: Run tests to verify they pass

```bash
.venv/bin/python -m pytest tests/test_meeting_models.py --no-cov -v
```

Expected: All 7 tests PASS

### Step 6: Run ruff to verify no lint issues

```bash
.venv/bin/ruff check storage/ tests/test_meeting_models.py
```

Expected: `All checks passed!`

### Step 7: Commit

```bash
git add ruff.toml storage/__init__.py storage/models.py tests/test_meeting_models.py
git commit -m "feat(DAR2-25): add meeting storage data models

MeetingRecord and TranscriptSegment dataclasses with duration,
word count, and full transcript reconstruction properties."
```

---

## Task 2: Implement MeetingStore (SQLite operations)

**Files:**
- Create: `storage/meeting_store.py`
- Test: `tests/test_meeting_store.py`

### Step 1: Write the test file

Create `tests/test_meeting_store.py`:

```python
"""Tests for MeetingStore SQLite operations (DAR2-25)."""

import sqlite3
from datetime import datetime, timezone
from pathlib import Path

import pytest

from storage.meeting_store import MeetingStore
from storage.models import MeetingRecord, TranscriptSegment


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
        before = datetime.now(tz=timezone.utc)
        meeting_id = store.start_meeting()
        after = datetime.now(tz=timezone.utc)
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
        before = datetime.now(tz=timezone.utc)
        store.append_segment(meeting_id, "test")
        after = datetime.now(tz=timezone.utc)
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
        now = datetime.now(tz=timezone.utc).isoformat()
        conn.executemany(
            "INSERT INTO transcript_segments (meeting_id, timestamp, text, is_final) VALUES (?, ?, ?, ?)",
            [(meeting_id, now, f"Segment number {i} with some realistic text content.", True) for i in range(3600)],
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
```

### Step 2: Run tests to verify they fail

```bash
.venv/bin/python -m pytest tests/test_meeting_store.py --no-cov -v
```

Expected: `ModuleNotFoundError: No module named 'storage.meeting_store'`

### Step 3: Implement MeetingStore

Create `storage/meeting_store.py`:

```python
"""SQLite storage for meeting transcripts (DAR2-25).

Thread-safe, WAL-mode SQLite database for persisting meeting sessions
and their transcript segments in real time.
"""

from __future__ import annotations

import sqlite3
import threading
from datetime import datetime, timezone
from pathlib import Path

from loguru import logger

from storage.models import MeetingRecord, TranscriptSegment

_DEFAULT_DB_PATH = Path.home() / ".darin-audio-assistant" / "meetings.db"

_SCHEMA_SQL = """\
CREATE TABLE IF NOT EXISTS meetings (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    title       TEXT,
    start_time  TEXT NOT NULL,
    end_time    TEXT
);

CREATE TABLE IF NOT EXISTS transcript_segments (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    meeting_id  INTEGER NOT NULL REFERENCES meetings(id) ON DELETE CASCADE,
    timestamp   TEXT NOT NULL,
    text        TEXT NOT NULL,
    is_final    INTEGER NOT NULL DEFAULT 1
);

CREATE INDEX IF NOT EXISTS idx_segments_meeting_ts
    ON transcript_segments(meeting_id, timestamp);
"""


class MeetingStore:
    """Thread-safe SQLite store for meeting transcripts.

    All write operations are serialized via a threading lock.
    The connection uses ``check_same_thread=False`` so it can be
    shared across the recorder, streaming, and UI threads.
    """

    def __init__(self, db_path: Path | None = None) -> None:
        self._db_path = db_path or _DEFAULT_DB_PATH
        self._db_path.parent.mkdir(parents=True, exist_ok=True)

        self._conn = sqlite3.connect(
            str(self._db_path),
            check_same_thread=False,
        )
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute("PRAGMA foreign_keys=ON")
        self._lock = threading.Lock()

        self._init_schema()
        logger.debug("MeetingStore initialized", db_path=str(self._db_path))

    def _init_schema(self) -> None:
        """Create tables if they don't exist."""
        with self._lock:
            self._conn.executescript(_SCHEMA_SQL)

    # ------------------------------------------------------------------
    # Meeting lifecycle
    # ------------------------------------------------------------------

    def start_meeting(self, title: str | None = None) -> int:
        """Create a new meeting row. Returns the meeting ID."""
        now = datetime.now(tz=timezone.utc).isoformat()
        with self._lock:
            cursor = self._conn.execute(
                "INSERT INTO meetings (title, start_time) VALUES (?, ?)",
                (title, now),
            )
            self._conn.commit()
            meeting_id = cursor.lastrowid
        logger.info("Meeting started", meeting_id=meeting_id, title=title)
        return meeting_id

    def end_meeting(self, meeting_id: int) -> None:
        """Set the end time for a meeting."""
        now = datetime.now(tz=timezone.utc).isoformat()
        with self._lock:
            self._conn.execute(
                "UPDATE meetings SET end_time = ? WHERE id = ?",
                (now, meeting_id),
            )
            self._conn.commit()
        logger.info("Meeting ended", meeting_id=meeting_id)

    # ------------------------------------------------------------------
    # Segment operations (real-time append)
    # ------------------------------------------------------------------

    def append_segment(self, meeting_id: int, text: str) -> None:
        """Append a transcript segment to a meeting.

        Empty or whitespace-only text is silently ignored.
        """
        if not text or not text.strip():
            return

        now = datetime.now(tz=timezone.utc).isoformat()
        with self._lock:
            self._conn.execute(
                "INSERT INTO transcript_segments (meeting_id, timestamp, text, is_final) "
                "VALUES (?, ?, ?, ?)",
                (meeting_id, now, text, 1),
            )
            self._conn.commit()

    # ------------------------------------------------------------------
    # Retrieval
    # ------------------------------------------------------------------

    def get_meeting(self, meeting_id: int) -> MeetingRecord | None:
        """Retrieve a meeting with all its segments."""
        row = self._conn.execute(
            "SELECT id, title, start_time, end_time FROM meetings WHERE id = ?",
            (meeting_id,),
        ).fetchone()

        if row is None:
            return None

        segments = self._conn.execute(
            "SELECT id, meeting_id, timestamp, text, is_final "
            "FROM transcript_segments WHERE meeting_id = ? ORDER BY timestamp, id",
            (meeting_id,),
        ).fetchall()

        return MeetingRecord(
            id=row[0],
            title=row[1],
            start_time=datetime.fromisoformat(row[2]),
            end_time=datetime.fromisoformat(row[3]) if row[3] else None,
            segments=[
                TranscriptSegment(
                    id=s[0],
                    meeting_id=s[1],
                    timestamp=datetime.fromisoformat(s[2]),
                    text=s[3],
                    is_final=bool(s[4]),
                )
                for s in segments
            ],
        )

    def get_full_transcript(self, meeting_id: int) -> str:
        """Efficiently retrieve the full transcript for a meeting.

        Uses a single query to concatenate all segment texts — avoids
        loading full TranscriptSegment objects.
        """
        rows = self._conn.execute(
            "SELECT text FROM transcript_segments "
            "WHERE meeting_id = ? ORDER BY timestamp, id",
            (meeting_id,),
        ).fetchall()
        return " ".join(row[0] for row in rows)

    def list_meetings(self) -> list[MeetingRecord]:
        """List all meetings, newest first. Segments are NOT loaded."""
        rows = self._conn.execute(
            "SELECT id, title, start_time, end_time FROM meetings "
            "ORDER BY start_time DESC",
        ).fetchall()

        return [
            MeetingRecord(
                id=r[0],
                title=r[1],
                start_time=datetime.fromisoformat(r[2]),
                end_time=datetime.fromisoformat(r[3]) if r[3] else None,
            )
            for r in rows
        ]

    # ------------------------------------------------------------------
    # Deletion
    # ------------------------------------------------------------------

    def delete_meeting(self, meeting_id: int) -> None:
        """Delete a meeting and all its segments (CASCADE)."""
        with self._lock:
            self._conn.execute("DELETE FROM meetings WHERE id = ?", (meeting_id,))
            self._conn.commit()
        logger.info("Meeting deleted", meeting_id=meeting_id)

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def close(self) -> None:
        """Close the database connection."""
        self._conn.close()
        logger.debug("MeetingStore connection closed")
```

### Step 4: Run tests to verify they pass

```bash
.venv/bin/python -m pytest tests/test_meeting_store.py --no-cov -v
```

Expected: All 20 tests PASS

### Step 5: Run ruff

```bash
.venv/bin/ruff check storage/meeting_store.py tests/test_meeting_store.py
```

Expected: `All checks passed!`

### Step 6: Commit

```bash
git add storage/meeting_store.py tests/test_meeting_store.py
git commit -m "feat(DAR2-25): implement MeetingStore with SQLite + WAL mode

Thread-safe SQLite store for meeting transcripts with append-only
segments, meeting lifecycle management, and efficient transcript
retrieval. 60-minute meeting retrieval tested under 1 second."
```

---

## Task 3: Update `__init__.py` exports and add `storage` to setuptools

**Files:**
- Modify: `storage/__init__.py`
- Modify: `pyproject.toml:8` (add `"storage*"` to setuptools packages)

### Step 1: Update `storage/__init__.py`

```python
"""Meeting transcript storage package (DAR2-25)."""

from storage.meeting_store import MeetingStore
from storage.models import MeetingRecord, TranscriptSegment

__all__ = ["MeetingStore", "MeetingRecord", "TranscriptSegment"]
```

### Step 2: Update `pyproject.toml` setuptools include

In `pyproject.toml`, line 8, change:
```toml
include = ["api*", "audio*", "processing*", "prompts*", "ui*"]
```
to:
```toml
include = ["api*", "audio*", "processing*", "prompts*", "storage*", "ui*"]
```

Keep alphabetical order.

### Step 3: Verify imports work

```bash
.venv/bin/python -c "from storage import MeetingStore, MeetingRecord, TranscriptSegment; print('OK')"
```

Expected: `OK`

### Step 4: Run all tests

```bash
.venv/bin/python -m pytest tests/test_meeting_models.py tests/test_meeting_store.py --no-cov -v
```

Expected: All 27 tests PASS

### Step 5: Run ruff on everything

```bash
.venv/bin/ruff check storage/ tests/test_meeting_models.py tests/test_meeting_store.py
```

Expected: `All checks passed!`

### Step 6: Commit

```bash
git add storage/__init__.py pyproject.toml
git commit -m "feat(DAR2-25): export storage package and add to setuptools"
```

---

## Task 4: Integrate MeetingStore into AppController

**Files:**
- Modify: `app_controller.py`
- Test: `tests/test_meeting_integration.py`

### Step 1: Write the integration test file

Create `tests/test_meeting_integration.py`:

```python
"""Tests for AppController ↔ MeetingStore integration (DAR2-25)."""

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
    with patch("app_controller.ContinuousRecorder") as mock_rec_cls, \
         patch("app_controller.ApiClient"):
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

    def test_start_streaming_creates_meeting(self, controller: AppController, tmp_store: MeetingStore):
        """start_streaming should create a meeting row when store is set."""
        with patch.object(controller, '_streaming_client') as mock_client:
            # Simulate streaming client being None initially, then created
            controller._streaming_client = None

            # Mock the DeepgramStreamingClient constructor and connect
            with patch("app_controller.DeepgramStreamingClient") as mock_dg_cls:
                mock_dg = Mock()
                mock_dg.is_connected = True
                mock_dg_cls.return_value = mock_dg

                controller.start_streaming()

                assert controller._active_meeting_id is not None
                meeting = tmp_store.get_meeting(controller._active_meeting_id)
                assert meeting is not None
                assert meeting.end_time is None  # still in progress

    def test_stop_streaming_ends_meeting(self, controller: AppController, tmp_store: MeetingStore):
        """stop_streaming should set end_time on the active meeting."""
        # Set up an active meeting
        meeting_id = tmp_store.start_meeting(title="Test")
        controller._active_meeting_id = meeting_id

        # Mock streaming client
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

    def test_handle_final_transcript_appends_segment(self, controller: AppController, tmp_store: MeetingStore):
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

    def test_multiple_segments_accumulated(self, controller: AppController, tmp_store: MeetingStore):
        meeting_id = tmp_store.start_meeting()
        controller._active_meeting_id = meeting_id

        controller._handle_meeting_segment("First.")
        controller._handle_meeting_segment("Second.")
        controller._handle_meeting_segment("Third.")

        transcript = tmp_store.get_full_transcript(meeting_id)
        assert transcript == "First. Second. Third."
```

### Step 2: Run tests to verify they fail

```bash
.venv/bin/python -m pytest tests/test_meeting_integration.py --no-cov -v
```

Expected: `AttributeError: 'AppController' object has no attribute '_meeting_store'`

### Step 3: Modify AppController

Add meeting storage to `app_controller.py`. The changes are:

**3a. Add import** — after the existing imports (around line 8), add:

```python
from storage.meeting_store import MeetingStore
```

**3b. Add state variables** — in `__init__`, after `self._template_type` (line 76), add:

```python
        # Meeting storage (DAR2-25)
        self._meeting_store: MeetingStore | None = None
        self._active_meeting_id: int | None = None
```

**3c. Add meeting store property** — after the `template_type` setter (after line 118), add:

```python
    @property
    def meeting_store(self) -> MeetingStore | None:
        return self._meeting_store

    @meeting_store.setter
    def meeting_store(self, store: MeetingStore | None) -> None:
        self._meeting_store = store
```

**3d. Modify `start_streaming()`** — after `self.recorder.add_chunk_consumer(self._on_recorder_chunk)` (line 186), add:

```python
        # Create meeting record if storage is available
        if self._meeting_store is not None:
            self._active_meeting_id = self._meeting_store.start_meeting()
```

**3e. Modify `stop_streaming()`** — after `self._streaming_client.disconnect()` and before `transcript = self._streaming_client.get_full_transcript()` (between lines 202-203), add:

```python
        # Finalize meeting record
        if self._meeting_store is not None and self._active_meeting_id is not None:
            self._meeting_store.end_meeting(self._active_meeting_id)
            self._active_meeting_id = None
```

Wait — the `_active_meeting_id = None` should happen AFTER we use it, but stop_streaming resets it. Let me reconsider. The end_meeting call and reset should happen in stop_streaming after the disconnect but the `_active_meeting_id` must be cleared. This is fine because we only need the ID for the end_meeting call.

Actually, we should clear `_active_meeting_id` at the very end of `stop_streaming()`, just before the return. Add after `self._streaming_client = None` (line 210):

```python
        # Clear meeting tracking (after all streaming cleanup)
        self._active_meeting_id = None
```

And the `end_meeting` call should be before the `disconnect()` isn't needed — actually, it should be after disconnect, which is fine. Let me write the exact insertion points:

After line 202 (`self._streaming_client.disconnect()`), insert:

```python
        # Finalize meeting record
        if self._meeting_store is not None and self._active_meeting_id is not None:
            self._meeting_store.end_meeting(self._active_meeting_id)
```

After line 210 (`self._streaming_client = None`), insert:

```python
        self._active_meeting_id = None
```

**3f. Add segment handler method** — after `_on_streaming_error` method (after line 236), add:

```python
    def _handle_meeting_segment(self, text: str) -> None:
        """Append a final transcript segment to the active meeting."""
        if self._meeting_store is not None and self._active_meeting_id is not None:
            self._meeting_store.append_segment(self._active_meeting_id, text)
```

**3g. Wire the segment handler into DeepgramStreamingClient** — in `start_streaming()`, modify the `DeepgramStreamingClient` constructor call. The `on_final_transcript` parameter currently points to `self._on_final_transcript` (the UI callback). We need to wrap it so both the UI callback AND the segment handler fire.

Replace (around line 174):
```python
            on_final_transcript=self._on_final_transcript,
```
with:
```python
            on_final_transcript=self._on_final_transcript_with_storage,
```

And add a new wrapper method after `_handle_meeting_segment`:

```python
    def _on_final_transcript_with_storage(self, text: str) -> None:
        """Handle final transcript: store segment AND notify UI."""
        self._handle_meeting_segment(text)
        if self._on_final_transcript:
            self._on_final_transcript(text)
```

### Step 4: Run integration tests

```bash
.venv/bin/python -m pytest tests/test_meeting_integration.py --no-cov -v
```

Expected: All 6 tests PASS

### Step 5: Run ALL tests to verify no regressions

```bash
.venv/bin/python -m pytest tests/ --no-cov -v
```

Expected: All tests PASS (existing + new)

### Step 6: Run ruff

```bash
.venv/bin/ruff check app_controller.py tests/test_meeting_integration.py
```

Expected: `All checks passed!`

### Step 7: Commit

```bash
git add app_controller.py tests/test_meeting_integration.py
git commit -m "feat(DAR2-25): integrate MeetingStore into AppController

start_streaming creates a meeting, final transcript callbacks append
segments in real-time, stop_streaming finalizes the meeting. Storage
is opt-in via the meeting_store property — no changes when unset."
```

---

## Task 5: Final verification and cleanup

### Step 1: Run the full test suite

```bash
.venv/bin/python -m pytest tests/ --no-cov -v
```

Expected: ALL tests pass

### Step 2: Run ruff on entire codebase

```bash
.venv/bin/ruff check .
```

Expected: `All checks passed!`

### Step 3: Verify acceptance criteria

Manually verify each from the Linear ticket:

1. **Meeting sessions stored with start/end times** — `test_start_meeting_sets_start_time`, `test_end_meeting_sets_end_time`
2. **Transcript segments appended in real-time without blocking audio** — `append_segment` uses a lock only for the INSERT; audio thread is not blocked because the lock is held for microseconds
3. **Full transcript retrievable after meeting ends** — `test_get_full_transcript`, `test_full_transcript_reconstruction`
4. **60-minute meeting transcript stored and retrieved in < 1 second** — `test_60_minute_meeting_retrieval_under_1_second`

### Step 4: Clean up stale `.pyc` files

```bash
rm -rf storage/__pycache__/
```

### Step 5: Final commit (if any cleanup was needed)

```bash
git add -A
git status  # verify only expected files
git commit -m "chore(DAR2-25): remove stale pyc files from storage/"
```
