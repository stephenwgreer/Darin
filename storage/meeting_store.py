"""SQLite storage for meeting transcripts (DAR2-25, DAR2-27).

Thread-safe, WAL-mode SQLite database for persisting meeting sessions,
their transcript segments in real time, and post-meeting analysis results.
"""

from __future__ import annotations

import sqlite3
import threading
from datetime import UTC, datetime
from pathlib import Path

from loguru import logger

from storage.models import MeetingAnalysis, MeetingRecord, TranscriptSegment


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

CREATE TABLE IF NOT EXISTS meeting_analyses (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    meeting_id  INTEGER NOT NULL REFERENCES meetings(id) ON DELETE CASCADE,
    prompt_id   TEXT NOT NULL,
    output_text TEXT NOT NULL,
    created_at  TEXT NOT NULL,
    UNIQUE(meeting_id, prompt_id)
);

CREATE INDEX IF NOT EXISTS idx_meeting_analyses_meeting_id
    ON meeting_analyses(meeting_id);
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
        now = datetime.now(tz=UTC).isoformat()
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
        now = datetime.now(tz=UTC).isoformat()
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

        now = datetime.now(tz=UTC).isoformat()
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
            "SELECT text FROM transcript_segments WHERE meeting_id = ? ORDER BY timestamp, id",
            (meeting_id,),
        ).fetchall()
        return " ".join(row[0] for row in rows)

    def list_meetings(self) -> list[MeetingRecord]:
        """List all meetings, newest first. Segments are NOT loaded."""
        rows = self._conn.execute(
            "SELECT id, title, start_time, end_time FROM meetings ORDER BY start_time DESC",
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

    def get_transcript_segment_range(
        self,
        meeting_id: int,
        from_minute: int,
        to_minute: int,
    ) -> str:
        """Return transcript text for a time window relative to meeting start.

        Retrieves segments whose timestamps fall between ``from_minute`` and
        ``to_minute`` (inclusive) relative to the meeting's ``start_time``.
        If no segments fall in the range, returns an empty string.

        Args:
            meeting_id: The meeting to retrieve transcript from.
            from_minute: Start of window in minutes (0-based from meeting start).
            to_minute: End of window in minutes (inclusive).

        Returns:
            Space-joined transcript text for the selected window.
        """
        row = self._conn.execute(
            "SELECT start_time FROM meetings WHERE id = ?",
            (meeting_id,),
        ).fetchone()

        if row is None:
            return ""

        start_time = datetime.fromisoformat(row[0])
        from_seconds = from_minute * 60
        to_seconds = to_minute * 60

        rows = self._conn.execute(
            """
            SELECT text FROM transcript_segments
            WHERE meeting_id = ?
              AND CAST((julianday(timestamp) - julianday(?)) * 86400 AS INTEGER) >= ?
              AND CAST((julianday(timestamp) - julianday(?)) * 86400 AS INTEGER) <= ?
            ORDER BY timestamp, id
            """,
            (
                meeting_id,
                start_time.isoformat(),
                from_seconds,
                start_time.isoformat(),
                to_seconds,
            ),
        ).fetchall()

        return " ".join(r[0] for r in rows)

    # ------------------------------------------------------------------
    # Analysis persistence (DAR2-27)
    # ------------------------------------------------------------------

    def save_analysis(
        self,
        meeting_id: int,
        prompt_id: str,
        output_text: str,
    ) -> None:
        """Save (or overwrite) a post-meeting analysis result.

        Uses INSERT OR REPLACE keyed on (meeting_id, prompt_id).
        A re-run of the same prompt overwrites the previous result.

        Args:
            meeting_id: The meeting this analysis belongs to.
            prompt_id: Registry ID of the prompt that produced this result.
            output_text: The full analysis text returned by Claude.
        """
        now = datetime.now(tz=UTC).isoformat()
        with self._lock:
            self._conn.execute(
                """
                INSERT INTO meeting_analyses (meeting_id, prompt_id, output_text, created_at)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(meeting_id, prompt_id) DO UPDATE SET
                    output_text = excluded.output_text,
                    created_at  = excluded.created_at
                """,
                (meeting_id, prompt_id, output_text, now),
            )
            self._conn.commit()
        logger.debug("Analysis saved", meeting_id=meeting_id, prompt_id=prompt_id)

    def get_analysis(
        self,
        meeting_id: int,
        prompt_id: str,
    ) -> str | None:
        """Return saved analysis text for a (meeting_id, prompt_id) pair.

        Returns None if no analysis has been saved for this combination.
        """
        row = self._conn.execute(
            "SELECT output_text FROM meeting_analyses WHERE meeting_id = ? AND prompt_id = ?",
            (meeting_id, prompt_id),
        ).fetchone()
        return row[0] if row is not None else None

    def list_analyses_for_meeting(
        self,
        meeting_id: int,
    ) -> dict[str, str]:
        """Return all saved analyses for a meeting as {prompt_id: output_text}."""
        rows = self._conn.execute(
            "SELECT prompt_id, output_text FROM meeting_analyses WHERE meeting_id = ?",
            (meeting_id,),
        ).fetchall()
        return {row[0]: row[1] for row in rows}

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
