"""
SessionStore: SQLite-backed persistence for Darin Audio Assistant sessions.

Database location: ~/.darin-audio-assistant/sessions.db

Threading: uses check_same_thread=False with an explicit threading.Lock() so
the connection can be shared across the main Qt thread and any background
threads that call save_session() in the future.

Note on strftime format codes:
    %-d and %-I (no-padding day / hour) are Linux/GNU libc extensions.
    This assumption is documented here; the app runs on WSL (Linux) only.
"""

import sqlite3
import threading
from datetime import datetime, timedelta
from pathlib import Path

from storage.models import AnalysisOutput, SessionData

# ---------------------------------------------------------------------------
# Schema DDL
# ---------------------------------------------------------------------------

_SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS schema_version (
    version     INTEGER PRIMARY KEY,
    applied_at  TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS sessions (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    title       TEXT NOT NULL,
    started_at  TEXT NOT NULL,
    ended_at    TEXT NOT NULL,
    duration_s  INTEGER NOT NULL,
    transcript  TEXT NOT NULL DEFAULT ''
);

CREATE TABLE IF NOT EXISTS session_analyses (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id  INTEGER NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
    prompt_id   TEXT NOT NULL,
    output_text TEXT NOT NULL,
    created_at  TEXT NOT NULL,
    UNIQUE(session_id, prompt_id)
);

CREATE INDEX IF NOT EXISTS idx_sessions_started_at
    ON sessions(started_at);

CREATE INDEX IF NOT EXISTS idx_analyses_session_id
    ON session_analyses(session_id);

INSERT OR IGNORE INTO schema_version(version, applied_at)
VALUES (1, datetime('now'));
"""

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _dt_to_iso(dt: datetime) -> str:
    """Convert datetime to ISO-8601 string for storage."""
    return dt.isoformat()


def _iso_to_dt(s: str) -> datetime:
    """Parse ISO-8601 string back to datetime."""
    return datetime.fromisoformat(s)


# ---------------------------------------------------------------------------
# SessionStore
# ---------------------------------------------------------------------------


class SessionStore:
    """Persists sessions and their analysis outputs in SQLite.

    Usage:
        store = SessionStore()
        session_id = store.save_session(session_data)
        sessions = store.list_sessions()
        detail = store.get_session(session_id)
        store.delete_session(session_id)
        store.close()
    """

    DB_PATH: Path = Path.home() / ".darin-audio-assistant" / "sessions.db"
    RETENTION_DAYS: int = 7
    MIN_DURATION_S: int = 10

    def __init__(self) -> None:
        # Ensure the directory exists
        self.DB_PATH.parent.mkdir(parents=True, exist_ok=True)

        # Open connection — check_same_thread=False allows use across threads;
        # the explicit _lock below serialises all access.
        self._conn = sqlite3.connect(str(self.DB_PATH), check_same_thread=False)
        self._conn.row_factory = sqlite3.Row

        # WAL mode for better write performance and crash safety
        self._conn.execute("PRAGMA journal_mode=WAL")
        # Enforce referential integrity (ON DELETE CASCADE for analyses)
        self._conn.execute("PRAGMA foreign_keys=ON")

        self._lock = threading.Lock()

        self._init_schema()
        self.purge_old_sessions()

    # ------------------------------------------------------------------
    # Schema
    # ------------------------------------------------------------------

    def _init_schema(self) -> None:
        """Create tables if they do not already exist."""
        with self._lock:
            self._conn.executescript(_SCHEMA_SQL)
            self._conn.commit()

    # ------------------------------------------------------------------
    # Write operations
    # ------------------------------------------------------------------

    def save_session(self, session: SessionData) -> int | None:
        """Persist a completed session to the database.

        Returns the new row ID, or None if the session is shorter than
        MIN_DURATION_S and was silently discarded.
        """
        if session.duration_s < self.MIN_DURATION_S:
            return None

        with self._lock:
            with self._conn:
                cursor = self._conn.cursor()
                cursor.execute(
                    """
                    INSERT INTO sessions
                        (title, started_at, ended_at, duration_s, transcript)
                    VALUES (?, ?, ?, ?, ?)
                    """,
                    (
                        session.title,
                        _dt_to_iso(session.started_at),
                        _dt_to_iso(session.ended_at),
                        session.duration_s,
                        session.transcript,
                    ),
                )
                session_id: int = cursor.lastrowid  # type: ignore[assignment]

                for analysis in session.analyses:
                    cursor.execute(
                        """
                        INSERT OR REPLACE INTO session_analyses
                            (session_id, prompt_id, output_text, created_at)
                        VALUES (?, ?, ?, ?)
                        """,
                        (
                            session_id,
                            analysis.prompt_id,
                            analysis.output_text,
                            _dt_to_iso(analysis.created_at),
                        ),
                    )
            return session_id

    def delete_session(self, session_id: int) -> None:
        """Delete a session and its analyses.

        The ON DELETE CASCADE foreign key constraint removes child rows in
        session_analyses automatically (PRAGMA foreign_keys=ON is required).
        """
        with self._lock:
            with self._conn:
                self._conn.execute(
                    "DELETE FROM sessions WHERE id = ?", (session_id,)
                )

    def purge_old_sessions(self) -> int:
        """Delete sessions older than RETENTION_DAYS.

        Returns the number of sessions deleted.
        """
        cutoff = datetime.now() - timedelta(days=self.RETENTION_DAYS)
        cutoff_iso = _dt_to_iso(cutoff)

        with self._lock:
            with self._conn:
                cursor = self._conn.execute(
                    "DELETE FROM sessions WHERE started_at < ?", (cutoff_iso,)
                )
            return cursor.rowcount

    # ------------------------------------------------------------------
    # Read operations
    # ------------------------------------------------------------------

    def list_sessions(self) -> list[SessionData]:
        """Return all sessions in reverse-chronological order.

        Analyses are NOT loaded — use get_session() for full detail.
        The analysis_count field is populated via a COUNT subquery so
        the history UI can display "N analyses" without a second query.
        """
        with self._lock:
            cursor = self._conn.execute(
                """
                SELECT
                    s.id,
                    s.title,
                    s.started_at,
                    s.ended_at,
                    s.duration_s,
                    s.transcript,
                    COUNT(sa.id) AS analysis_count
                FROM sessions s
                LEFT JOIN session_analyses sa ON sa.session_id = s.id
                GROUP BY s.id
                ORDER BY s.started_at DESC
                """
            )
            rows = cursor.fetchall()

        sessions: list[SessionData] = []
        for row in rows:
            sessions.append(
                SessionData(
                    id=row["id"],
                    title=row["title"],
                    started_at=_iso_to_dt(row["started_at"]),
                    ended_at=_iso_to_dt(row["ended_at"]),
                    duration_s=row["duration_s"],
                    transcript=row["transcript"],
                    analyses=[],
                    analysis_count=row["analysis_count"],
                )
            )
        return sessions

    def get_session(self, session_id: int) -> SessionData | None:
        """Return a full session including all analysis outputs.

        Returns None if the session does not exist.
        """
        with self._lock:
            row = self._conn.execute(
                "SELECT * FROM sessions WHERE id = ?", (session_id,)
            ).fetchone()

            if row is None:
                return None

            analysis_rows = self._conn.execute(
                """
                SELECT prompt_id, output_text, created_at
                FROM session_analyses
                WHERE session_id = ?
                ORDER BY id
                """,
                (session_id,),
            ).fetchall()

        analyses: list[AnalysisOutput] = [
            AnalysisOutput(
                prompt_id=ar["prompt_id"],
                output_text=ar["output_text"],
                created_at=_iso_to_dt(ar["created_at"]),
            )
            for ar in analysis_rows
        ]

        return SessionData(
            id=row["id"],
            title=row["title"],
            started_at=_iso_to_dt(row["started_at"]),
            ended_at=_iso_to_dt(row["ended_at"]),
            duration_s=row["duration_s"],
            transcript=row["transcript"],
            analyses=analyses,
            analysis_count=len(analyses),
        )

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def close(self) -> None:
        """Close the database connection."""
        self._conn.close()
