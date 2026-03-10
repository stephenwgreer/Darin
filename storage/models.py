"""Data models for meeting transcript storage (DAR2-25, DAR2-27)."""

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
class MeetingAnalysis:
    """A saved post-meeting analysis result (DAR2-27)."""

    meeting_id: int
    prompt_id: str
    output_text: str
    created_at: datetime
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
