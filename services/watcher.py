"""Proactive watcher lane — utterance-end ticks with code-enforced debounce.

The watcher runs in its OWN thread, completely outside the interactive lane.
It is started on meeting start and stopped on meeting end. On each Deepgram
UtteranceEnd event the controller calls :meth:`Watcher.on_utterance_end`; the
worker thread then decides whether to run ONE Haiku tick over the
incrementally-cached transcript.

All throttling is CODE, not prompt:
- min 12 s between LLM ticks AND >= 30 new words accumulated;
- global render cap: at most 1 card per 15 s;
- per-type cooldown: 60 s;
- topic dedupe (topic_key): 5 min;
- user-dismissed topic_keys suppressed for the whole meeting;
- the last 5 shown card headlines are passed into each tick prompt.

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


@dataclass
class WatcherRules:
    """Tunable debounce/dedupe/cooldown thresholds (seconds / words)."""

    min_tick_seconds: float = 12.0
    min_new_words: int = 30
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
        self.recent_headlines: deque[str] = deque(maxlen=5)

    # ---- tick gating ----

    def should_tick(self, new_word_count: int) -> bool:
        """min 12 s since the last LLM tick AND >= 30 new words accumulated."""
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
        """Return (allowed, reason). Reason is "" when allowed."""
        now = self._clock()

        if card.topic_key in self._dismissed_topics:
            return False, "dismissed_topic"

        if (
            self._last_render_at is not None
            and now - self._last_render_at < self.rules.render_cap_seconds
        ):
            return False, "render_cap"

        last_type = self._last_type_at.get(card.type)
        if last_type is not None and now - last_type < self.rules.type_cooldown_seconds:
            return False, "type_cooldown"

        last_topic = self._last_topic_at.get(card.topic_key)
        if last_topic is not None and now - last_topic < self.rules.topic_dedupe_seconds:
            return False, "topic_dedupe"

        return True, ""

    def note_rendered(self, card: Card) -> None:
        now = self._clock()
        self._last_render_at = now
        self._last_type_at[card.type] = now
        self._last_topic_at[card.topic_key] = now
        self.recent_headlines.append(card.headline)

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

        headlines = list(self.policy.recent_headlines)
        headlines_text = "\n".join(f"- {h}" for h in headlines) if headlines else "(none yet)"
        instruction = WATCHER_TICK_INSTRUCTION.format(recent_headlines=headlines_text)

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

        # The watcher returns {} or exactly ONE card — enforce in code too.
        for card in cards[:1]:
            allowed, reason = self.policy.filter_card(card)
            if not allowed:
                logger.info(
                    "Watcher card suppressed",
                    reason=reason,
                    card_type=card.type,
                    topic_key=card.topic_key,
                )
                continue
            self.policy.note_rendered(card)
            self._emit_card(card)

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
