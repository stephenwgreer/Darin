from __future__ import annotations

from services.auto_answer import AutoAnswerPolicy


class FakeClock:
    def __init__(self, start: float = 1000.0) -> None:
        self.now = start

    def __call__(self) -> float:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += seconds


def _policy(clock: FakeClock | None = None) -> AutoAnswerPolicy:
    return AutoAnswerPolicy(clock=clock or FakeClock())


BASE = {
    "enabled": True,
    "trigger": "question_at_user",
    "meeting_active": True,
    "source_card_id": "c1",
}


def test_allowed_when_all_conditions_met() -> None:
    assert _policy().should_answer(**BASE) == (True, "")


def test_disabled_flag() -> None:
    assert _policy().should_answer(**{**BASE, "enabled": False}) == (False, "disabled")


def test_wrong_trigger() -> None:
    assert _policy().should_answer(**{**BASE, "trigger": "fact_check_them"}) == (
        False,
        "wrong_trigger",
    )
    assert _policy().should_answer(**{**BASE, "trigger": None}) == (False, "wrong_trigger")


def test_response_expected_trigger_allowed() -> None:
    assert _policy().should_answer(**{**BASE, "trigger": "response_expected"}) == (True, "")


def test_objection_trigger_allowed() -> None:
    assert _policy().should_answer(**{**BASE, "trigger": "objection"}) == (True, "")


def test_unrelated_trigger_still_rejected() -> None:
    assert _policy().should_answer(**{**BASE, "trigger": "fact_check"}) == (
        False,
        "wrong_trigger",
    )


def test_not_active() -> None:
    assert _policy().should_answer(**{**BASE, "meeting_active": False}) == (False, "not_active")


def test_in_flight_same_source() -> None:
    policy = _policy()
    policy.note_started("c1")
    assert policy.should_answer(**BASE) == (False, "in_flight")


def test_cooldown_boundary() -> None:
    clock = FakeClock()
    policy = _policy(clock)
    policy.note_started("c1")
    policy.note_accepted()
    clock.advance(19.9)
    assert policy.should_answer(**{**BASE, "source_card_id": "c2"}) == (False, "cooldown")
    clock.advance(0.2)  # 20.1s total
    assert policy.should_answer(**{**BASE, "source_card_id": "c2"}) == (True, "")


def test_note_finished_releases_slot() -> None:
    clock = FakeClock()
    policy = _policy(clock)
    policy.note_started("c1")
    policy.note_accepted()
    policy.note_finished("c1")
    # No longer in-flight, so the same source id now hits the cooldown gate.
    assert policy.should_answer(**BASE) == (False, "cooldown")
    clock.advance(20.1)
    assert policy.should_answer(**BASE) == (True, "")


def test_rejected_run_does_not_arm_cooldown() -> None:
    """A run rejected by the interactive lane (manual Answer-this in flight)
    must not start the cooldown — the next watcher question should go through
    immediately once the guard is released."""
    clock = FakeClock()
    policy = _policy(clock)
    policy.note_started("c1")  # armed before run_reactive_prompt...
    policy.note_finished("c1")  # ...which rejected: guard released, no note_accepted
    clock.advance(1.0)
    assert policy.should_answer(**{**BASE, "source_card_id": "c2"}) == (True, "")
