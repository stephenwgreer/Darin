"""Rolling summary service — background lane.

Every ~5 minutes of meeting time, folds the NEW transcript since the previous
update into a ~300-token running summary using the watcher model. The summary
feeds the reactive lane's context ([rolling summary] + [last ~3 min verbatim])
and is persisted per-meeting by the controller via the meeting store.
"""

from __future__ import annotations

import threading
from collections.abc import Callable

from loguru import logger

import config
from prompts.templates import ROLLING_SUMMARY_PROMPT


class RollingSummaryService:
    """Periodic transcript summarizer running in its own daemon thread."""

    def __init__(
        self,
        api_client,  # noqa: ANN001 — ApiClient (duck-typed for tests)
        *,
        get_transcript: Callable[[], str],
        on_update: Callable[[str], None] | None = None,
        interval_seconds: float = config.ROLLING_SUMMARY_INTERVAL_S,
        model: str = config.WATCHER_MODEL,
        max_tokens: int = config.ROLLING_SUMMARY_MAX_TOKENS,
    ) -> None:
        self._api_client = api_client
        self._get_transcript = get_transcript
        self._on_update = on_update
        self._interval_seconds = interval_seconds
        self._model = model
        self._max_tokens = max_tokens

        self._summary = ""
        self._consumed_chars = 0
        self._lock = threading.Lock()
        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None

    @property
    def summary(self) -> str:
        """The current running summary ("" until the first update)."""
        with self._lock:
            return self._summary

    @property
    def is_running(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    def start(self) -> None:
        if self.is_running:
            logger.warning("Rolling summary already running")
            return
        self._stop_event.clear()
        self._thread = threading.Thread(target=self._run, name="rolling-summary", daemon=True)
        self._thread.start()
        logger.info("Rolling summary started", interval_seconds=self._interval_seconds)

    def stop(self) -> None:
        if self._thread is None:
            return
        self._stop_event.set()
        # An in-flight LLM call can outlive this join; update_now() checks
        # _stop_event after the call returns, so a late result is discarded
        # instead of firing on_update after the meeting ended.
        self._thread.join(timeout=2.0)
        self._thread = None
        logger.info("Rolling summary stopped")

    def _run(self) -> None:
        while not self._stop_event.wait(timeout=self._interval_seconds):
            try:
                self.update_now()
            except Exception as e:  # noqa: BLE001 — background lane must never die
                logger.warning("Rolling summary update failed: {}", e)

    def update_now(self) -> str:
        """Fold new transcript text into the running summary (synchronous)."""
        transcript = self._get_transcript() or ""
        new_text = transcript[self._consumed_chars :]
        if not new_text.strip():
            return self.summary

        with self._lock:
            previous = self._summary
        template = ROLLING_SUMMARY_PROMPT.replace("{previous_summary}", previous or "(none yet)")
        result = self._api_client.process_with_anthropic(
            new_text,
            template,
            stream=False,
            model=self._model,
            max_tokens=self._max_tokens,
            lane="background",
            cache_transcript=False,  # each tail is sent exactly once — never re-read
        )

        # stop() may have fired while the LLM call was in flight — discard the
        # late result rather than mutating state / persisting after meeting end.
        if self._stop_event.is_set():
            logger.info("Rolling summary update finished after stop — result discarded")
            return self.summary

        summary = (result or "").strip()
        if summary:
            with self._lock:
                self._summary = summary
            self._consumed_chars = len(transcript)
            logger.info("Rolling summary updated", summary_chars=len(summary))
            if self._on_update is not None:
                try:
                    self._on_update(summary)
                except Exception as e:  # noqa: BLE001
                    logger.warning("Rolling summary on_update callback failed: {}", e)
        return self.summary
