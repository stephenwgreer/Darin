"""Proactive watcher lane — utterance-end ticks with code-enforced debounce.

The watcher runs in its OWN thread, completely outside the interactive lane.
It is started on meeting start and stopped on meeting end. On each Deepgram
UtteranceEnd event the controller calls :meth:`Watcher.on_utterance_end`; the
worker thread then decides whether to run ONE Haiku tick over the
incrementally-cached transcript.

All throttling is CODE, not prompt:
- min 8 s between LLM ticks AND >= 15 new words accumulated;
- global render cap: at most 1 interrupt card per 15 s (rails don't count);
- per-type cooldown: 60 s (skipped for response-expected-class triggers);
- topic dedupe (topic_key): 5 min (bypassed by an update:true refresh);
- user-dismissed topic_keys suppressed for the whole meeting;
- the last 5 shown (trigger, topic_key) pairs are passed into each tick prompt.

Each tick may emit AT MOST one interrupt card and one rail card (urgency=="fyi"
cards are rails and don't consume the interrupt budget), plus any number of
disposition="log" cards, which bypass all gating and never render live.

The pure gating rules live in :class:`WatcherPolicy` (injectable clock, no
I/O) so they are unit-testable without threads or network.
"""

from __future__ import annotations

import threading
import time
from collections import deque
from collections.abc import Callable
from dataclasses import dataclass

from loguru import logger

import config
from prompts.templates import WATCHER_TICK_INSTRUCTION, build_watcher_system
from services.cards import Card


# Trigger names exempt from per-type cooldown: response-expected moments must
# never be suppressed just because a same-typed card rendered recently. Both
# the legacy trigger name and its S3 replacement are listed during the rename
# transition.
NO_TYPE_COOLDOWN_TRIGGERS = frozenset({"response_expected", "question_at_user", "objection"})


@dataclass
class WatcherRules:
    """Tunable debounce/dedupe/cooldown thresholds (seconds / words)."""

    min_tick_seconds: float = 8.0
    min_new_words: int = 15
    render_cap_seconds: float = 15.0
    type_cooldown_seconds: float = 60.0
    topic_dedupe_seconds: float = 300.0


class WatcherPolicy:
    """Pure, code-enforced watcher gating rules. No I/O, injectable clock."""

    def __init__(
        self,
        rules: WatcherRules | None = None,
        *,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self.rules = rules or WatcherRules()
        self._clock = clock
        self._last_tick_at: float | None = None
        self._last_render_at: float | None = None
        self._last_type_at: dict[str, float] = {}
        self._last_topic_at: dict[str, float] = {}
        self._dismissed_topics: set[str] = set()
        # Last 5 (trigger, topic_key) pairs shown — fed into the next tick
        # prompt so the model can reuse an exact topic_key to refresh.
        self.recent_topics: deque[tuple[str, str]] = deque(maxlen=5)

    # ---- tick gating ----

    def should_tick(self, new_word_count: int) -> bool:
        """min 8 s since the last LLM tick AND >= 15 new words accumulated."""
        if new_word_count < self.rules.min_new_words:
            return False
        if self._last_tick_at is not None:
            if self._clock() - self._last_tick_at < self.rules.min_tick_seconds:
                return False
        return True

    def note_tick(self) -> None:
        self._last_tick_at = self._clock()

    # ---- card emission gating ----

    def filter_card(self, card: Card) -> tuple[bool, str]:
        """Return (allowed, reason). Reason is "" when allowed.

        CRITICAL: a card is a "rail" (passive, doesn't consume the interrupt
        budget) iff ``card.urgency == "fyi"``; every other value is an
        interrupt. Gating on ``urgency == "now"`` instead would be a trap —
        ``parse_card`` DEFAULTS urgency to "fyi", so an unset/legacy urgency
        must still land as a rail, and the render cap must still apply to
        every genuine interrupt (including any future non-"now" value).
        """
        now = self._clock()

        if card.topic_key in self._dismissed_topics:
            return False, "dismissed_topic"

        is_rail = card.urgency == "fyi"
        if (
            not is_rail
            and self._last_render_at is not None
            and now - self._last_render_at < self.rules.render_cap_seconds
        ):
            return False, "render_cap"

        if card.trigger not in NO_TYPE_COOLDOWN_TRIGGERS:
            last_type = self._last_type_at.get(card.type)
            if last_type is not None and now - last_type < self.rules.type_cooldown_seconds:
                return False, "type_cooldown"

        last_topic = self._last_topic_at.get(card.topic_key)
        if last_topic is not None and now - last_topic < self.rules.topic_dedupe_seconds:
            # An update:true card refreshes an evolving topic instead of being
            # deduped into silence.
            if not card.update:
                return False, "topic_dedupe"

        return True, ""

    def note_rendered(self, card: Card) -> None:
        now = self._clock()
        # Rails (urgency == "fyi") don't consume the interrupt render budget.
        if card.urgency != "fyi":
            self._last_render_at = now
        self._last_type_at[card.type] = now
        self._last_topic_at[card.topic_key] = now
        self.recent_topics.append((card.trigger or card.type, card.topic_key))

    def dismiss_topic(self, topic_key: str) -> None:
        """Suppress a topic_key for the remainder of the meeting."""
        if topic_key:
            self._dismissed_topics.add(topic_key)

    @property
    def dismissed_topics(self) -> frozenset[str]:
        return frozenset(self._dismissed_topics)


class Watcher:
    """Utterance-end-driven proactive card service (one Haiku tick at a time)."""

    def __init__(
        self,
        api_client,  # noqa: ANN001 — ApiClient (duck-typed for tests)
        *,
        persona: str = "general",
        context_pack_text: str = "",
        on_card: Callable[[Card], None] | None = None,
        on_status: Callable[[str], None] | None = None,
        on_log_item: Callable[[Card], None] | None = None,
        model: str = config.WATCHER_MODEL,
        max_tokens: int = config.WATCHER_MAX_TOKENS,
        rules: WatcherRules | None = None,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._api_client = api_client
        self._persona = persona
        self._system_text = build_watcher_system(persona)
        self._context_pack_text = context_pack_text
        self._on_card = on_card
        self._on_status = on_status
        self._on_log_item = on_log_item
        self._model = model
        self._max_tokens = max_tokens
        self.policy = WatcherPolicy(rules, clock=clock)

        # Incrementally-cached transcript: append-only blocks + consumed offset.
        self._transcript_blocks: list[str] = []
        self._consumed_chars = 0
        self._latest_transcript = ""

        self._lock = threading.Lock()
        self._wake = threading.Event()
        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    @property
    def is_running(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    def start(self) -> None:
        if self.is_running:
            logger.warning("Watcher already running")
            return
        self._stop_event.clear()
        self._thread = threading.Thread(target=self._run, name="watcher", daemon=True)
        self._thread.start()
        self._emit_status("watching")
        logger.info("Watcher started", persona=self._persona, model=self._model)

    def stop(self) -> None:
        if self._thread is None:
            return
        self._stop_event.set()
        self._wake.set()
        # An in-flight LLM tick can outlive this join (WATCHER_TIMEOUT_S > the
        # join timeout). That's fine: once _stop_event is set, _emit_card /
        # _emit_status suppress all further emissions, so a late tick can never
        # push a card or a "watching" status into the post-meeting UI.
        self._thread.join(timeout=2.0)
        self._thread = None
        self._emit_status("stopped", force=True)
        logger.info("Watcher stopped")

    # ------------------------------------------------------------------
    # Inputs (called from other threads)
    # ------------------------------------------------------------------

    def on_utterance_end(self, full_transcript: str) -> None:
        """Feed the latest full transcript; wakes the worker thread."""
        with self._lock:
            self._latest_transcript = full_transcript
        self._wake.set()

    def dismiss_topic(self, topic_key: str) -> None:
        self.policy.dismiss_topic(topic_key)

    # ------------------------------------------------------------------
    # Worker
    # ------------------------------------------------------------------

    def _run(self) -> None:
        while not self._stop_event.is_set():
            self._wake.wait(timeout=1.0)
            if self._stop_event.is_set():
                return
            self._wake.clear()
            try:
                self._maybe_tick()
            except Exception as e:  # noqa: BLE001 — the watcher must never die
                logger.warning("Watcher tick failed: {}", e)
                self._emit_status("watching")

    def _maybe_tick(self) -> None:
        """Run one LLM tick if the code-enforced gates allow it."""
        with self._lock:
            transcript = self._latest_transcript

        new_text = transcript[self._consumed_chars :]
        new_words = len(new_text.split())
        if not self.policy.should_tick(new_words):
            return

        self.policy.note_tick()
        self._transcript_blocks.append(new_text)
        self._consumed_chars = len(transcript)

        recent = list(self.policy.recent_topics)
        recent_text = (
            "\n".join(f"- {trigger}: {topic_key}" for trigger, topic_key in recent)
            if recent
            else "(none yet)"
        )
        instruction = WATCHER_TICK_INSTRUCTION.format(recent_topics=recent_text)

        from api.client import build_system_blocks, build_transcript_messages

        system = build_system_blocks(self._system_text, self._context_pack_text)
        messages = build_transcript_messages(self._transcript_blocks, instruction)

        self._emit_status("thinking")
        try:
            cards = self._api_client.create_cards(
                lane="watcher",
                model=self._model,
                max_tokens=self._max_tokens,
                system=system,
                messages=messages,
            )
        finally:
            self._emit_status("watching")

        # The meeting may have ended while the LLM call was in flight — a late
        # tick must never emit a card into the post-meeting UI.
        if self._stop_event.is_set():
            logger.info("Watcher tick finished after stop — result discarded")
            return

        # Multi-surface: at most ONE interrupt + ONE rail per tick, plus any
        # number of disposition="log" items (which bypass gating entirely and
        # never count against the interrupt/rail budget).
        interrupt_emitted = False
        rail_emitted = False
        for card in cards:
            if card.disposition == "log":
                self._log_disposition_card(card)
                continue

            is_rail = card.urgency == "fyi"
            if is_rail and rail_emitted:
                continue
            if not is_rail and interrupt_emitted:
                continue

            allowed, reason = self.policy.filter_card(card)
            self._log_suppression(card, reason=reason, allowed=allowed)
            if not allowed:
                continue

            self.policy.note_rendered(card)
            self._emit_card(card)
            if is_rail:
                rail_emitted = True
            else:
                interrupt_emitted = True

    # ------------------------------------------------------------------
    # Structured gate logging
    # ------------------------------------------------------------------

    def _log_suppression(self, card: Card, *, reason: str, allowed: bool) -> None:
        """Structured emit for every filter_card decision — allowed AND killed.

        Feeds the watcher_gate.jsonl sink used for the periodic review of
        gate behaviour; bound with watcher_gate=True so it can be filtered out
        of normal application logs.
        """
        logger.bind(watcher_gate=True).info(
            "Watcher card gated",
            allowed=allowed,
            reason=reason,
            trigger=card.trigger,
            card_type=card.type,
            topic_key=card.topic_key,
            urgency=card.urgency,
            confidence=card.confidence,
            source=card.source,
            disposition=card.disposition,
        )

    # ------------------------------------------------------------------
    # Callback plumbing (per-callback try/except — a bad consumer never kills us)
    # ------------------------------------------------------------------

    def _emit_card(self, card: Card) -> None:
        if self._on_card is None or self._stop_event.is_set():
            return
        try:
            self._on_card(card)
        except Exception as e:  # noqa: BLE001
            logger.warning("Watcher on_card callback failed: {}", e)

    def _emit_log_item(self, card: Card) -> None:
        if self._on_log_item is None or self._stop_event.is_set():
            return
        try:
            self._on_log_item(card)
        except Exception as e:  # noqa: BLE001
            logger.warning("Watcher on_log_item callback failed: {}", e)

    def _log_disposition_card(self, card: Card) -> None:
        """Route a disposition="log" card straight to on_log_item.

        Bypasses filter_card/note_rendered/render_cap entirely — a log item is
        a silent post-meeting artifact, never a live interrupt or rail, and
        must never consume any gating budget.
        """
        self._emit_log_item(card)

    def _emit_status(self, state: str, *, force: bool = False) -> None:
        """Emit a watcher_status update; suppressed once stop() has begun.

        ``force=True`` bypasses the suppression for the final "stopped" emit.
        """
        if self._on_status is None or (self._stop_event.is_set() and not force):
            return
        try:
            self._on_status(state)
        except Exception as e:  # noqa: BLE001
            logger.warning("Watcher on_status callback failed: {}", e)
