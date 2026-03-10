"""Tests for NiceGUI OutputPanel streaming pipeline (DAR2-37)."""

from __future__ import annotations

from unittest.mock import MagicMock, patch


class TestOutputPanelSetup:
    """Test scaffold HTML installation before streaming begins."""

    def test_setup_template_sets_scaffold_html(self) -> None:
        with patch("ui.components.output_panel.ui"):
            from ui.components.output_panel import OutputPanel

            controller = MagicMock()
            panel = OutputPanel(controller)
            panel._content = MagicMock()

            panel.setup_template("fill-gaps")

            html_set = panel._content.set_content.call_args[0][0]
            assert 'id="core-thinking-list"' in html_set
            assert 'id="gaps-list"' in html_set

    def test_setup_template_clears_buffer(self) -> None:
        with patch("ui.components.output_panel.ui"):
            from ui.components.output_panel import OutputPanel

            controller = MagicMock()
            panel = OutputPanel(controller)
            panel._content = MagicMock()

            # Simulate leftover buffer state
            panel._buffer.write_and_extract("<li>partial")
            panel.setup_template("meeting-summary")

            # Buffer should be cleared — old partial should not appear
            items = panel._buffer.write_and_extract("</li>")
            assert items == []

    def test_setup_template_uses_config_pattern(self) -> None:
        with patch("ui.components.output_panel.ui"):
            from ui.components.output_panel import OutputPanel

            controller = MagicMock()
            panel = OutputPanel(controller)
            panel._content = MagicMock()

            panel.setup_template("fact-check")

            # fact-check has a specific pattern — verify buffer was recreated with it
            assert "fact-check-item" in panel._buffer._pattern


class TestOutputPanelStreaming:
    """Test chunk processing — buffer + extract + route."""

    def test_complete_item_appended_via_js(self) -> None:
        with patch("ui.components.output_panel.ui") as mock_ui:
            from ui.components.output_panel import OutputPanel

            controller = MagicMock()
            panel = OutputPanel(controller)
            panel._content = MagicMock()
            panel._scroll = MagicMock()

            panel.setup_template("meeting-summary")
            panel.handle_stream_chunk('<li class="insight-item">Point A</li>')

            # Should have called run_javascript for incremental append
            mock_ui.run_javascript.assert_called()
            js_call = mock_ui.run_javascript.call_args[0][0]
            assert "insertAdjacentHTML" in js_call
            assert "dynamic-content" in js_call

    def test_partial_item_not_appended(self) -> None:
        with patch("ui.components.output_panel.ui") as mock_ui:
            from ui.components.output_panel import OutputPanel

            controller = MagicMock()
            panel = OutputPanel(controller)
            panel._content = MagicMock()
            panel._scroll = MagicMock()

            panel.setup_template("meeting-summary")
            panel.handle_stream_chunk('<li class="insight-item">partial...')

            mock_ui.run_javascript.assert_not_called()

    def test_multi_list_routing(self) -> None:
        with patch("ui.components.output_panel.ui") as mock_ui:
            from ui.components.output_panel import OutputPanel

            controller = MagicMock()
            panel = OutputPanel(controller)
            panel._content = MagicMock()
            panel._scroll = MagicMock()

            panel.setup_template("fill-gaps")
            panel.handle_stream_chunk('<li class="gap-item">Missing data</li>')

            js_call = mock_ui.run_javascript.call_args[0][0]
            assert "gaps-list" in js_call


class TestOutputPanelFinalize:
    """Test _finalize behavior with registered templates."""

    def test_finalize_skips_replace_for_registered_template(self) -> None:
        with patch("ui.components.output_panel.ui"):
            from ui.components.output_panel import OutputPanel

            controller = MagicMock()
            panel = OutputPanel(controller)
            panel._content = MagicMock()
            panel._scroll = MagicMock()

            panel.setup_template("fill-gaps")
            panel._content.set_content.reset_mock()  # clear setup call
            panel._finalize({"result": "raw text"})

            # Should NOT replace content — scaffold + streamed items are already correct
            panel._content.set_content.assert_not_called()

    def test_finalize_replaces_for_unregistered_template(self) -> None:
        with patch("ui.components.output_panel.ui"):
            from ui.components.output_panel import OutputPanel

            controller = MagicMock()
            panel = OutputPanel(controller)
            panel._content = MagicMock()
            panel._md_content = MagicMock()
            panel._scroll = MagicMock()

            # No setup_template called — _template_type is None
            panel._finalize({"result": "Final analysis"})

            panel._md_content.set_content.assert_called_with("Final analysis")


class TestOutputPanelCallbackWiring:
    """Test controller callback registration."""

    def test_controller_callbacks_wired(self) -> None:
        with patch("ui.components.output_panel.ui"):
            from ui.components.output_panel import OutputPanel

            controller = MagicMock()
            OutputPanel(controller)

            assert controller.on_stream_chunk is not None
            assert controller.on_processing_complete is not None

    def test_clear_resets_state(self) -> None:
        with patch("ui.components.output_panel.ui"):
            from ui.components.output_panel import OutputPanel

            controller = MagicMock()
            panel = OutputPanel(controller)
            panel._content = MagicMock()

            panel.setup_template("fill-gaps")
            panel.clear()

            assert panel._template_type is None
            panel._content.set_content.assert_called_with("")
