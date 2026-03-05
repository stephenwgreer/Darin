"""Tests for PromptButtons component (DAR2-26)."""

from __future__ import annotations

from unittest.mock import MagicMock, patch


class TestPromptButtonsState:
    """Test prompt visibility by state."""

    def test_mid_meeting_visible_when_active(self) -> None:
        with patch("ui.components.prompt_buttons.ui"):
            from ui.components.prompt_buttons import PromptButtons

            pb = PromptButtons(MagicMock())
            pb._mid_meeting_card = MagicMock()
            pb._post_meeting_card = MagicMock()

            pb.set_state("active")

            pb._mid_meeting_card.set_visibility.assert_called_with(True)
            pb._post_meeting_card.set_visibility.assert_called_with(False)

    def test_mid_meeting_hidden_when_idle(self) -> None:
        with patch("ui.components.prompt_buttons.ui"):
            from ui.components.prompt_buttons import PromptButtons

            pb = PromptButtons(MagicMock())
            pb._mid_meeting_card = MagicMock()
            pb._post_meeting_card = MagicMock()

            pb.set_state("idle")

            pb._mid_meeting_card.set_visibility.assert_called_with(False)
            pb._post_meeting_card.set_visibility.assert_called_with(False)

    def test_post_meeting_visible_when_post(self) -> None:
        with patch("ui.components.prompt_buttons.ui"):
            from ui.components.prompt_buttons import PromptButtons

            pb = PromptButtons(MagicMock())
            pb._mid_meeting_card = MagicMock()
            pb._post_meeting_card = MagicMock()

            pb.set_state("post_meeting")

            pb._mid_meeting_card.set_visibility.assert_called_with(False)
            pb._post_meeting_card.set_visibility.assert_called_with(True)


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


class TestPromptTemplates:
    """Test prompt template definitions."""

    def test_mid_meeting_prompts_returns_tuples(self) -> None:
        with patch("ui.components.prompt_buttons.ui"):
            from ui.components.prompt_buttons import PromptButtons

            prompts = PromptButtons._mid_meeting_prompts()
            assert len(prompts) == 4
            for name, template in prompts:
                assert isinstance(name, str)
                assert isinstance(template, str)

    def test_post_meeting_prompts_returns_tuples(self) -> None:
        with patch("ui.components.prompt_buttons.ui"):
            from ui.components.prompt_buttons import PromptButtons

            prompts = PromptButtons._post_meeting_prompts()
            assert len(prompts) == 4
            for name, template in prompts:
                assert isinstance(name, str)
                assert isinstance(template, str)


class TestPromptButtonsTemplateSetup:
    """Verify PromptButtons passes on_template_setup to controller (DAR2-37)."""

    def test_run_prompt_passes_template_setup(self) -> None:
        with patch("ui.components.prompt_buttons.ui"):
            from ui.components.prompt_buttons import PromptButtons

            controller = MagicMock()
            output_panel = MagicMock()
            buttons = PromptButtons(controller, output_panel=output_panel)

            import asyncio
            asyncio.get_event_loop().run_until_complete(
                buttons._run_prompt("some_template")
            )

            controller.run_prompt.assert_called_once()
            call_kwargs = controller.run_prompt.call_args
            assert call_kwargs.kwargs.get("on_template_setup") is not None
