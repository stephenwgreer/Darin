"""Tests for OutputPanel component (DAR2-26)."""

from __future__ import annotations

from unittest.mock import MagicMock, patch


class TestOutputPanelLogic:
    """Test OutputPanel's content management without NiceGUI server."""

    def test_append_chunk_accumulates_text(self) -> None:
        with patch("ui.components.output_panel.ui"):
            from ui.components.output_panel import OutputPanel

            panel = OutputPanel(MagicMock())
            panel._content = MagicMock()
            panel._content.content = ""
            panel._scroll = MagicMock()

            panel._append_chunk("Hello ")
            panel._content.set_content.assert_called_with("Hello ")

    def test_finalize_replaces_content(self) -> None:
        with patch("ui.components.output_panel.ui"):
            from ui.components.output_panel import OutputPanel

            panel = OutputPanel(MagicMock())
            panel._content = MagicMock()
            panel._scroll = MagicMock()

            panel._finalize({"result": "Final analysis"})
            panel._content.set_content.assert_called_with("Final analysis")

    def test_clear_resets_content(self) -> None:
        with patch("ui.components.output_panel.ui"):
            from ui.components.output_panel import OutputPanel

            panel = OutputPanel(MagicMock())
            panel._content = MagicMock()

            panel.clear()
            panel._content.set_content.assert_called_with("")

    def test_controller_callbacks_wired(self) -> None:
        with patch("ui.components.output_panel.ui"):
            from ui.components.output_panel import OutputPanel

            controller = MagicMock()
            panel = OutputPanel(controller)

            assert controller.on_stream_chunk is not None
            assert controller.on_processing_complete is not None
