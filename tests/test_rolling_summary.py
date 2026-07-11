"""Tests for the rolling summary service (background lane). No network."""

from __future__ import annotations

from unittest.mock import Mock

import config
from services.rolling_summary import RollingSummaryService


def make_service(transcript_holder: dict, result: str = "summary v1"):
    api_client = Mock()
    api_client.process_with_anthropic.return_value = result
    updates: list[str] = []
    service = RollingSummaryService(
        api_client,
        get_transcript=lambda: transcript_holder["text"],
        on_update=updates.append,
    )
    return service, api_client, updates


class TestUpdateNow:
    def test_no_call_when_transcript_empty(self) -> None:
        service, api_client, _ = make_service({"text": ""})
        assert service.update_now() == ""
        api_client.process_with_anthropic.assert_not_called()

    def test_summary_updated_and_callback_fired(self) -> None:
        holder = {"text": "ME: hello\nTHEM: hi"}
        service, api_client, updates = make_service(holder)

        assert service.update_now() == "summary v1"
        assert service.summary == "summary v1"
        assert updates == ["summary v1"]

        kwargs = api_client.process_with_anthropic.call_args.kwargs
        assert kwargs["stream"] is False
        assert kwargs["model"] == config.WATCHER_MODEL
        assert kwargs["lane"] == "background"

    def test_only_new_transcript_sent_on_next_update(self) -> None:
        holder = {"text": "part one. "}
        service, api_client, _ = make_service(holder)
        service.update_now()

        holder["text"] = "part one. part two."
        api_client.process_with_anthropic.return_value = "summary v2"
        service.update_now()

        args = api_client.process_with_anthropic.call_args.args
        assert args[0] == "part two."  # only the tail since last update
        assert service.summary == "summary v2"

    def test_previous_summary_included_in_prompt(self) -> None:
        holder = {"text": "part one. "}
        service, api_client, _ = make_service(holder, result="first summary")
        service.update_now()

        holder["text"] = "part one. part two."
        service.update_now()

        template = api_client.process_with_anthropic.call_args.args[1]
        assert "first summary" in template

    def test_no_change_no_call(self) -> None:
        holder = {"text": "same text"}
        service, api_client, _ = make_service(holder)
        service.update_now()
        service.update_now()  # transcript unchanged — no second LLM call
        assert api_client.process_with_anthropic.call_count == 1


class TestLifecycle:
    def test_start_stop_thread(self) -> None:
        service, _, _ = make_service({"text": ""})
        service.start()
        assert service.is_running
        service.stop()
        assert not service.is_running

    def test_update_finishing_after_stop_is_discarded(self) -> None:
        """An LLM call in flight when stop() fires must not mutate the summary
        or invoke on_update after the meeting has ended."""
        holder = {"text": "ME: hello there everyone"}
        service, api_client, updates = make_service(holder, result="late summary")

        def slow_call(*args, **kwargs):
            service._stop_event.set()  # stop() fires mid-call
            return "late summary"

        api_client.process_with_anthropic.side_effect = slow_call

        assert service.update_now() == ""
        assert service.summary == ""
        assert updates == []

    def test_transcript_block_not_cache_written(self) -> None:
        """Each transcript tail is sent exactly once — no cache write premium."""
        service, api_client, _ = make_service({"text": "some words here"})
        service.update_now()
        kwargs = api_client.process_with_anthropic.call_args.kwargs
        assert kwargs["cache_transcript"] is False
