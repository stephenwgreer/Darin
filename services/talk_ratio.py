"""Talk-ratio heads-up policy — pure, code-enforced, no LLM.

Watches the ME/THEM speaking-time split over a rolling window on the
*meeting* (Deepgram) timeline and, purely from arithmetic, decides when to
surface a lightweight ``heads_up`` card:

- ME-dominance: ME has held > ``me_dominance_frac`` of the spoken seconds in
  the window — a nudge to ask a question and let THEM talk.
- THEM-monologue: THEM has held the floor, uninterrupted, for more than
  ``them_monologue_s`` seconds — a nudge that the conversation may need a
  check-in.

Two DISTINCT clocks are in play and must never be mixed:

1. The **Deepgram/meeting timeline** (``start``/``duration`` from the ASR
   result, i.e. seconds since the meeting/stream began). Segment retention
   (window trimming) and monologue-length math use THIS clock, because it
   reflects when speech actually happened regardless of any processing lag.
2. The **monotonic wall clock** (``time.monotonic`` by default, injectable
   for tests). Only the emit COOLDOWN — how often we're allowed to nag the
   user in real time — uses this clock.

Mixing them would be a bug: e.g. trimming the window using monotonic time
would evict segments based on when this process happened to observe them
rather than when they were actually spoken.
"""

from __future__ import annotations

import time
import uuid
from collections import deque
from collections.abc import Callable

from services.cards import Card


# Personas for which the ME-dominance heads-up is meaningful. Deliberately
# EXCLUDES "technical": a technical SE is *expected* to talk more than THEM
# while explaining architecture, walking through a diagram, or answering a
# deep technical question — flagging that as "you're dominating" would be
# noise, not signal. THEM-monologue, by contrast, is persona-agnostic: an
# unusually long uninterrupted THEM run is worth flagging no matter who is
# running the call.
_ME_DOMINANCE_PERSONAS = frozenset({"general", "sales"})

_ME_DOMINANCE_TRIGGER = "talk_ratio"
_THEM_MONOLOGUE_TRIGGER = "them_monologue"


class TalkRatioPolicy:
    """Pure talk-ratio gating + card construction. No I/O, injectable clock."""

    def __init__(
        self,
        *,
        persona: str = "general",
        clock: Callable[[], float] = time.monotonic,
        window_s: float = 240.0,
        me_dominance_frac: float = 0.70,
        them_monologue_s: float = 90.0,
        emit_cooldown_s: float = 120.0,
    ) -> None:
        self.persona = persona
        self._clock = clock
        self.window_s = window_s
        self.me_dominance_frac = me_dominance_frac
        self.them_monologue_s = them_monologue_s
        self.emit_cooldown_s = emit_cooldown_s

        # (segment_end_time, speaker, duration_seconds) on the Deepgram
        # timeline — segment_end_time = start + duration.
        self._segments: deque[tuple[float, str, float]] = deque()
        # Monotonic wall-clock timestamp of the last emitted card (any kind).
        self._last_emit_at: float | None = None

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def observe(self, speaker: str | None, start: float, duration: float) -> Card | None:
        """Record one final ASR segment; return a Card if a threshold fires.

        Defensive by design: never raises. Malformed/negative timing or an
        unattributed speaker (``None``) is recorded harmlessly (or ignored)
        rather than breaking transcription.
        """
        try:
            return self._observe(speaker, start, duration)
        except Exception:  # noqa: BLE001 — the ASR callback must never die
            return None

    def reset(self) -> None:
        """Clear all state (new meeting)."""
        self._segments.clear()
        self._last_emit_at = None

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    def _observe(self, speaker: str | None, start: float, duration: float) -> Card | None:
        duration = float(duration or 0.0)
        start = float(start or 0.0)
        if duration <= 0.0 or speaker not in ("ME", "THEM"):
            return None

        segment_end = start + duration
        self._segments.append((segment_end, speaker, duration))
        self._trim_window(segment_end)

        card = self._check_me_dominance()
        if card is None:
            card = self._check_them_monologue()
        return card

    def _trim_window(self, newest_end: float) -> None:
        """Drop segments older than ``window_s`` relative to the newest
        segment's end time — trimming uses the Deepgram timeline, NOT the
        monotonic clock."""
        cutoff = newest_end - self.window_s
        while self._segments and self._segments[0][0] < cutoff:
            self._segments.popleft()

    def _window_span(self) -> float:
        """Seconds of meeting-timeline coverage currently held in the window."""
        if not self._segments:
            return 0.0
        oldest_end = self._segments[0][0] - self._segments[0][2]
        newest_end = self._segments[-1][0]
        return max(0.0, newest_end - oldest_end)

    def _check_me_dominance(self) -> Card | None:
        if self.persona not in _ME_DOMINANCE_PERSONAS:
            return None
        # Require at least half the window to be populated before judging —
        # avoids flagging dominance off a tiny, unrepresentative sample.
        if self._window_span() < (self.window_s / 2.0):
            return None

        me_seconds = sum(d for _, spk, d in self._segments if spk == "ME")
        total_seconds = sum(d for _, _spk, d in self._segments)
        if total_seconds <= 0.0:
            return None

        me_share = me_seconds / total_seconds
        if me_share <= self.me_dominance_frac:
            return None

        if not self._cooldown_elapsed():
            return None

        return self._build_card(
            trigger=_ME_DOMINANCE_TRIGGER,
            headline="You're talking 70%+ — ask one",
            topic_key="talk-ratio-me",
            cues=["ask one"],
        )

    def _check_them_monologue(self) -> Card | None:
        run_seconds = self._current_them_run_seconds()
        if run_seconds <= self.them_monologue_s:
            return None

        if not self._cooldown_elapsed():
            return None

        return self._build_card(
            trigger=_THEM_MONOLOGUE_TRIGGER,
            headline="THEM has held the floor 90s+",
            topic_key="talk-ratio-them",
            cues=["check in"],
        )

    def _current_them_run_seconds(self) -> float:
        """Sum of duration for the most recent contiguous run of THEM
        segments (i.e. walking backwards from the newest segment until a ME
        segment is hit)."""
        total = 0.0
        for _end, speaker, duration in reversed(self._segments):
            if speaker != "THEM":
                break
            total += duration
        return total

    def _cooldown_elapsed(self) -> bool:
        now = self._clock()
        return not (
            self._last_emit_at is not None and now - self._last_emit_at < self.emit_cooldown_s
        )

    def _build_card(
        self,
        *,
        trigger: str,
        headline: str,
        topic_key: str,
        cues: list[str],
    ) -> Card:
        self._last_emit_at = self._clock()
        return Card(
            id=f"card_{uuid.uuid4().hex[:12]}",
            lane="proactive",
            type="heads_up",
            trigger=trigger,
            headline=headline,
            cues=cues,
            confidence="high",
            urgency="fyi",
            source="transcript",
            disposition="render",
            topic_key=topic_key,
        )
