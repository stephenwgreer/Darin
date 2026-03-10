"""Regression tests for DAR2-39: transcript not injected into prompt template.

Root cause: _transcribe_and_process_thread had no guard against empty
transcription results. When Deepgram returned an empty string, the
prompt template still executed with {transcript}="" — causing Claude to
produce a generic textbook response instead of analysing actual speech.

Fix: guard added after transcription in _transcribe_and_process_thread,
matching the guard already present in _run_post_meeting_thread.
"""

from __future__ import annotations

import threading
import time
from unittest.mock import MagicMock, patch

import pytest

from app_controller import AppController
from prompts.logic_templates import HYPOTHESIS_DRIVEN_PROMPT
from prompts.registry import PROMPT_REGISTRY


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _wait_for(condition_fn: object, timeout: float = 2.0, poll: float = 0.05) -> bool:
    """Poll until condition_fn() is True or timeout expires."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if condition_fn():
            return True
        time.sleep(poll)
    return False


@pytest.fixture
def controller() -> AppController:
    """AppController with mocked recorder and API client."""
    with (
        patch("app_controller.ContinuousRecorder") as mock_recorder_cls,
        patch("app_controller.ApiClient") as mock_api_cls,
    ):
        mock_recorder = MagicMock()
        mock_recorder.sample_rate = 16000
        mock_recorder.is_recording = False
        mock_recorder.get_buffer_seconds.return_value = 60
        mock_recorder_cls.return_value = mock_recorder

        mock_api = MagicMock()
        mock_api_cls.return_value = mock_api

        ctrl = AppController()
        ctrl._mock_recorder = mock_recorder
        ctrl._mock_api = mock_api
        yield ctrl


# ---------------------------------------------------------------------------
# DAR2-39: Transcript injection guard
# ---------------------------------------------------------------------------


class TestTranscriptInjectionGuard:
    """When transcription returns empty, prompt must NOT execute."""

    def test_empty_transcription_triggers_error_callback_not_prompt(
        self, controller: AppController
    ) -> None:
        """_run_prompt_thread must NOT be called when transcription is empty."""
        # Arrange
        controller._mock_recorder.save_buffer.return_value = b"\x00" * 1024
        controller._mock_api.transcribe_with_deepgram.return_value = ""

        errors: list[dict] = []
        done = threading.Event()

        def on_complete(result: dict) -> None:
            errors.append(result)
            done.set()

        controller._on_processing_complete = on_complete

        # Act
        controller.run_prompt(HYPOTHESIS_DRIVEN_PROMPT)

        # Assert: error callback fired, NOT process_with_anthropic
        assert done.wait(timeout=2.0), "on_processing_complete was never called"
        assert any("error" in e for e in errors), f"Expected error result, got: {errors}"
        controller._mock_api.process_with_anthropic.assert_not_called()

    def test_whitespace_only_transcription_does_not_run_prompt(
        self, controller: AppController
    ) -> None:
        """Whitespace-only transcription result is treated the same as empty."""
        controller._mock_recorder.save_buffer.return_value = b"\x00" * 1024
        controller._mock_api.transcribe_with_deepgram.return_value = "   \n\t  "

        done = threading.Event()
        controller._on_processing_complete = lambda result: done.set()

        controller.run_prompt(HYPOTHESIS_DRIVEN_PROMPT)

        assert done.wait(timeout=2.0)
        controller._mock_api.process_with_anthropic.assert_not_called()

    def test_non_empty_transcription_injects_transcript_into_template(
        self, controller: AppController
    ) -> None:
        """When transcription succeeds, the actual transcript must appear in the prompt sent to Claude."""
        real_transcript = "The meeting discussed the Q3 revenue forecast."
        controller._mock_recorder.save_buffer.return_value = b"\x00" * 1024
        controller._mock_api.transcribe_with_deepgram.return_value = real_transcript
        controller._mock_api.process_with_anthropic.return_value = "<li>result</li>"

        done = threading.Event()
        controller._on_processing_complete = lambda result: done.set()

        controller.run_prompt(HYPOTHESIS_DRIVEN_PROMPT)

        assert done.wait(timeout=2.0), "Prompt never completed"
        controller._mock_api.process_with_anthropic.assert_called_once()

        # Verify the transcript was the first argument passed to process_with_anthropic
        call_args = controller._mock_api.process_with_anthropic.call_args
        passed_transcript = call_args.args[0]
        assert passed_transcript == real_transcript, (
            f"Expected transcript {real_transcript!r} as first arg, got {passed_transcript!r}"
        )

    def test_transcript_substituted_in_hypothesis_template(
        self, controller: AppController
    ) -> None:
        """The full substituted content sent to Claude must contain the transcript text."""
        real_transcript = "We hypothesize that cost reduction drives margin improvement."
        controller._mock_recorder.save_buffer.return_value = b"\x00" * 1024
        controller._mock_api.transcribe_with_deepgram.return_value = real_transcript

        captured_content: list[str] = []

        def mock_process(text: str, prompt_template: str | None = None, **kwargs: object) -> str:
            if prompt_template:
                content = prompt_template.format(transcript=text)
                captured_content.append(content)
            return "<li>ok</li>"

        controller._mock_api.process_with_anthropic.side_effect = mock_process

        done = threading.Event()
        controller._on_processing_complete = lambda result: done.set()

        controller.run_prompt(HYPOTHESIS_DRIVEN_PROMPT)

        assert done.wait(timeout=2.0)
        assert len(captured_content) == 1
        assert real_transcript in captured_content[0], (
            f"Transcript not found in content sent to Claude.\n"
            f"Transcript: {real_transcript!r}\n"
            f"Content sent: {captured_content[0][:200]!r}"
        )
        assert "{transcript}" not in captured_content[0], (
            "Literal '{transcript}' placeholder was not substituted — bug reproduced!"
        )


class TestAllTemplatesHaveTranscriptPlaceholder:
    """Guard: every prompt in the registry must have a {transcript} placeholder."""

    def test_all_registry_templates_have_transcript_placeholder(self) -> None:
        """Regression for DAR2-39: every template must inject the transcript."""
        missing = [
            cfg.id for cfg in PROMPT_REGISTRY if "{transcript}" not in cfg.template
        ]
        assert not missing, (
            f"These prompts are missing the {{transcript}} placeholder: {missing}"
        )

    def test_all_templates_can_format_with_transcript(self) -> None:
        """Verify no template raises KeyError when formatted with transcript=..."""
        sample_transcript = "Sample transcript content for testing."
        failures: list[tuple[str, str]] = []

        for cfg in PROMPT_REGISTRY:
            try:
                result = cfg.template.format(transcript=sample_transcript)
                if sample_transcript not in result:
                    failures.append((cfg.id, "transcript not present in formatted output"))
            except KeyError as e:
                failures.append((cfg.id, f"KeyError: {e}"))
            except Exception as e:
                failures.append((cfg.id, f"{type(e).__name__}: {e}"))

        assert not failures, (
            "Template formatting failures:\n"
            + "\n".join(f"  {pid}: {msg}" for pid, msg in failures)
        )
