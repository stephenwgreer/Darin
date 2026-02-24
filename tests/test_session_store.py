"""
Unit Tests for SessionStore — DAR2-13: Session Persistence

Tests the SQLite-backed SessionStore class in storage/session_store.py.

Each test uses pytest's tmp_path fixture and monkeypatches SessionStore.DB_PATH
so the real ~/.darin-audio-assistant/sessions.db is never touched.

Test coverage:
    - save + retrieve round-trip (field-level assertions)
    - reverse-chronological ordering
    - analysis_count in list_sessions()
    - short-session discard (< MIN_DURATION_S)
    - MIN_DURATION_S boundary (exactly 10 s is kept)
    - purge_old_sessions() removes stale rows
    - purge_old_sessions() keeps recent rows
    - delete_session() cascades to session_analyses
    - INSERT OR REPLACE path (duplicate prompt_id within one session)
    - concurrent save_session() calls — no exceptions, all rows committed
    - DB file + directory created on first run
    - get_session() with unknown id returns None
"""

import sys
import threading
from datetime import datetime, timedelta
from pathlib import Path


sys.path.insert(0, str(Path(__file__).parent.parent))

import pytest

from storage.models import AnalysisOutput, SessionData
from storage.session_store import SessionStore


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_session(
    *,
    title: str = "Test Session",
    started_at: datetime | None = None,
    duration_s: int = 60,
    transcript: str = "Hello world.",
    analyses: list[AnalysisOutput] | None = None,
) -> SessionData:
    """Build a SessionData with sensible defaults."""
    now = started_at or datetime(2026, 2, 23, 10, 0, 0)
    return SessionData(
        title=title,
        started_at=now,
        ended_at=now + timedelta(seconds=duration_s),
        duration_s=duration_s,
        transcript=transcript,
        analyses=analyses or [],
    )


def _make_analysis(prompt_id: str = "topic_summary", output_text: str = "Summary text") -> AnalysisOutput:
    """Build an AnalysisOutput with sensible defaults."""
    return AnalysisOutput(
        prompt_id=prompt_id,
        output_text=output_text,
        created_at=datetime(2026, 2, 23, 10, 1, 0),
    )


@pytest.fixture
def store(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> SessionStore:
    """
    Create a SessionStore backed by a temporary database.

    monkeypatch replaces SessionStore.DB_PATH before instantiation so the
    constructor writes to tmp_path instead of ~/.darin-audio-assistant/.
    """
    db_file = tmp_path / "test_sessions.db"
    monkeypatch.setattr(SessionStore, "DB_PATH", db_file)
    s = SessionStore()
    yield s
    s.close()


# ---------------------------------------------------------------------------
# Test: save_and_retrieve_session
# ---------------------------------------------------------------------------


def test_save_and_retrieve_session(store: SessionStore) -> None:
    """
    GIVEN a session with two analyses
    WHEN saved and then retrieved via get_session()
    SHOULD return all fields with exact values
    """
    # Arrange
    started = datetime(2026, 2, 23, 9, 0, 0)
    analysis_a = AnalysisOutput(
        prompt_id="topic_summary",
        output_text="Topics: AI, testing.",
        created_at=datetime(2026, 2, 23, 9, 5, 0),
    )
    analysis_b = AnalysisOutput(
        prompt_id="sentiment_analysis",
        output_text="Sentiment: positive.",
        created_at=datetime(2026, 2, 23, 9, 6, 0),
    )
    session = _make_session(
        title="Morning Standup",
        started_at=started,
        duration_s=300,
        transcript="Let's discuss AI testing.",
        analyses=[analysis_a, analysis_b],
    )

    # Act
    session_id = store.save_session(session)
    result = store.get_session(session_id)  # type: ignore[arg-type]

    # Assert — top-level fields
    assert result is not None
    assert result.id == session_id
    assert result.title == "Morning Standup"
    assert result.transcript == "Let's discuss AI testing."
    assert result.duration_s == 300
    assert result.started_at == started
    assert result.ended_at == started + timedelta(seconds=300)

    # Assert — analyses (order preserved by INSERT order)
    assert len(result.analyses) == 2
    assert result.analyses[0].prompt_id == "topic_summary"
    assert result.analyses[0].output_text == "Topics: AI, testing."
    assert result.analyses[1].prompt_id == "sentiment_analysis"
    assert result.analyses[1].output_text == "Sentiment: positive."


# ---------------------------------------------------------------------------
# Test: list_sessions reverse-chronological order
# ---------------------------------------------------------------------------


def test_list_sessions_reverse_chronological(store: SessionStore) -> None:
    """
    GIVEN 3 sessions saved with timestamps one hour apart
    WHEN list_sessions() is called
    SHOULD return them newest-first
    """
    # Arrange — intentionally save in oldest-first order
    base = datetime(2026, 2, 23, 8, 0, 0)
    for offset_hours in range(3):
        store.save_session(
            _make_session(
                title=f"Session {offset_hours}",
                started_at=base + timedelta(hours=offset_hours),
            )
        )

    # Act
    sessions = store.list_sessions()

    # Assert
    assert len(sessions) == 3
    assert sessions[0].title == "Session 2"  # newest
    assert sessions[1].title == "Session 1"
    assert sessions[2].title == "Session 0"  # oldest


# ---------------------------------------------------------------------------
# Test: list_sessions analysis_count
# ---------------------------------------------------------------------------


def test_list_sessions_analysis_count(store: SessionStore) -> None:
    """
    GIVEN a session with 3 analyses
    WHEN list_sessions() is called
    SHOULD report analysis_count == 3 for that session
    """
    # Arrange
    analyses = [
        _make_analysis(prompt_id="summary"),
        _make_analysis(prompt_id="sentiment"),
        _make_analysis(prompt_id="keywords"),
    ]
    store.save_session(_make_session(analyses=analyses))

    # Act
    sessions = store.list_sessions()

    # Assert
    assert len(sessions) == 1
    assert sessions[0].analysis_count == 3


# ---------------------------------------------------------------------------
# Test: short session discarded
# ---------------------------------------------------------------------------


def test_short_session_discarded(store: SessionStore) -> None:
    """
    GIVEN a session shorter than MIN_DURATION_S (5 s < 10 s)
    WHEN save_session() is called
    SHOULD return None and not persist the session
    """
    # Arrange
    short_session = _make_session(duration_s=5)

    # Act
    result = store.save_session(short_session)

    # Assert
    assert result is None
    assert store.list_sessions() == []


# ---------------------------------------------------------------------------
# Test: MIN_DURATION_S boundary (exactly 10 s is kept)
# ---------------------------------------------------------------------------


def test_min_duration_boundary(store: SessionStore) -> None:
    """
    GIVEN a session with duration_s exactly equal to MIN_DURATION_S (10 s)
    WHEN save_session() is called
    SHOULD persist the session (boundary is inclusive)
    """
    # Arrange
    boundary_session = _make_session(duration_s=SessionStore.MIN_DURATION_S)

    # Act
    session_id = store.save_session(boundary_session)

    # Assert
    assert session_id is not None
    assert store.get_session(session_id) is not None


# ---------------------------------------------------------------------------
# Test: purge_old_sessions removes stale rows
# ---------------------------------------------------------------------------


def test_purge_old_sessions(store: SessionStore, monkeypatch: pytest.MonkeyPatch) -> None:
    """
    GIVEN a session whose started_at is 8 days ago (beyond RETENTION_DAYS=7)
    WHEN purge_old_sessions() is called
    SHOULD delete that session
    """
    # Arrange — bypass purge that runs in __init__ by saving after construction
    old_started = datetime.now() - timedelta(days=8)
    session = _make_session(started_at=old_started)
    session_id = store.save_session(session)
    assert session_id is not None

    # Act — call purge explicitly (also called in __init__, but session was saved after)
    deleted = store.purge_old_sessions()

    # Assert
    assert deleted >= 1
    assert store.get_session(session_id) is None


# ---------------------------------------------------------------------------
# Test: purge_old_sessions keeps recent rows
# ---------------------------------------------------------------------------


def test_purge_keeps_recent(store: SessionStore) -> None:
    """
    GIVEN a session 6 days old (within RETENTION_DAYS=7)
    WHEN purge_old_sessions() is called
    SHOULD leave the session intact
    """
    # Arrange
    recent_started = datetime.now() - timedelta(days=6)
    session = _make_session(started_at=recent_started)
    session_id = store.save_session(session)
    assert session_id is not None

    # Act
    store.purge_old_sessions()

    # Assert
    assert store.get_session(session_id) is not None


# ---------------------------------------------------------------------------
# Test: delete_session cascades to session_analyses
# ---------------------------------------------------------------------------


def test_delete_session_cascades(store: SessionStore) -> None:
    """
    GIVEN a session with two analyses
    WHEN delete_session() is called
    SHOULD remove both the session row and all child analysis rows
    """
    # Arrange
    analyses = [
        _make_analysis(prompt_id="summary"),
        _make_analysis(prompt_id="sentiment"),
    ]
    session_id = store.save_session(_make_session(analyses=analyses))
    assert session_id is not None

    # Act
    store.delete_session(session_id)

    # Assert — session gone
    assert store.get_session(session_id) is None

    # Assert — analyses gone (query directly through the connection)
    with store._lock:
        rows = store._conn.execute(
            "SELECT COUNT(*) FROM session_analyses WHERE session_id = ?",
            (session_id,),
        ).fetchone()
    assert rows[0] == 0


# ---------------------------------------------------------------------------
# Test: duplicate prompt_id overwrites via INSERT OR REPLACE
# ---------------------------------------------------------------------------


def test_duplicate_analysis_overwrite(store: SessionStore) -> None:
    """
    GIVEN a session saved with a 'topic_summary' analysis
    WHEN a second session with the same prompt_id is saved and retrieved
    SHOULD store the latest output_text for each prompt_id (last-write-wins)

    Note: INSERT OR REPLACE is scoped per (session_id, prompt_id), so each
    new session gets a fresh session_id.  We verify the last-write-wins path
    by saving a session that contains the same prompt_id twice — only the
    second value should survive because the UNIQUE constraint fires an OR REPLACE.
    """
    # Arrange — two analyses with the same prompt_id; second should win
    first_analysis = AnalysisOutput(
        prompt_id="topic_summary",
        output_text="First version",
        created_at=datetime(2026, 2, 23, 10, 0, 0),
    )
    second_analysis = AnalysisOutput(
        prompt_id="topic_summary",
        output_text="Overwritten version",
        created_at=datetime(2026, 2, 23, 10, 1, 0),
    )
    session = _make_session(analyses=[first_analysis, second_analysis])

    # Act
    session_id = store.save_session(session)
    result = store.get_session(session_id)  # type: ignore[arg-type]

    # Assert — only one row for topic_summary; last value wins
    assert result is not None
    topic_analyses = [a for a in result.analyses if a.prompt_id == "topic_summary"]
    assert len(topic_analyses) == 1
    assert topic_analyses[0].output_text == "Overwritten version"


# ---------------------------------------------------------------------------
# Test: concurrent writes — no exceptions, all sessions persisted
# ---------------------------------------------------------------------------


def test_concurrent_writes(store: SessionStore) -> None:
    """
    GIVEN 5 threads each calling save_session() simultaneously
    WHEN all threads complete
    SHOULD have saved all 5 sessions with no exceptions
    """
    # Arrange
    errors: list[Exception] = []
    saved_ids: list[int] = []
    lock = threading.Lock()

    def worker(index: int) -> None:
        try:
            session = _make_session(
                title=f"Concurrent Session {index}",
                started_at=datetime(2026, 2, 23, 10, index, 0),
            )
            session_id = store.save_session(session)
            if session_id is not None:
                with lock:
                    saved_ids.append(session_id)
        except Exception as exc:  # noqa: BLE001
            with lock:
                errors.append(exc)

    # Act
    threads = [threading.Thread(target=worker, args=(i,)) for i in range(5)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=10)

    # Assert
    assert errors == [], f"Concurrent writes raised exceptions: {errors}"
    assert len(saved_ids) == 5


# ---------------------------------------------------------------------------
# Test: DB file and directory created on first run
# ---------------------------------------------------------------------------


def test_db_created_on_first_run(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """
    GIVEN a DB_PATH pointing to a directory and file that do not yet exist
    WHEN SessionStore() is instantiated
    SHOULD create the parent directory and the .db file automatically
    """
    # Arrange — nested path that doesn't exist yet
    db_file = tmp_path / "new_dir" / "sessions.db"
    assert not db_file.parent.exists()

    monkeypatch.setattr(SessionStore, "DB_PATH", db_file)

    # Act
    s = SessionStore()
    s.close()

    # Assert
    assert db_file.parent.exists()
    assert db_file.exists()


# ---------------------------------------------------------------------------
# Test: get_session returns None for unknown id
# ---------------------------------------------------------------------------


def test_get_session_not_found(store: SessionStore) -> None:
    """
    GIVEN an empty database
    WHEN get_session() is called with an id that does not exist
    SHOULD return None
    """
    # Act
    result = store.get_session(99999)

    # Assert
    assert result is None
