from __future__ import annotations

from services.talk_ratio import TalkRatioPolicy


class FakeClock:
    """Injectable monotonic clock — governs ONLY the emit cooldown."""

    def __init__(self, start: float = 1000.0) -> None:
        self.now = start

    def __call__(self) -> float:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += seconds


def _policy(clock: FakeClock | None = None, **kwargs) -> TalkRatioPolicy:
    return TalkRatioPolicy(clock=clock or FakeClock(), **kwargs)


def _feed(policy: TalkRatioPolicy, segments: list[tuple[str, float, float]]):
    """Feed a list of (speaker, start, duration) segments; return the last
    non-None card produced (or None if nothing fired)."""
    result = None
    for speaker, start, duration in segments:
        card = policy.observe(speaker, start, duration)
        if card is not None:
            result = card
    return result


# ============================================================================
# ME-dominance
# ============================================================================


def test_me_dominance_fires_over_full_window():
    """ME talking >70% of a fully-populated window triggers talk_ratio."""
    policy = _policy(window_s=240.0, me_dominance_frac=0.70)
    segments = []
    t = 0.0
    # Build ~240s of window: alternate ME(15s)/THEM(3s) chunks -> ME dominant.
    while t < 240.0:
        segments.append(("ME", t, 15.0))
        t += 15.0
        segments.append(("THEM", t, 3.0))
        t += 3.0

    card = _feed(policy, segments)

    assert card is not None
    assert card.trigger == "talk_ratio"
    assert card.type == "heads_up"
    assert card.lane == "proactive"
    assert card.urgency == "fyi"
    assert card.disposition == "render"
    assert card.confidence == "high"
    assert card.source == "transcript"
    assert card.topic_key == "talk-ratio-me"
    assert "ask one" in card.cues


def test_me_dominance_does_not_fire_below_threshold():
    policy = _policy(window_s=240.0, me_dominance_frac=0.70)
    segments = []
    t = 0.0
    # Roughly 50/50 split -> should never fire.
    while t < 240.0:
        segments.append(("ME", t, 10.0))
        t += 10.0
        segments.append(("THEM", t, 10.0))
        t += 10.0

    card = _feed(policy, segments)
    assert card is None


def test_me_dominance_requires_half_full_window():
    """A tiny sample (well under half the window) must not trigger dominance,
    even if 100% ME so far."""
    policy = _policy(window_s=240.0, me_dominance_frac=0.70)
    card = policy.observe("ME", 0.0, 20.0)  # only 20s of a 240s window
    assert card is None


def test_me_dominance_excluded_for_technical_persona():
    """Technical SEs are EXPECTED to talk more while explaining architecture —
    ME-dominance must never fire for persona='technical'."""
    policy = _policy(persona="technical", window_s=240.0, me_dominance_frac=0.70)
    segments = []
    t = 0.0
    while t < 240.0:
        segments.append(("ME", t, 15.0))
        t += 15.0
        segments.append(("THEM", t, 3.0))
        t += 3.0

    card = _feed(policy, segments)
    assert card is None


def test_me_dominance_fires_for_general_and_sales():
    for persona in ("general", "sales"):
        policy = _policy(persona=persona, window_s=240.0, me_dominance_frac=0.70)
        segments = []
        t = 0.0
        while t < 240.0:
            segments.append(("ME", t, 15.0))
            t += 15.0
            segments.append(("THEM", t, 3.0))
            t += 3.0

        card = _feed(policy, segments)
        assert card is not None, f"expected dominance card for persona={persona}"
        assert card.trigger == "talk_ratio"


# ============================================================================
# THEM-monologue
# ============================================================================


def test_them_monologue_fires_over_threshold():
    policy = _policy(them_monologue_s=90.0)
    # A single contiguous THEM run > 90s.
    card = policy.observe("THEM", 0.0, 45.0)
    assert card is None  # 45s, not yet over threshold
    card = policy.observe("THEM", 45.0, 50.0)  # cumulative 95s
    assert card is not None
    assert card.trigger == "them_monologue"
    assert card.urgency == "fyi"
    assert card.topic_key == "talk-ratio-them"


def test_them_monologue_fires_for_technical_persona_too():
    """Unlike ME-dominance, THEM-monologue fires for ALL personas."""
    policy = _policy(persona="technical", them_monologue_s=90.0)
    policy.observe("THEM", 0.0, 50.0)
    card = policy.observe("THEM", 50.0, 50.0)
    assert card is not None
    assert card.trigger == "them_monologue"


def test_them_monologue_run_resets_on_me_interjection():
    policy = _policy(them_monologue_s=90.0)
    policy.observe("THEM", 0.0, 60.0)
    policy.observe("ME", 60.0, 1.0)  # brief interjection breaks the run
    card = policy.observe("THEM", 61.0, 60.0)  # only 60s into the new run
    assert card is None


# ============================================================================
# Emit cooldown (monotonic clock)
# ============================================================================


def test_emit_cooldown_suppresses_second_card_within_120s():
    clock = FakeClock()
    policy = _policy(clock, them_monologue_s=90.0, emit_cooldown_s=120.0)

    policy.observe("THEM", 0.0, 50.0)
    first = policy.observe("THEM", 50.0, 50.0)  # 100s -> fires
    assert first is not None

    clock.advance(60.0)  # only 60s of monotonic time elapsed (< 120s cooldown)
    # Keep accumulating a fresh, even-longer THEM run.
    second = policy.observe("THEM", 100.0, 60.0)  # cumulative run now huge
    assert second is None  # suppressed by cooldown

    clock.advance(61.0)  # total ~121s since first emit -> cooldown elapsed
    third = policy.observe("THEM", 160.0, 5.0)
    assert third is not None


def test_advancing_monotonic_alone_does_not_evict_segments():
    """The monotonic clock must NEVER affect window trimming — only the
    Deepgram/meeting timeline (segment end-times) does."""
    clock = FakeClock()
    policy = _policy(clock, window_s=240.0, me_dominance_frac=0.70)

    policy.observe("ME", 0.0, 20.0)
    assert len(policy._segments) == 1

    clock.advance(10_000.0)  # huge monotonic jump; segment timeline untouched

    assert len(policy._segments) == 1  # still there — not evicted by wall clock


def test_advancing_segment_time_evicts_old_segments():
    """Segments fall out of the window once newer segment end-times exceed
    window_s beyond them (measured on the Deepgram timeline)."""
    policy = _policy(window_s=100.0)

    policy.observe("ME", 0.0, 10.0)  # ends at t=10
    assert len(policy._segments) == 1

    # Newest segment ends at t=250, well beyond 100s past t=10 -> evicted.
    policy.observe("ME", 200.0, 50.0)
    ends = [seg[0] for seg in policy._segments]
    assert 10.0 not in ends


# ============================================================================
# reset()
# ============================================================================


def test_reset_clears_all_state():
    clock = FakeClock()
    policy = _policy(clock, them_monologue_s=90.0)

    policy.observe("THEM", 0.0, 50.0)
    card = policy.observe("THEM", 50.0, 50.0)
    assert card is not None

    policy.reset()

    assert len(policy._segments) == 0
    assert policy._last_emit_at is None

    # Post-reset, cooldown must not carry over: an immediate new monologue can
    # fire right away.
    policy.observe("THEM", 0.0, 50.0)
    fresh = policy.observe("THEM", 50.0, 50.0)
    assert fresh is not None


# ============================================================================
# Defensive behavior
# ============================================================================


def test_observe_never_raises_on_bad_input():
    policy = _policy()
    assert policy.observe(None, 0.0, 10.0) is None
    assert policy.observe("ME", -5.0, -1.0) is None
    assert policy.observe("UNKNOWN_SPEAKER", 0.0, 10.0) is None


def test_zero_duration_segment_ignored():
    policy = _policy()
    assert policy.observe("ME", 0.0, 0.0) is None
    assert len(policy._segments) == 0
