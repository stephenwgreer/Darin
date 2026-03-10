"""Tests for PromptButtons component — three-bucket layout (DAR2-27)."""

from __future__ import annotations

import asyncio
from unittest.mock import MagicMock, patch


class TestPromptButtonsState:
    """Test prompt card visibility by meeting state."""

    def test_mid_meeting_visible_when_active(self) -> None:
        with patch("ui.components.prompt_buttons.ui"):
            from ui.components.prompt_buttons import PromptButtons

            pb = PromptButtons(MagicMock())
            pb._mid_meeting_card = MagicMock()
            pb._reasoning_card = MagicMock()
            pb._post_meeting_card = MagicMock()

            pb.set_state("active")

            pb._mid_meeting_card.set_visibility.assert_called_with(True)
            pb._reasoning_card.set_visibility.assert_called_with(True)
            pb._post_meeting_card.set_visibility.assert_called_with(False)

    def test_reasoning_card_visible_when_active(self) -> None:
        with patch("ui.components.prompt_buttons.ui"):
            from ui.components.prompt_buttons import PromptButtons

            pb = PromptButtons(MagicMock())
            pb._mid_meeting_card = MagicMock()
            pb._reasoning_card = MagicMock()
            pb._post_meeting_card = MagicMock()

            pb.set_state("active")

            pb._reasoning_card.set_visibility.assert_called_with(True)

    def test_mid_meeting_hidden_when_idle(self) -> None:
        with patch("ui.components.prompt_buttons.ui"):
            from ui.components.prompt_buttons import PromptButtons

            pb = PromptButtons(MagicMock())
            pb._mid_meeting_card = MagicMock()
            pb._reasoning_card = MagicMock()
            pb._post_meeting_card = MagicMock()

            pb.set_state("idle")

            pb._mid_meeting_card.set_visibility.assert_called_with(False)
            pb._reasoning_card.set_visibility.assert_called_with(False)
            pb._post_meeting_card.set_visibility.assert_called_with(False)

    def test_post_meeting_visible_when_post(self) -> None:
        with patch("ui.components.prompt_buttons.ui"):
            from ui.components.prompt_buttons import PromptButtons

            pb = PromptButtons(MagicMock())
            pb._mid_meeting_card = MagicMock()
            pb._reasoning_card = MagicMock()
            pb._post_meeting_card = MagicMock()

            pb.set_state("post_meeting")

            pb._mid_meeting_card.set_visibility.assert_called_with(False)
            pb._reasoning_card.set_visibility.assert_called_with(False)
            pb._post_meeting_card.set_visibility.assert_called_with(True)

    def test_mid_meeting_hidden_when_post(self) -> None:
        with patch("ui.components.prompt_buttons.ui"):
            from ui.components.prompt_buttons import PromptButtons

            pb = PromptButtons(MagicMock())
            pb._mid_meeting_card = MagicMock()
            pb._reasoning_card = MagicMock()
            pb._post_meeting_card = MagicMock()

            pb.set_state("post_meeting")

            pb._mid_meeting_card.set_visibility.assert_called_with(False)
            pb._reasoning_card.set_visibility.assert_called_with(False)

    def test_set_state_refreshes_saved_state_on_post_meeting(self) -> None:
        with patch("ui.components.prompt_buttons.ui"):
            from ui.components.prompt_buttons import PromptButtons

            controller = MagicMock()
            controller.get_saved_analyses.return_value = {}

            pb = PromptButtons(controller)
            pb._mid_meeting_card = MagicMock()
            pb._reasoning_card = MagicMock()
            pb._post_meeting_card = MagicMock()

            pb.set_state("post_meeting")

            controller.get_saved_analyses.assert_called_once()

    def test_set_state_does_not_refresh_on_active(self) -> None:
        with patch("ui.components.prompt_buttons.ui"):
            from ui.components.prompt_buttons import PromptButtons

            controller = MagicMock()

            pb = PromptButtons(controller)
            pb._mid_meeting_card = MagicMock()
            pb._reasoning_card = MagicMock()
            pb._post_meeting_card = MagicMock()

            pb.set_state("active")

            controller.get_saved_analyses.assert_not_called()


class TestPromptProcessingGuard:
    """Test that buttons are disabled during prompt execution."""

    def test_set_buttons_enabled_disables_all(self) -> None:
        with patch("ui.components.prompt_buttons.ui"):
            from ui.components.prompt_buttons import PromptButtons

            pb = PromptButtons(MagicMock())
            mock_btn1 = MagicMock()
            mock_btn2 = MagicMock()
            pb._prompt_buttons = [mock_btn1, mock_btn2]

            pb._set_buttons_enabled(False)

            mock_btn1.set_enabled.assert_called_with(False)
            mock_btn2.set_enabled.assert_called_with(False)

    def test_set_buttons_enabled_enables_all(self) -> None:
        with patch("ui.components.prompt_buttons.ui"):
            from ui.components.prompt_buttons import PromptButtons

            pb = PromptButtons(MagicMock())
            mock_btn1 = MagicMock()
            mock_btn2 = MagicMock()
            pb._prompt_buttons = [mock_btn1, mock_btn2]

            pb._set_buttons_enabled(True)

            mock_btn1.set_enabled.assert_called_with(True)
            mock_btn2.set_enabled.assert_called_with(True)


class TestRegistryDrivenButtons:
    """Verify buttons are driven from the registry, not hardcoded strings."""

    def test_mid_meeting_uses_registry_templates(self) -> None:
        """Mid-meeting buttons must use real PromptConfig templates, not bare strings."""
        from prompts.registry import get_prompts_by_bucket

        for cfg in get_prompts_by_bucket("mid_meeting"):
            assert len(cfg.template) > 50, (
                f"mid_meeting prompt {cfg.id!r} has suspiciously short template"
            )

    def test_reasoning_uses_registry_templates(self) -> None:
        from prompts.registry import get_prompts_by_bucket

        for cfg in get_prompts_by_bucket("reasoning"):
            assert len(cfg.template) > 50, (
                f"reasoning prompt {cfg.id!r} has suspiciously short template"
            )

    def test_post_meeting_uses_registry_templates(self) -> None:
        from prompts.registry import get_prompts_by_bucket

        for cfg in get_prompts_by_bucket("post_meeting"):
            assert len(cfg.template) > 50, (
                f"post_meeting prompt {cfg.id!r} has suspiciously short template"
            )

    def test_nine_mid_meeting_prompts(self) -> None:
        from prompts.registry import get_prompts_by_bucket

        assert len(get_prompts_by_bucket("mid_meeting")) == 9

    def test_five_reasoning_prompts(self) -> None:
        from prompts.registry import get_prompts_by_bucket

        assert len(get_prompts_by_bucket("reasoning")) == 5

    def test_four_post_meeting_prompts(self) -> None:
        from prompts.registry import get_prompts_by_bucket

        assert len(get_prompts_by_bucket("post_meeting")) == 4


class TestBadgeManagement:
    """Test checkmark badge show/hide for saved post-meeting analyses."""

    def test_mark_as_run_shows_badge(self) -> None:
        with patch("ui.components.prompt_buttons.ui"):
            from ui.components.prompt_buttons import PromptButtons

            pb = PromptButtons(MagicMock())
            mock_badge = MagicMock()
            pb._post_meeting_badges = {"meeting_summary": mock_badge}

            pb._mark_as_run("meeting_summary")

            mock_badge.set_visibility.assert_called_with(True)

    def test_mark_as_run_unknown_prompt_is_noop(self) -> None:
        with patch("ui.components.prompt_buttons.ui"):
            from ui.components.prompt_buttons import PromptButtons

            pb = PromptButtons(MagicMock())
            pb._post_meeting_badges = {}

            pb._mark_as_run("nonexistent_prompt")  # should not raise

    def test_refresh_saved_state_shows_saved_badges(self) -> None:
        with patch("ui.components.prompt_buttons.ui"):
            from ui.components.prompt_buttons import PromptButtons

            controller = MagicMock()
            controller.get_saved_analyses.return_value = {"meeting_summary": "some text"}

            pb = PromptButtons(controller)
            mock_badge = MagicMock()
            pb._post_meeting_badges = {"meeting_summary": mock_badge, "action_items": MagicMock()}

            pb._refresh_saved_state()

            mock_badge.set_visibility.assert_called_with(True)

    def test_refresh_saved_state_hides_unsaved_badges(self) -> None:
        with patch("ui.components.prompt_buttons.ui"):
            from ui.components.prompt_buttons import PromptButtons

            controller = MagicMock()
            controller.get_saved_analyses.return_value = {}

            pb = PromptButtons(controller)
            mock_badge = MagicMock()
            pb._post_meeting_badges = {"meeting_summary": mock_badge}

            pb._refresh_saved_state()

            mock_badge.set_visibility.assert_called_with(False)


class TestRunMidMeeting:
    """Test _run_mid_meeting calls controller.run_prompt with template."""

    def test_run_mid_meeting_calls_run_prompt(self) -> None:
        with patch("ui.components.prompt_buttons.ui"):
            from ui.components.prompt_buttons import PromptButtons

            controller = MagicMock()
            pb = PromptButtons(controller)

            from prompts.registry import get_prompt_config_by_id
            cfg = get_prompt_config_by_id("sentiment_analysis")

            asyncio.get_event_loop().run_until_complete(pb._run_mid_meeting(cfg))

            controller.run_prompt.assert_called_once()
            call_args = controller.run_prompt.call_args
            assert call_args.args[0] == cfg.template

    def test_run_mid_meeting_passes_on_template_setup_when_output_panel_set(self) -> None:
        with patch("ui.components.prompt_buttons.ui"):
            from ui.components.prompt_buttons import PromptButtons

            controller = MagicMock()
            output_panel = MagicMock()
            pb = PromptButtons(controller, output_panel=output_panel)

            from prompts.registry import get_prompt_config_by_id
            cfg = get_prompt_config_by_id("sentiment_analysis")

            asyncio.get_event_loop().run_until_complete(pb._run_mid_meeting(cfg))

            call_kwargs = controller.run_prompt.call_args.kwargs
            assert call_kwargs.get("on_template_setup") is not None


class TestRunPostMeeting:
    """Test _run_post_meeting calls controller.run_post_meeting_prompt."""

    def test_run_post_meeting_calls_controller(self) -> None:
        with patch("ui.components.prompt_buttons.ui"):
            from ui.components.prompt_buttons import PromptButtons

            controller = MagicMock()
            pb = PromptButtons(controller)
            pb._segment_mode = MagicMock()
            pb._segment_mode.value = "Full transcript"

            from prompts.registry import get_prompt_config_by_id
            cfg = get_prompt_config_by_id("meeting_summary")

            asyncio.get_event_loop().run_until_complete(pb._run_post_meeting(cfg))

            controller.run_post_meeting_prompt.assert_called_once()

    def test_run_post_meeting_passes_range_when_time_range_selected(self) -> None:
        with patch("ui.components.prompt_buttons.ui"):
            from ui.components.prompt_buttons import PromptButtons

            controller = MagicMock()
            pb = PromptButtons(controller)
            pb._segment_mode = MagicMock()
            pb._segment_mode.value = "Time range"
            pb._from_minute = MagicMock()
            pb._from_minute.value = 5
            pb._to_minute = MagicMock()
            pb._to_minute.value = 15

            from prompts.registry import get_prompt_config_by_id
            cfg = get_prompt_config_by_id("action_items")

            asyncio.get_event_loop().run_until_complete(pb._run_post_meeting(cfg))

            call_kwargs = controller.run_post_meeting_prompt.call_args.kwargs
            assert call_kwargs["from_minute"] == 5
            assert call_kwargs["to_minute"] == 15

    def test_run_post_meeting_no_range_when_full_transcript_selected(self) -> None:
        with patch("ui.components.prompt_buttons.ui"):
            from ui.components.prompt_buttons import PromptButtons

            controller = MagicMock()
            pb = PromptButtons(controller)
            pb._segment_mode = MagicMock()
            pb._segment_mode.value = "Full transcript"

            from prompts.registry import get_prompt_config_by_id
            cfg = get_prompt_config_by_id("key_decisions")

            asyncio.get_event_loop().run_until_complete(pb._run_post_meeting(cfg))

            call_kwargs = controller.run_post_meeting_prompt.call_args.kwargs
            assert call_kwargs["from_minute"] is None
            assert call_kwargs["to_minute"] is None
