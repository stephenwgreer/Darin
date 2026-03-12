"""File-based storage for meeting transcripts.

Each meeting is stored as a directory:

  ~/.darin-audio-assistant/meetings/
    2026-03-11_134304/
      meta.txt          ← line 1: start ISO, line 2: end ISO (blank if active)
      transcript.txt    ← one segment per line, appended in real time
      segments.tsv      ← ISO_TIMESTAMP<TAB>text per line (for time-range queries)
      analyses/
        <prompt_id>.txt ← one file per prompt

Thread safety: a threading.Lock serializes all writes.
"""

from __future__ import annotations

import shutil
import threading
from datetime import UTC, datetime
from pathlib import Path

from loguru import logger

from storage.models import MeetingRecord, TranscriptSegment


_DEFAULT_BASE_DIR = Path.home() / ".darin-audio-assistant" / "meetings"


class MeetingStore:
    """File-based store for meeting transcripts and analyses."""

    def __init__(self, base_dir: Path | None = None) -> None:
        self._base_dir = base_dir or _DEFAULT_BASE_DIR
        self._base_dir.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        logger.debug("MeetingStore initialized", base_dir=str(self._base_dir))

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _meeting_dir(self, meeting_id: str) -> Path:
        return self._base_dir / meeting_id

    def _transcript_path(self, meeting_id: str) -> Path:
        return self._meeting_dir(meeting_id) / "transcript.txt"

    def _segments_path(self, meeting_id: str) -> Path:
        return self._meeting_dir(meeting_id) / "segments.tsv"

    def _meta_path(self, meeting_id: str) -> Path:
        return self._meeting_dir(meeting_id) / "meta.txt"

    def _analyses_dir(self, meeting_id: str) -> Path:
        return self._meeting_dir(meeting_id) / "analyses"

    def _read_meta(self, meeting_id: str) -> tuple[datetime, datetime | None]:
        """Read start_time and optional end_time from meta.txt."""
        lines = self._meta_path(meeting_id).read_text(encoding="utf-8").splitlines()
        start_time = datetime.fromisoformat(lines[0])
        end_time = datetime.fromisoformat(lines[1]) if len(lines) > 1 and lines[1] else None
        return start_time, end_time

    def _read_title(self, meeting_id: str) -> str | None:
        path = self._meeting_dir(meeting_id) / "title.txt"
        if not path.exists():
            return None
        return path.read_text(encoding="utf-8").strip() or None

    # ------------------------------------------------------------------
    # Meeting lifecycle
    # ------------------------------------------------------------------

    def start_meeting(self, title: str | None = None) -> str:  # noqa: ARG002
        """Create a new meeting directory. Returns the meeting ID (folder name)."""
        now = datetime.now(tz=UTC)
        base_id = now.strftime("%Y-%m-%d_%H%M%S")

        # Handle same-second collisions (e.g. in tests)
        with self._lock:
            meeting_id = base_id
            counter = 1
            while self._meeting_dir(meeting_id).exists():
                meeting_id = f"{base_id}_{counter}"
                counter += 1

            meeting_dir = self._meeting_dir(meeting_id)
            meeting_dir.mkdir(parents=True)
            self._analyses_dir(meeting_id).mkdir()
            self._meta_path(meeting_id).write_text(now.isoformat() + "\n", encoding="utf-8")

        logger.info("Meeting started", meeting_id=meeting_id)
        return meeting_id

    def end_meeting(self, meeting_id: str) -> None:
        """Record end time in meta.txt."""
        meta_path = self._meta_path(meeting_id)
        if not meta_path.exists():
            return
        now = datetime.now(tz=UTC)
        with self._lock:
            start_line = meta_path.read_text(encoding="utf-8").splitlines()[0]
            meta_path.write_text(f"{start_line}\n{now.isoformat()}\n", encoding="utf-8")
        logger.info("Meeting ended", meeting_id=meeting_id)

    def save_title(self, meeting_id: str, title: str) -> None:
        """Save a generated title for a meeting (title.txt alongside meta.txt)."""
        path = self._meeting_dir(meeting_id) / "title.txt"
        with self._lock:
            path.write_text(title.strip(), encoding="utf-8")
        logger.debug("Title saved", meeting_id=meeting_id)

    # ------------------------------------------------------------------
    # Segment operations (real-time append)
    # ------------------------------------------------------------------

    def append_segment(self, meeting_id: str, text: str) -> None:
        """Append a transcript segment. Empty/whitespace text is silently ignored."""
        if not text or not text.strip():
            return
        now = datetime.now(tz=UTC).isoformat()
        with self._lock:
            with self._transcript_path(meeting_id).open("a", encoding="utf-8") as f:
                f.write(text.strip() + "\n")
            with self._segments_path(meeting_id).open("a", encoding="utf-8") as f:
                f.write(f"{now}\t{text.strip()}\n")

    # ------------------------------------------------------------------
    # Retrieval
    # ------------------------------------------------------------------

    def get_meeting(self, meeting_id: str) -> MeetingRecord | None:
        """Retrieve a meeting record with all transcript segments."""
        meta_path = self._meta_path(meeting_id)
        if not meta_path.exists():
            return None

        start_time, end_time = self._read_meta(meeting_id)
        segments: list[TranscriptSegment] = []

        seg_path = self._segments_path(meeting_id)
        if seg_path.exists():
            for line in seg_path.read_text(encoding="utf-8").splitlines():
                if "\t" not in line:
                    continue
                ts_str, seg_text = line.split("\t", 1)
                segments.append(
                    TranscriptSegment(
                        timestamp=datetime.fromisoformat(ts_str),
                        text=seg_text,
                        meeting_id=meeting_id,
                    )
                )

        return MeetingRecord(
            id=meeting_id,
            start_time=start_time,
            end_time=end_time,
            segments=segments,
            title=self._read_title(meeting_id),
        )

    def get_full_transcript(self, meeting_id: str) -> str:
        """Return all transcript text as a single space-joined string."""
        path = self._transcript_path(meeting_id)
        if not path.exists():
            return ""
        lines = path.read_text(encoding="utf-8").splitlines()
        return " ".join(line for line in lines if line)

    def list_meetings(self) -> list[MeetingRecord]:
        """List all meetings, newest first. Segments are NOT loaded."""
        meetings = []
        for d in sorted(self._base_dir.iterdir(), reverse=True):
            if not d.is_dir():
                continue
            meta_path = d / "meta.txt"
            if not meta_path.exists():
                continue
            start_time, end_time = self._read_meta(d.name)
            meetings.append(
                MeetingRecord(
                    id=d.name,
                    start_time=start_time,
                    end_time=end_time,
                    title=self._read_title(d.name),
                )
            )
        return meetings

    def get_transcript_segment_range(
        self,
        meeting_id: str,
        from_minute: int,
        to_minute: int,
    ) -> str:
        """Return transcript text for segments within a time window.

        Filters segments whose timestamps fall between from_minute and to_minute
        (inclusive) relative to the meeting start time.
        """
        meta_path = self._meta_path(meeting_id)
        if not meta_path.exists():
            return ""

        start_time, _ = self._read_meta(meeting_id)
        from_seconds = from_minute * 60
        to_seconds = to_minute * 60

        seg_path = self._segments_path(meeting_id)
        if not seg_path.exists():
            return ""

        results = []
        for line in seg_path.read_text(encoding="utf-8").splitlines():
            if "\t" not in line:
                continue
            ts_str, text = line.split("\t", 1)
            ts = datetime.fromisoformat(ts_str)
            offset = int((ts - start_time).total_seconds())
            if from_seconds <= offset <= to_seconds:
                results.append(text)

        return " ".join(results)

    # ------------------------------------------------------------------
    # Analysis persistence
    # ------------------------------------------------------------------

    def save_analysis(self, meeting_id: str, prompt_id: str, output_text: str) -> None:
        """Save (or overwrite) a post-meeting analysis result."""
        path = self._analyses_dir(meeting_id) / f"{prompt_id}.txt"
        with self._lock:
            path.write_text(output_text, encoding="utf-8")
        logger.debug("Analysis saved", meeting_id=meeting_id, prompt_id=prompt_id)

    def get_analysis(self, meeting_id: str, prompt_id: str) -> str | None:
        """Return saved analysis text, or None if not found."""
        path = self._analyses_dir(meeting_id) / f"{prompt_id}.txt"
        if not path.exists():
            return None
        return path.read_text(encoding="utf-8")

    def list_analyses_for_meeting(self, meeting_id: str) -> dict[str, str]:
        """Return all saved analyses for a meeting as {prompt_id: output_text}."""
        analyses_dir = self._analyses_dir(meeting_id)
        if not analyses_dir.exists():
            return {}
        return {p.stem: p.read_text(encoding="utf-8") for p in analyses_dir.glob("*.txt")}

    # ------------------------------------------------------------------
    # Deletion
    # ------------------------------------------------------------------

    def delete_meeting(self, meeting_id: str) -> None:
        """Delete a meeting directory and all its contents."""
        meeting_dir = self._meeting_dir(meeting_id)
        if not meeting_dir.exists():
            return
        with self._lock:
            shutil.rmtree(meeting_dir)
        logger.info("Meeting deleted", meeting_id=meeting_id)

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def close(self) -> None:
        """No-op — no connection to close."""
