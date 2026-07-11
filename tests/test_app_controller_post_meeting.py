"""Tests for AppController post-meeting prompt execution (DAR2-27)."""

from __future__ import annotations

import threading
import time
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from app_controller import AppController
from prompts.registry import get_prompt_config_by_id
from storage.meeting_store import MeetingStore


@pytest.fixture
def store(tmp_path: Path) -> MeetingStore:
    return MeetingStore(base_dir=tmp_path / "meetings")


@pytest.fixture
def controller(store: MeetingStore) -> AppController:
    """AppController wired with a real MeetingStore and mocked API client."""
    ctrl = AppController()
    ctrl.meeting_store = store
    # Mock the API client so no real network calls happen
    ctrl.api_client = MagicMock()
    ctrl.api_client.process_with_anthropic.return_value = "<li>mocked result</li>"
    return ctrl


def _wait_for(condition_fn: object, timeout: float = 2.0, poll: float = 0.05) -> bool:
    """Poll until condition_fn() is True or timeout expires."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if condition_fn():
            return True
        time.sleep(poll)
    return False


class TestGetSavedAnalyses:
    """Test AppController.get_saved_analyses()."""

    def test_returns_empty_dict_when_no_meeting(self, controller: AppController) -> None:
        result = controller.get_saved_analyses()
        assert result == {}

    def test_returns_empty_dict_when_no_store(self) -> None:
        ctrl = AppController()
        ctrl._last_meeting_id = 1
        result = ctrl.get_saved_analyses()
        assert result == {}

    def test_returns_saved_analyses_for_last_meeting(
        self, controller: AppController, store: MeetingStore
    ) -> None:
        meeting_id = store.start_meeting()
        store.save_analysis(meeting_id, "meeting_summary", "summary text")
        controller._last_meeting_id = meeting_id

        result = controller.get_saved_analyses()
        assert result == {"meeting_summary": "summary text"}

    def test_prefers_last_meeting_id_over_active(
        self, controller: AppController, store: MeetingStore
    ) -> None:
        active_id = store.start_meeting()
        last_id = store.start_meeting()
        store.save_analysis(last_id, "key_decisions", "last meeting decisions")
        controller._active_meeting_id = active_id
        controller._last_meeting_id = last_id

        result = controller.get_saved_analyses()
        assert "key_decisions" in result


class TestRunPostMeetingPrompt:
    """Test AppController.run_post_meeting_prompt()."""

    def test_rejects_second_longform_while_one_streams(self, controller: AppController) -> None:
        """Long-form streaming is single-flight: the SSE stream pipeline is one
        shared slot, so ANY second long-form prompt is rejected while one runs."""
        from app_controller import LONGFORM_LANE_KEY

        assert controller._try_acquire_interactive(LONGFORM_LANE_KEY)
        completed = []
        # Same prompt AND a different long-form prompt are both rejected
        for prompt_id in ("meeting_summary", "action_items"):
            accepted = controller.run_post_meeting_prompt(
                get_prompt_config_by_id(prompt_id),
                on_complete=lambda pid, txt: completed.append(pid),
            )
            assert accepted is False
        time.sleep(0.1)
        assert completed == []
        controller._release_interactive(LONGFORM_LANE_KEY)

    def test_accepted_longform_returns_true(
        self, controller: AppController, store: MeetingStore
    ) -> None:
        meeting_id = store.start_meeting()
        store.append_segment(meeting_id, "Hello world content.")
        store.end_meeting(meeting_id)
        controller._last_meeting_id = meeting_id

        done = threading.Event()
        accepted = controller.run_post_meeting_prompt(
            get_prompt_config_by_id("meeting_summary"),
            on_complete=lambda pid, txt: done.set(),
        )
        assert accepted is True
        assert done.wait(timeout=2.0)

    def test_invokes_on_complete_with_prompt_id(
        self, controller: AppController, store: MeetingStore
    ) -> None:
        meeting_id = store.start_meeting()
        store.append_segment(meeting_id, "Hello world, this is a test meeting.")
        store.end_meeting(meeting_id)
        controller._last_meeting_id = meeting_id

        completed: list[tuple[str, str]] = []

        def on_complete(pid: str, txt: str) -> None:
            completed.append((pid, txt))

        prompt_config = get_prompt_config_by_id("meeting_summary")
        controller.run_post_meeting_prompt(prompt_config, on_complete=on_complete)

        assert _wait_for(lambda: len(completed) > 0), "on_complete was never called"
        assert completed[0][0] == "meeting_summary"

    def test_saves_result_to_meeting_store(
        self, controller: AppController, store: MeetingStore
    ) -> None:
        meeting_id = store.start_meeting()
        store.append_segment(meeting_id, "Test transcript content.")
        store.end_meeting(meeting_id)
        controller._last_meeting_id = meeting_id

        done = threading.Event()
        controller.run_post_meeting_prompt(
            get_prompt_config_by_id("action_items"),
            on_complete=lambda pid, txt: done.set(),
        )

        assert done.wait(timeout=2.0), "Post-meeting prompt did not complete"
        saved = store.get_analysis(meeting_id, "action_items")
        assert saved is not None

    def test_retrieves_full_transcript_when_no_range(
        self, controller: AppController, store: MeetingStore
    ) -> None:
        meeting_id = store.start_meeting()
        store.append_segment(meeting_id, "Full transcript content here.")
        store.end_meeting(meeting_id)
        controller._last_meeting_id = meeting_id

        done = threading.Event()
        controller.run_post_meeting_prompt(
            get_prompt_config_by_id("meeting_summary"),
            on_complete=lambda pid, txt: done.set(),
        )

        assert done.wait(timeout=2.0)
        # Verify process_with_anthropic was called with the full transcript
        call_args = controller.api_client.process_with_anthropic.call_args
        assert "Full transcript content here." in call_args[0][0]

    def test_retrieves_segment_range_when_specified(
        self, controller: AppController, store: MeetingStore
    ) -> None:
        """When from_minute/to_minute are provided, store.get_transcript_segment_range is used."""
        meeting_id = store.start_meeting()
        controller._last_meeting_id = meeting_id

        # Mock the store's segment range method
        controller._meeting_store.get_transcript_segment_range = MagicMock(
            return_value="segment text"
        )

        done = threading.Event()
        controller.run_post_meeting_prompt(
            get_prompt_config_by_id("key_decisions"),
            from_minute=5,
            to_minute=15,
            on_complete=lambda pid, txt: done.set(),
        )

        assert done.wait(timeout=2.0)
        controller._meeting_store.get_transcript_segment_range.assert_called_once_with(
            meeting_id, 5, 15
        )

    def test_no_op_when_no_meeting_available(self, controller: AppController) -> None:
        """When no meeting ID is set, prompt completes with error."""
        errors: list[dict] = []
        controller._on_processing_complete = lambda result: errors.append(result)

        done = threading.Event()

        def on_complete_or_error(result: dict) -> None:
            errors.append(result)
            done.set()

        controller._on_processing_complete = on_complete_or_error

        controller.run_post_meeting_prompt(get_prompt_config_by_id("meeting_summary"))

        assert done.wait(timeout=2.0)
        assert any("error" in e for e in errors)

    def test_resets_is_processing_after_completion(
        self, controller: AppController, store: MeetingStore
    ) -> None:
        meeting_id = store.start_meeting()
        store.append_segment(meeting_id, "Some content.")
        store.end_meeting(meeting_id)
        controller._last_meeting_id = meeting_id

        done = threading.Event()
        controller.run_post_meeting_prompt(
            get_prompt_config_by_id("meeting_summary"),
            on_complete=lambda pid, txt: done.set(),
        )

        assert done.wait(timeout=2.0)
        assert not controller.is_processing


class TestPromptRegistryIntegrity:
    """Guard against registry regressions (two-lane card copilot)."""

    def test_all_registry_prompts_have_bucket(self) -> None:
        from prompts.registry import PROMPT_REGISTRY

        for cfg in PROMPT_REGISTRY:
            assert cfg.bucket in (
                "reactive",
                "post_meeting",
            ), f"Prompt {cfg.id!r} has unexpected bucket {cfg.bucket!r}"

    def test_get_prompts_by_bucket_reactive_count(self) -> None:
        """Exactly 5 reactive buttons (Ask is separate, not a button)."""
        from prompts.registry import get_prompts_by_bucket

        prompts = get_prompts_by_bucket("reactive")
        assert [p.id for p in prompts] == [
            "answer_this",
            "fact_check",
            "reframe",
            "where_are_we",
            "next_step",
        ]

    def test_get_prompts_by_bucket_post_meeting_count(self) -> None:
        from prompts.registry import get_prompts_by_bucket

        prompts = get_prompts_by_bucket("post_meeting")
        assert [p.id for p in prompts] == ["meeting_summary", "action_items", "key_decisions"]

    def test_killed_prompts_are_gone(self) -> None:
        """The 21-button estate is gone — killed ids must not resolve."""
        for prompt_id in (
            "scqa",
            "issue_tree",
            "first_principles",
            "hypothesis_driven",
            "buying_signals",
            "objection_handling",
            "deal_risk",
            "sentiment_analysis",
            "practitioner_insights",
            "follow_up_questions",
            "company_fit",
            "topic_summary",
            "analyze_statement",
            "gaps_reasoning",
            "brainstorming",
        ):
            assert get_prompt_config_by_id(prompt_id) is None, (
                f"Killed prompt {prompt_id!r} is still in the registry"
            )

    def test_all_templates_are_real_strings(self) -> None:
        """Guard: no registry template should be a bare 1-2 word string."""
        from prompts.registry import PROMPT_REGISTRY

        for cfg in PROMPT_REGISTRY:
            assert len(cfg.template) > 50, (
                f"Prompt {cfg.id!r} has suspiciously short template "
                f"({len(cfg.template)} chars) — likely a bare ID string, not a real template"
            )

    def test_post_meeting_prompts_have_transcript_placeholder(self) -> None:
        for prompt_id in ("meeting_summary", "action_items", "key_decisions"):
            cfg = get_prompt_config_by_id(prompt_id)
            assert cfg is not None, f"Prompt {prompt_id!r} not found in registry"
            assert "{transcript}" in cfg.template, (
                f"Prompt {prompt_id!r} template is missing {{transcript}} placeholder"
            )

    def test_total_prompt_count(self) -> None:
        from prompts.registry import PROMPT_REGISTRY

        assert len(PROMPT_REGISTRY) == 8, (
            f"Expected 8 total prompts (5 reactive + 3 post-meeting), got {len(PROMPT_REGISTRY)}"
        )
