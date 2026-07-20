from __future__ import annotations

import threading

from services.speculative_question import (
    Decision,
    SpeculativeQuestionPolicy,
    SpeculativeRules,
    question_key,
)


class FakeClock:
    def __init__(self, start: float = 1000.0) -> None:
        self.now = start

    def __call__(self) -> float:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += seconds


def _policy(
    clock: FakeClock | None = None, rules: SpeculativeRules | None = None
) -> SpeculativeQuestionPolicy:
    return SpeculativeQuestionPolicy(rules, clock=clock or FakeClock())


# --- Detection matrix -----------------------------------------------------


def test_name_plus_second_person_fires() -> None:
    policy = _policy()
    decision, hit = policy.on_interim("Stephen, can you walk us through this?", "THEM")
    assert decision == Decision.FIRE
    assert hit is not None
    assert hit.rule == "name_second_person"


def test_interrogative_stem_fires() -> None:
    policy = _policy()
    decision, hit = policy.on_interim("does your team support that workflow", "THEM")
    assert decision == Decision.FIRE
    assert hit is not None
    assert hit.rule == "interrogative_stem"


def test_handoff_phrase_fires() -> None:
    policy = _policy()
    decision, hit = policy.on_interim("so that's the rollout plan, over to you", "THEM")
    assert decision == Decision.FIRE
    assert hit is not None
    assert hit.rule == "handoff_phrase"


def test_challenge_form_fires() -> None:
    policy = _policy()
    decision, hit = policy.on_interim("don't you think that's risky", "THEM")
    assert decision == Decision.FIRE
    assert hit is not None
    assert hit.rule == "challenge_form"


def test_no_match_holds() -> None:
    policy = _policy()
    decision, hit = policy.on_interim("we shipped the report yesterday", "THEM")
    assert decision == Decision.HOLD
    assert hit is None


def test_third_person_mention_is_not_a_hit() -> None:
    """Regression: narration referencing the user by name in third person
    must never be treated as a direct question."""
    policy = _policy()
    decision, hit = policy.on_interim(
        "as Stephen mentioned earlier, the numbers were solid", "THEM"
    )
    assert decision == Decision.HOLD
    assert hit is None


def test_third_person_mention_variants_guarded() -> None:
    policy = _policy()
    for text in (
        "when Stephen said that, everyone agreed",
        "like Steven noted, it's on track",
        "as Stephen pointed out, we need more time",
    ):
        decision, hit = policy.on_interim(text, "THEM")
        assert decision == Decision.HOLD, text
        assert hit is None, text


def test_me_speaker_always_holds() -> None:
    policy = _policy()
    decision, hit = policy.on_interim("Stephen, can you clarify that?", "ME")
    assert decision == Decision.HOLD
    assert hit is None


# --- Name-final-pause gap proxy --------------------------------------------


def test_name_utterance_final_allowed_after_sufficient_gap() -> None:
    clock = FakeClock()
    policy = _policy(clock)
    # Prime last-interim timestamp with an earlier, non-matching THEM interim.
    policy.on_interim("well, let's see", "THEM")
    clock.advance(0.8)
    decision, hit = policy.on_interim("what do you think, Stephen", "THEM")
    assert decision == Decision.FIRE
    assert hit is not None


def test_name_utterance_final_rejected_with_short_gap() -> None:
    clock = FakeClock()
    policy = _policy(clock)
    policy.on_interim("well, let's see", "THEM")
    clock.advance(0.3)
    decision, hit = policy.on_interim("quick thought, Stephen", "THEM")
    assert decision == Decision.HOLD
    assert hit is None


# --- Cooldowns --------------------------------------------------------------


def test_global_cooldown_blocks_second_fire() -> None:
    clock = FakeClock()
    policy = _policy(clock)
    decision, hit = policy.on_interim("Stephen, can you confirm the date", "THEM")
    assert decision == Decision.FIRE
    assert hit is not None
    policy.note_fired(hit.question_key)

    clock.advance(1.0)
    decision2, hit2 = policy.on_interim("does your team have bandwidth", "THEM")
    assert decision2 == Decision.HOLD
    assert hit2 is not None

    clock.advance(3.1)  # total 4.1s
    decision3, hit3 = policy.on_interim("does your team have bandwidth", "THEM")
    assert decision3 == Decision.FIRE
    assert hit3 is not None


def test_same_question_cooldown_blocks_repeat_within_window() -> None:
    clock = FakeClock()
    policy = _policy(clock)
    text = "Stephen, can you confirm the migration date"
    decision, hit = policy.on_interim(text, "THEM")
    assert decision == Decision.FIRE
    assert hit is not None
    policy.note_fired(hit.question_key)

    clock.advance(5.0)  # past global cooldown (4s), inside same-question (8s)
    decision2, hit2 = policy.on_interim(text, "THEM")
    assert decision2 == Decision.HOLD
    assert hit2 is not None

    clock.advance(3.1)  # total 8.1s since fire
    decision3, hit3 = policy.on_interim(text, "THEM")
    assert decision3 == Decision.FIRE
    assert hit3 is not None


# --- Supersede semantics -----------------------------------------------------


def test_utterance_final_no_pending_key_gated_fire() -> None:
    policy = _policy()
    decision, hit = policy.on_utterance_final(
        "THEM: Stephen, can you walk through the numbers?"
    )
    assert decision == Decision.FIRE
    assert hit is not None


def test_utterance_final_same_pending_key_holds() -> None:
    policy = _policy()
    transcript = "THEM: Stephen, can you walk through the numbers?"
    _, hit = policy.on_utterance_final(transcript)
    assert hit is not None
    policy.note_fired(hit.question_key)

    decision, hit2 = policy.on_utterance_final(transcript)
    assert decision == Decision.HOLD
    assert hit2 is not None
    assert hit2.question_key == hit.question_key


def test_utterance_final_different_pending_key_supersedes() -> None:
    policy = _policy()
    first = "THEM: Stephen, can you walk through the numbers?"
    _, hit = policy.on_utterance_final(first)
    assert hit is not None
    policy.note_fired(hit.question_key)

    second = "THEM: does your team support single sign-on"
    decision, hit2 = policy.on_utterance_final(second)
    assert decision == Decision.SUPERSEDE
    assert hit2 is not None
    assert hit2.question_key != hit.question_key


# --- Recently-answered guard -------------------------------------------------


def test_recently_answered_blocks_fire_within_window() -> None:
    clock = FakeClock()
    policy = _policy(clock)
    text = "does your platform support SAML"
    key = question_key(text)
    policy.note_answered(key)

    decision, hit = policy.on_interim(text, "THEM")
    assert decision == Decision.HOLD
    assert hit is not None

    clock.advance(45.1)
    decision2, hit2 = policy.on_interim(text, "THEM")
    assert decision2 == Decision.FIRE
    assert hit2 is not None


def test_was_recently_answered_default_now() -> None:
    policy = _policy()
    key = "some key"
    assert policy.was_recently_answered(key) is False
    policy.note_answered(key)
    assert policy.was_recently_answered(key) is True


# --- note_rejected un-arms ----------------------------------------------------


def test_note_rejected_unarms_cooldowns() -> None:
    clock = FakeClock()
    policy = _policy(clock)
    text = "Stephen, can you confirm the budget"
    decision, hit = policy.on_interim(text, "THEM")
    assert decision == Decision.FIRE
    assert hit is not None
    policy.note_fired(hit.question_key)

    policy.note_rejected()

    clock.advance(0.5)  # would still be inside both cooldowns if armed
    decision2, hit2 = policy.on_interim(text, "THEM")
    assert decision2 == Decision.FIRE
    assert hit2 is not None
    assert policy.fired_within(100.0) is False


# --- question_key properties ---------------------------------------------


def test_question_key_is_order_independent() -> None:
    a = question_key("can you confirm the launch date")
    b = question_key("the launch date, can you confirm")
    assert a == b


def test_question_key_never_contains_name() -> None:
    key = question_key("Stephen, can you confirm the launch date")
    assert "stephen" not in key
    assert "steven" not in key


def test_question_key_drops_stopwords() -> None:
    key = question_key("what do you think about the new pricing plan")
    tokens = key.split()
    assert "the" not in tokens
    assert "what" not in tokens
    assert "pricing" in tokens
    assert "plan" in tokens


# --- fired_within -------------------------------------------------------


def test_fired_within_reflects_last_fire_time() -> None:
    clock = FakeClock()
    policy = _policy(clock)
    assert policy.fired_within(10.0) is False

    policy.note_fired("some-key")
    assert policy.fired_within(10.0) is True

    clock.advance(10.1)
    assert policy.fired_within(10.0) is False


def test_clear_resets_all_state() -> None:
    clock = FakeClock()
    policy = _policy(clock)
    policy.note_fired("k1")
    policy.note_answered("k2")
    policy.on_interim("well, let's see", "THEM")

    policy.clear()

    assert policy.fired_within(1000.0) is False
    assert policy.was_recently_answered("k2") is False


# --- Thread-safety ---------------------------------------------------------


def test_concurrent_note_fired_and_note_answered_is_consistent() -> None:
    """Two threads hammer note_fired/note_answered concurrently; the lock
    must keep internal dict/float state consistent (no lost updates, no
    exceptions from concurrent dict mutation)."""
    policy = _policy()
    iterations = 500

    def fire_loop() -> None:
        for i in range(iterations):
            policy.note_fired(f"fire-key-{i % 10}")

    def answer_loop() -> None:
        for i in range(iterations):
            policy.note_answered(f"answer-key-{i % 10}")

    threads = [
        threading.Thread(target=fire_loop),
        threading.Thread(target=answer_loop),
        threading.Thread(target=fire_loop),
        threading.Thread(target=answer_loop),
    ]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    # No exceptions raised, and both dicts converged to the expected size
    # (10 distinct keys per loop; the lock prevents interleaved corruption).
    assert len(policy._fired_key_at) == 10
    assert len(policy._answered_at) == 10
    assert policy._last_fire_at is not None
