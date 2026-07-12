"""Auto-Answer gating policy — pure, code-enforced, injectable clock."""
from __future__ import annotations

import time
from collections.abc import Callable


QUESTION_TRIGGER = "question_at_user"
AUTO_ANSWER_TRIGGER = "auto_answer"


class AutoAnswerPolicy:
    """Decide whether a watcher card should auto-trigger an answer run.

    No I/O, injectable clock. At most one auto-answer per cooldown window;
    never for a non-question trigger; never when the meeting is not active;
    never twice for the same in-flight source card.
    """

    def __init__(
        self,
        *,
        cooldown_seconds: float = 20.0,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self.cooldown_seconds = cooldown_seconds
        self._clock = clock
        self._last_answer_at: float | None = None
        self._inflight: set[str] = set()

    def should_answer(
        self,
        *,
        enabled: bool,
        trigger: str | None,
        meeting_active: bool,
        source_card_id: str,
    ) -> tuple[bool, str]:
        if not enabled:
            return False, "disabled"
        if trigger != QUESTION_TRIGGER:
            return False, "wrong_trigger"
        if not meeting_active:
            return False, "not_active"
        if source_card_id in self._inflight:
            return False, "in_flight"
        if (
            self._last_answer_at is not None
            and self._clock() - self._last_answer_at < self.cooldown_seconds
        ):
            return False, "cooldown"
        return True, ""

    def note_started(self, source_card_id: str) -> None:
        """Arm the in-flight guard BEFORE spawning the run (prevents double-fire)."""
        self._inflight.add(source_card_id)

    def note_accepted(self) -> None:
        """Arm the cooldown — only once the reactive run was actually accepted.

        A rejected run (e.g. a manual Answer-this click already holds the lane)
        must not start the cooldown, or genuine questions in the next 20s would
        be silently dropped.
        """
        self._last_answer_at = self._clock()

    def note_finished(self, source_card_id: str) -> None:
        self._inflight.discard(source_card_id)
