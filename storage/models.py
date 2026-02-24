"""
Data models for session persistence.

These are plain Python dataclasses — no framework dependencies.
They are the domain layer for the storage module.
"""

from dataclasses import dataclass, field
from datetime import datetime


@dataclass
class AnalysisOutput:
    """A single analysis output generated during a session.

    prompt_id: storage key, e.g. "topic_summary" or "sentiment_analysis"
    output_text: plain text accumulated during streaming (HTML tags stripped)
    created_at: wall-clock time when the analysis stream completed
    """

    prompt_id: str
    output_text: str
    created_at: datetime


@dataclass
class SessionData:
    """A complete session including its transcript and analysis outputs.

    id is None until the session has been persisted to the database.
    analysis_count is populated by list_sessions() via a COUNT subquery;
    it is NOT populated by get_session() (use len(analyses) there instead).
    """

    title: str
    started_at: datetime
    ended_at: datetime
    duration_s: int
    transcript: str
    analyses: list[AnalysisOutput] = field(default_factory=list)
    analysis_count: int = 0  # populated by list_sessions() COUNT query
    id: int | None = None
