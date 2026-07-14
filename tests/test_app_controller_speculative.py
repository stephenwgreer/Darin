"""Tests for the Tier-1 speculative question detector wiring (Commit 4b).

The pure policy module (services/speculative_question.py) is tested on its
own; these tests cover the app_controller.py glue: firing run_reactive_prompt
with the right overrides, the supersede queue/drain cycle, the FINDING-5
auto-answer mutual exclusion, and that a detector exception never propagates
out of the ASR callback.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from app_controller import AppController
from services.cards import Card


@pytest.fixture
def controller() -> AppController:
    """An AppController with mocked backend deps, parked in 'active' state
    so the speculative gates (meeting_active) are satisfied without going
    through the full async start_meeting() lifecycle."""
    with (
        patch("app_controller.ContinuousRecorder"),
        patch("app_controller.ApiClient"),
    ):
        ctrl = AppController()
        ctrl._meeting_state = "active"
        yield ctrl


def _mock_run_reactive_prompt(controller: AppController, *, accepted: bool = True) -> MagicMock:
    """Patch run_reactive_prompt to record calls without spawning threads.

    Mirrors the real accept/reject contract: on_complete is only ever invoked
    by _run_reactive_thread's finally block, which only runs when a thread was
    actually spawned — i.e. only when the call was ACCEPTED. A rejected call
    (interactive lane busy) returns False and never touches on_complete, same
    as the real run_reactive_prompt/_try_acquire_interactive contract.
    """
    mock = MagicMock(return_value=accepted)

    def _fake(*args, **kwargs):
        on_complete = kwargs.get("on_complete")
        if accepted and on_complete is not None:
            on_complete()
        return accepted

    mock.side_effect = _fake
    controller.run_reactive_prompt = mock
    return mock


class TestInterimFire:
    def test_interim_fire_calls_run_reactive_prompt_with_trigger_and_transcript(
        self, controller: AppController
    ) -> None:
        mock = _mock_run_reactive_prompt(controller)
        controller._last_reactive_emitted = True

        controller._handle_interim_transcript(
            "Stephen, can you walk us through the pricing model", "THEM"
        )

        mock.assert_called_once()
        _, kwargs = mock.call_args
        assert kwargs["trigger_override"] == "speculative_answer"
        assert kwargs["transcript_override"] is not None
        assert "can you walk us through the pricing model" in kwargs["transcript_override"]

    def test_me_speaker_never_fires(self, controller: AppController) -> None:
        mock = _mock_run_reactive_prompt(controller)

        controller._handle_interim_transcript(
            "Stephen, can you walk us through the pricing model", "ME"
        )

        mock.assert_not_called()

    def test_meeting_not_active_never_fires(self, controller: AppController) -> None:
        controller._meeting_state = "idle"
        mock = _mock_run_reactive_prompt(controller)

        controller._handle_interim_transcript(
            "Stephen, can you walk us through the pricing model", "THEM"
        )

        mock.assert_not_called()

    def test_disabled_flag_never_fires(self, controller: AppController) -> None:
        controller.speculative_answer_enabled = False
        mock = _mock_run_reactive_prompt(controller)

        controller._handle_interim_transcript(
            "Stephen, can you walk us through the pricing model", "THEM"
        )

        mock.assert_not_called()

    def test_detector_exception_is_swallowed(self, controller: AppController) -> None:
        mock = _mock_run_reactive_prompt(controller)
        controller._speculative_policy.on_interim = MagicMock(
            side_effect=RuntimeError("boom")
        )

        # Must not raise.
        controller._handle_interim_transcript("can you help me", "THEM")

        mock.assert_not_called()


class TestSupersede:
    def test_rejected_fire_queues_pending_supersede_and_drain_refires(
        self, controller: AppController
    ) -> None:
        controller.current_transcript = "THEM: can you walk us through the pricing model"
        # First fire is rejected (lane busy) -> queues _pending_supersede.
        mock = _mock_run_reactive_prompt(controller, accepted=False)
        controller._fire_speculative("pricing model", source="interim")

        with controller._speculative_lock:
            assert controller._pending_supersede is not None
            qk, _snapshot = controller._pending_supersede
        assert qk == "pricing model"
        mock.assert_called_once()

        # Now the lane frees up: draining re-fires with the queued snapshot.
        mock2 = _mock_run_reactive_prompt(controller, accepted=True)
        controller._drain_pending_supersede()

        mock2.assert_called_once()
        _, kwargs = mock2.call_args
        assert kwargs["trigger_override"] == "speculative_answer"
        with controller._speculative_lock:
            assert controller._pending_supersede is None

    def test_speculative_release_drains_pending_supersede(
        self, controller: AppController
    ) -> None:
        """_speculative_release (the real on_complete) must trigger the drain,
        not just _drain_pending_supersede called directly."""
        with controller._speculative_lock:
            controller._pending_supersede = ("some question", "THEM: some question")
        controller._last_reactive_emitted = True
        mock = _mock_run_reactive_prompt(controller, accepted=True)

        controller._speculative_release("other-key")

        mock.assert_called_once()
        with controller._speculative_lock:
            assert controller._pending_supersede is None

    def test_drain_skips_if_meeting_not_active(self, controller: AppController) -> None:
        with controller._speculative_lock:
            controller._pending_supersede = ("q", "THEM: q")
        controller._meeting_state = "post_meeting"
        mock = _mock_run_reactive_prompt(controller)

        controller._drain_pending_supersede()

        mock.assert_not_called()
        # Pending slot is still cleared (consumed, not requeued).
        with controller._speculative_lock:
            assert controller._pending_supersede is None


class TestAutoAnswerSuppression:
    def _card(self, trigger: str = "question_at_user") -> Card:
        return Card(
            id="c1",
            lane="proactive",
            type="question",
            trigger=trigger,
            headline="Some totally unrelated watcher headline",
        )

    def test_auto_answer_suppressed_when_fired_within_window(
        self, controller: AppController
    ) -> None:
        """FINDING-5 regression: suppression is time-based, so it must fire
        even when the watcher card's headline shares no tokens with whatever
        question_key Tier-1 fired on."""
        controller._speculative_policy.note_fired("totally different tokens")
        controller.auto_answer_enabled = True

        with patch.object(controller, "run_reactive_prompt") as mock_run:
            controller._maybe_auto_answer(self._card())

        mock_run.assert_not_called()

    def test_auto_answer_proceeds_when_not_recently_fired(
        self, controller: AppController
    ) -> None:
        controller.auto_answer_enabled = True

        with patch.object(controller, "run_reactive_prompt", return_value=True) as mock_run:
            controller._maybe_auto_answer(self._card())

        mock_run.assert_called_once()


class TestEmptyContextAndAnsweredTracking:
    def test_empty_context_never_fires(self, controller: AppController) -> None:
        mock = _mock_run_reactive_prompt(controller)
        controller.current_transcript = ""
        controller._recent_lines.clear()
        controller._partial_question = None

        controller._fire_speculative("some key", source="interim")

        mock.assert_not_called()

    def test_last_reactive_emitted_false_skips_note_answered(
        self, controller: AppController
    ) -> None:
        """FINDING-6: if the reactive run produced no card (error/empty), the
        release path must not mark the question as answered — otherwise a
        legitimate follow-up on the same topic gets silently suppressed."""
        controller._last_reactive_emitted = False
        controller._speculative_policy.note_answered = MagicMock()

        controller._speculative_release("some key")

        controller._speculative_policy.note_answered.assert_not_called()

    def test_last_reactive_emitted_true_marks_answered(
        self, controller: AppController
    ) -> None:
        controller._last_reactive_emitted = True
        controller._speculative_policy.note_answered = MagicMock()

        controller._speculative_release("some key")

        controller._speculative_policy.note_answered.assert_called_once_with("some key")
