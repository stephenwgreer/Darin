"""Tests for per-lane concurrency in AppController.

The global _is_processing gate is gone. Interactive lane = one in-flight
request PER prompt_id: a second click of the SAME button is rejected, while
DIFFERENT buttons run concurrently. The watcher lane never touches the gate;
the background lane is unrestricted.
"""

from __future__ import annotations

import threading
import time
from unittest.mock import MagicMock, patch

import pytest

from app_controller import AppController
from prompts.registry import get_prompt_config_by_id
from services.cards import parse_card


def _wait_for(condition_fn, timeout: float = 3.0, poll: float = 0.02) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if condition_fn():
            return True
        time.sleep(poll)
    return False


@pytest.fixture
def controller():
    """AppController with mocked recorder and API client."""
    with (
        patch("app_controller.ContinuousRecorder"),
        patch("app_controller.ApiClient"),
    ):
        ctrl = AppController()
        ctrl.api_client = MagicMock()
        ctrl.api_client.create_cards.return_value = []
        # Give the reactive lane transcript context to work with
        ctrl.current_transcript = "ME: hello there\nTHEM: hi, quick question for you"
        yield ctrl


class TestInteractiveLane:
    def test_same_button_second_click_rejected(self, controller: AppController) -> None:
        gate = threading.Event()
        started = threading.Event()

        def blocking_create_cards(**kwargs):
            started.set()
            gate.wait(timeout=3.0)
            return []

        controller.api_client.create_cards.side_effect = blocking_create_cards
        cfg = get_prompt_config_by_id("answer_this")

        assert controller.run_reactive_prompt(cfg) is True
        assert started.wait(timeout=3.0)

        # Second click of the SAME button while in flight → rejected
        assert controller.run_reactive_prompt(cfg) is False

        gate.set()
        assert _wait_for(lambda: not controller.is_processing)
        assert controller.api_client.create_cards.call_count == 1

    def test_different_buttons_run_concurrently(self, controller: AppController) -> None:
        gate = threading.Event()
        in_flight: list[str] = []
        lock = threading.Lock()

        def blocking_create_cards(**kwargs):
            with lock:
                in_flight.append("call")
            gate.wait(timeout=3.0)
            return []

        controller.api_client.create_cards.side_effect = blocking_create_cards

        assert controller.run_reactive_prompt(get_prompt_config_by_id("answer_this")) is True
        assert controller.run_reactive_prompt(get_prompt_config_by_id("fact_check")) is True

        # Both LLM calls must be simultaneously in flight
        assert _wait_for(lambda: len(in_flight) == 2)
        assert controller.is_processing

        gate.set()
        assert _wait_for(lambda: not controller.is_processing)

    def test_same_button_allowed_again_after_completion(self, controller: AppController) -> None:
        cfg = get_prompt_config_by_id("answer_this")

        assert controller.run_reactive_prompt(cfg) is True
        assert _wait_for(lambda: not controller.is_processing)
        assert controller.run_reactive_prompt(cfg) is True
        assert _wait_for(lambda: not controller.is_processing)
        assert controller.api_client.create_cards.call_count == 2

    def test_is_processing_reflects_any_interactive_inflight(
        self, controller: AppController
    ) -> None:
        assert controller.is_processing is False
        controller._try_acquire_interactive("some_button")
        assert controller.is_processing is True
        controller._release_interactive("some_button")
        assert controller.is_processing is False

    def test_slot_released_even_on_llm_failure(self, controller: AppController) -> None:
        controller.api_client.create_cards.side_effect = RuntimeError("boom")
        errors: list[dict] = []
        done = threading.Event()

        def on_complete(result: dict) -> None:
            errors.append(result)
            done.set()

        controller._on_processing_complete = on_complete
        cfg = get_prompt_config_by_id("fact_check")

        assert controller.run_reactive_prompt(cfg) is True
        assert done.wait(timeout=3.0)
        assert any("error" in e for e in errors)
        assert _wait_for(lambda: not controller.is_processing)

    def test_reactive_and_longform_run_concurrently(self, controller: AppController) -> None:
        """The card lane and the (single-flight) long-form lane don't block each other."""
        from app_controller import LONGFORM_LANE_KEY

        gate = threading.Event()

        def blocking_create_cards(**kwargs):
            gate.wait(timeout=3.0)
            return []

        controller.api_client.create_cards.side_effect = blocking_create_cards
        assert controller.run_reactive_prompt(get_prompt_config_by_id("answer_this")) is True

        # The long-form streaming slot is still free while a card runs
        assert controller._try_acquire_interactive(LONGFORM_LANE_KEY) is True
        controller._release_interactive(LONGFORM_LANE_KEY)

        gate.set()
        assert _wait_for(lambda: not controller.is_processing)


class TestReactiveContext:
    def test_reactive_context_is_summary_plus_recent_not_full_transcript(
        self, controller: AppController
    ) -> None:
        """Reactive context = [rolling summary] + [last ~3 min verbatim]."""
        now = time.monotonic()
        controller._recent_lines.append((now - 400, "THEM: ancient line"))
        controller._recent_lines.append((now - 10, "THEM: recent line"))

        summary_mock = MagicMock()
        summary_mock.summary = "the rolling summary"
        controller._rolling_summary = summary_mock

        cfg = get_prompt_config_by_id("answer_this")
        assert controller.run_reactive_prompt(cfg) is True
        assert _wait_for(lambda: not controller.is_processing)

        kwargs = controller.api_client.create_cards.call_args.kwargs
        assert kwargs["lane"] == "reactive"
        context_text = "".join(block["text"] for block in kwargs["messages"][0]["content"])
        assert "the rolling summary" in context_text
        assert "recent line" in context_text
        assert "ancient line" not in context_text

    def test_ask_routes_through_reactive_lane_with_question(
        self, controller: AppController
    ) -> None:
        controller.ask_question("What did they commit to?")
        assert _wait_for(lambda: not controller.is_processing)

        kwargs = controller.api_client.create_cards.call_args.kwargs
        instruction = kwargs["messages"][-1]["content"][0]["text"]
        assert "What did they commit to?" in instruction
        assert kwargs["max_tokens"] == 600

    def test_ask_with_historical_transcript_uses_override(self, controller: AppController) -> None:
        controller.ask_question("Q?", historical_transcript="THEM: archived meeting text")
        assert _wait_for(lambda: not controller.is_processing)

        kwargs = controller.api_client.create_cards.call_args.kwargs
        context_text = "".join(block["text"] for block in kwargs["messages"][0]["content"])
        assert "archived meeting text" in context_text

    def test_error_when_no_transcript_context(self, controller: AppController) -> None:
        controller.current_transcript = ""
        errors: list[dict] = []
        done = threading.Event()
        controller._on_processing_complete = lambda r: (errors.append(r), done.set())

        controller.run_reactive_prompt(get_prompt_config_by_id("answer_this"))
        assert done.wait(timeout=3.0)
        assert any("error" in e for e in errors)
        controller.api_client.create_cards.assert_not_called()


class TestCardEmission:
    def test_reactive_cards_emitted_via_on_card(self, controller: AppController) -> None:
        card = parse_card({"type": "answer", "headline": "hi"}, lane="reactive")
        controller.api_client.create_cards.return_value = [card]
        emitted: list[dict] = []
        controller.on_card = emitted.append

        controller.run_reactive_prompt(get_prompt_config_by_id("answer_this"))
        assert _wait_for(lambda: len(emitted) == 1)
        assert emitted[0]["headline"] == "hi"
        assert emitted[0]["id"] == card.id

    def test_dismiss_card_suppresses_topic_and_notifies(self, controller: AppController) -> None:
        card = parse_card(
            {"type": "answer", "headline": "hi", "topic_key": "topic-z"}, lane="reactive"
        )
        controller.api_client.create_cards.return_value = [card]
        controller.run_reactive_prompt(get_prompt_config_by_id("answer_this"))
        assert _wait_for(lambda: not controller.is_processing)

        watcher_mock = MagicMock()
        controller._watcher = watcher_mock
        dismissed: list[str] = []
        controller.on_card_dismissed = dismissed.append

        assert controller.dismiss_card(card.id) is True
        watcher_mock.dismiss_topic.assert_called_once_with("topic-z")
        assert dismissed == [card.id]

    def test_dismiss_unknown_card_returns_false(self, controller: AppController) -> None:
        assert controller.dismiss_card("card_nope") is False
