"""Tests for the proactive watcher — debounce/dedupe/cooldown rules.

Pure logic with a fake clock; no threads are started and no network is used.
"""

from __future__ import annotations

from unittest.mock import Mock

from services.cards import parse_card
from services.watcher import Watcher, WatcherPolicy, WatcherRules


class FakeClock:
    def __init__(self, start: float = 1000.0) -> None:
        self.now = start

    def __call__(self) -> float:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += seconds


def make_card(
    card_type: str = "answer",
    headline: str = "A headline",
    topic_key: str = "topic-a",
):
    card = parse_card(
        {"type": card_type, "headline": headline, "topic_key": topic_key},
        lane="proactive",
    )
    assert card is not None
    return card


# ---------------------------------------------------------------------------
# WatcherPolicy: tick gating (min 12 s AND >= 30 new words)
# ---------------------------------------------------------------------------


class TestTickGating:
    def test_first_tick_allowed_with_enough_words(self) -> None:
        policy = WatcherPolicy(clock=FakeClock())
        assert policy.should_tick(30) is True

    def test_tick_blocked_below_word_threshold(self) -> None:
        policy = WatcherPolicy(clock=FakeClock())
        assert policy.should_tick(29) is False

    def test_tick_blocked_within_12s_of_previous_tick(self) -> None:
        clock = FakeClock()
        policy = WatcherPolicy(clock=clock)
        policy.note_tick()
        clock.advance(11.9)
        assert policy.should_tick(100) is False

    def test_tick_allowed_after_12s_and_30_words(self) -> None:
        clock = FakeClock()
        policy = WatcherPolicy(clock=clock)
        policy.note_tick()
        clock.advance(12.1)
        assert policy.should_tick(30) is True

    def test_both_conditions_required(self) -> None:
        clock = FakeClock()
        policy = WatcherPolicy(clock=clock)
        policy.note_tick()
        clock.advance(60.0)  # plenty of time, too few words
        assert policy.should_tick(10) is False


# ---------------------------------------------------------------------------
# WatcherPolicy: card emission gating
# ---------------------------------------------------------------------------


class TestRenderCap:
    def test_global_render_cap_1_card_per_15s(self) -> None:
        clock = FakeClock()
        policy = WatcherPolicy(clock=clock)

        first = make_card(topic_key="t1")
        assert policy.filter_card(first) == (True, "")
        policy.note_rendered(first)

        clock.advance(14.9)
        second = make_card(card_type="status", topic_key="t2")
        allowed, reason = policy.filter_card(second)
        assert allowed is False
        assert reason == "render_cap"

        clock.advance(0.2)
        assert policy.filter_card(second)[0] is True


class TestTypeCooldown:
    def test_same_type_blocked_for_60s(self) -> None:
        clock = FakeClock()
        policy = WatcherPolicy(clock=clock)

        first = make_card(card_type="fact_check", topic_key="t1")
        policy.note_rendered(first)

        clock.advance(30.0)  # past render cap, inside type cooldown
        second = make_card(card_type="fact_check", topic_key="t2")
        allowed, reason = policy.filter_card(second)
        assert allowed is False
        assert reason == "type_cooldown"

        clock.advance(30.1)  # 60.1 s since first
        assert policy.filter_card(second)[0] is True

    def test_different_type_not_blocked_by_cooldown(self) -> None:
        clock = FakeClock()
        policy = WatcherPolicy(clock=clock)
        policy.note_rendered(make_card(card_type="fact_check", topic_key="t1"))

        clock.advance(16.0)
        other = make_card(card_type="answer", topic_key="t2")
        assert policy.filter_card(other)[0] is True


class TestTopicDedupe:
    def test_same_topic_blocked_for_5_minutes(self) -> None:
        clock = FakeClock()
        policy = WatcherPolicy(clock=clock)
        policy.note_rendered(make_card(card_type="answer", topic_key="redis"))

        clock.advance(120.0)  # past render cap + type cooldown
        repeat = make_card(card_type="status", topic_key="redis")
        allowed, reason = policy.filter_card(repeat)
        assert allowed is False
        assert reason == "topic_dedupe"

        clock.advance(200.0)  # 320 s since render — past the 300 s dedupe
        assert policy.filter_card(repeat)[0] is True


class TestDismissSuppression:
    def test_dismissed_topic_suppressed_forever(self) -> None:
        clock = FakeClock()
        policy = WatcherPolicy(clock=clock)
        policy.dismiss_topic("pricing")

        clock.advance(100_000.0)
        card = make_card(topic_key="pricing")
        allowed, reason = policy.filter_card(card)
        assert allowed is False
        assert reason == "dismissed_topic"

    def test_empty_topic_key_not_recorded(self) -> None:
        policy = WatcherPolicy(clock=FakeClock())
        policy.dismiss_topic("")
        assert policy.dismissed_topics == frozenset()


class TestRecentHeadlines:
    def test_last_5_headlines_kept(self) -> None:
        clock = FakeClock()
        policy = WatcherPolicy(
            WatcherRules(render_cap_seconds=0, type_cooldown_seconds=0, topic_dedupe_seconds=0),
            clock=clock,
        )
        for i in range(7):
            policy.note_rendered(make_card(headline=f"H{i}", topic_key=f"t{i}"))
            clock.advance(1.0)
        assert list(policy.recent_headlines) == ["H2", "H3", "H4", "H5", "H6"]


# ---------------------------------------------------------------------------
# Watcher: tick behaviour (synchronous _maybe_tick, mocked ApiClient)
# ---------------------------------------------------------------------------


def make_watcher(clock: FakeClock, cards=None, **kwargs) -> tuple[Watcher, Mock, list]:
    api_client = Mock()
    api_client.create_cards.return_value = cards if cards is not None else []
    emitted: list = []
    watcher = Watcher(
        api_client,
        on_card=emitted.append,
        clock=clock,
        **kwargs,
    )
    return watcher, api_client, emitted


class TestWatcherTicks:
    def test_no_llm_call_below_word_threshold(self) -> None:
        clock = FakeClock()
        watcher, api_client, _ = make_watcher(clock)

        watcher.on_utterance_end("THEM: short")
        watcher._maybe_tick()

        api_client.create_cards.assert_not_called()

    def test_one_llm_call_per_eligible_tick(self) -> None:
        clock = FakeClock()
        watcher, api_client, _ = make_watcher(clock)

        transcript = "THEM: " + "word " * 40
        watcher.on_utterance_end(transcript)
        watcher._maybe_tick()

        assert api_client.create_cards.call_count == 1
        kwargs = api_client.create_cards.call_args.kwargs
        assert kwargs["lane"] == "watcher"

        # Immediately after: same transcript, no new words — no second call
        watcher._maybe_tick()
        assert api_client.create_cards.call_count == 1

    def test_transcript_blocks_are_append_only(self) -> None:
        """Each tick appends only the NEW transcript text (incremental cache)."""
        clock = FakeClock()
        watcher, api_client, _ = make_watcher(clock)

        part1 = "THEM: " + "alpha " * 35
        watcher.on_utterance_end(part1)
        watcher._maybe_tick()

        clock.advance(13.0)
        part2 = part1 + "ME: " + "beta " * 35
        watcher.on_utterance_end(part2)
        watcher._maybe_tick()

        assert api_client.create_cards.call_count == 2
        assert watcher._transcript_blocks[0] == part1
        assert watcher._transcript_blocks[1] == part2[len(part1) :]

    def test_emitted_card_passes_through_policy(self) -> None:
        clock = FakeClock()
        card = make_card(topic_key="topic-x")
        watcher, _, emitted = make_watcher(clock, cards=[card])

        watcher.on_utterance_end("THEM: " + "word " * 40)
        watcher._maybe_tick()

        assert emitted == [card]

    def test_dismissed_topic_card_suppressed(self) -> None:
        clock = FakeClock()
        card = make_card(topic_key="topic-x")
        watcher, _, emitted = make_watcher(clock, cards=[card])

        watcher.dismiss_topic("topic-x")
        watcher.on_utterance_end("THEM: " + "word " * 40)
        watcher._maybe_tick()

        assert emitted == []

    def test_at_most_one_card_per_tick(self) -> None:
        clock = FakeClock()
        cards = [make_card(topic_key="a"), make_card(card_type="status", topic_key="b")]
        watcher, _, emitted = make_watcher(clock, cards=cards)

        watcher.on_utterance_end("THEM: " + "word " * 40)
        watcher._maybe_tick()

        assert len(emitted) == 1

    def test_recent_headlines_passed_into_tick_instruction(self) -> None:
        clock = FakeClock()
        card = make_card(headline="Shown already", topic_key="a")
        watcher, api_client, _ = make_watcher(clock, cards=[card])

        watcher.on_utterance_end("THEM: " + "word " * 40)
        watcher._maybe_tick()

        clock.advance(20.0)
        watcher.on_utterance_end("THEM: " + "word " * 40 + "more " * 35)
        watcher._maybe_tick()

        messages = api_client.create_cards.call_args.kwargs["messages"]
        instruction = messages[-1]["content"][0]["text"]
        assert "Shown already" in instruction

    def test_sales_persona_arms_sales_signal(self) -> None:
        clock = FakeClock()
        sales_watcher, _, _ = make_watcher(clock, persona="sales")
        general_watcher, _, _ = make_watcher(clock, persona="general")

        assert "sales_signal" in sales_watcher._system_text
        assert "sales_signal" not in general_watcher._system_text

    def test_llm_failure_does_not_crash_worker(self) -> None:
        clock = FakeClock()
        watcher, api_client, emitted = make_watcher(clock)
        api_client.create_cards.side_effect = RuntimeError("boom")
        statuses: list[str] = []
        watcher._on_status = statuses.append

        watcher.on_utterance_end("THEM: " + "word " * 40)
        try:
            watcher._maybe_tick()
        except RuntimeError:
            pass  # _run() catches this in the real thread loop

        # Status must be restored to "watching" even on failure
        assert statuses[-1] == "watching"
        assert emitted == []


class TestWatcherLifecycle:
    def test_start_stop_thread(self) -> None:
        watcher, _, _ = make_watcher(FakeClock())
        statuses: list[str] = []
        watcher._on_status = statuses.append

        watcher.start()
        assert watcher.is_running
        watcher.stop()
        assert not watcher.is_running
        assert statuses[0] == "watching"
        assert statuses[-1] == "stopped"

    def test_tick_finishing_after_stop_emits_nothing(self) -> None:
        """An LLM call in flight when the meeting ends must not emit a card
        or a trailing 'watching' status into the post-meeting UI."""
        clock = FakeClock()
        card = make_card(topic_key="late-topic")
        watcher, api_client, emitted = make_watcher(clock, cards=[card])
        statuses: list[str] = []
        watcher._on_status = statuses.append

        def slow_create_cards(**kwargs):
            # The meeting ends while the call is in flight
            watcher._stop_event.set()
            return [card]

        api_client.create_cards.side_effect = slow_create_cards

        watcher.on_utterance_end("THEM: " + "word " * 40)
        watcher._maybe_tick()

        assert emitted == []
        assert "watching" not in statuses  # post-stop status emissions suppressed

    def test_emissions_suppressed_once_stop_event_set(self) -> None:
        watcher, _, emitted = make_watcher(FakeClock())
        statuses: list[str] = []
        watcher._on_status = statuses.append

        watcher._stop_event.set()
        watcher._emit_card(make_card())
        watcher._emit_status("thinking")
        watcher._emit_status("stopped", force=True)  # stop()'s final emit passes

        assert emitted == []
        assert statuses == ["stopped"]
