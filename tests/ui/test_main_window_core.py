"""
Core MainWindow Unit Tests

Tests core functionality including:
- Window initialization
- Thread-safe properties
- Signal connections
- UI component setup
"""

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from PyQt6.QtWidgets import QApplication


# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from ui.main_window import MainWindow


@pytest.fixture(scope="session")
def qapp():
    """Create QApplication for PyQt tests."""
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    yield app
    # Don't quit to allow multiple tests


@pytest.fixture
def mock_recorder():
    """Mock ContinuousRecorder to avoid audio hardware dependencies."""
    with patch("ui.main_window.ContinuousRecorder") as mock:
        recorder_instance = MagicMock()
        recorder_instance.is_recording = False
        recorder_instance.sample_rate = 16000
        recorder_instance.get_buffer_seconds.return_value = 60
        mock.return_value = recorder_instance
        yield recorder_instance


@pytest.fixture
def mock_api_client():
    """Mock ApiClient to avoid network dependencies."""
    with patch("ui.main_window.ApiClient") as mock:
        api_instance = MagicMock()
        mock.return_value = api_instance
        yield api_instance


@pytest.fixture
def mock_font_manager():
    """Mock FontManager to avoid font loading."""
    with patch("ui.main_window.FontManager") as mock:
        mock.load_fonts.return_value = None
        mock.get_font.return_value = MagicMock()
        yield mock


@pytest.fixture
def main_window(qapp, mock_recorder, mock_api_client, mock_font_manager):
    """Create MainWindow instance for testing."""
    with patch("ui.main_window.logger"):
        window = MainWindow()
        yield window
        window.close()


class TestMainWindowInitialization:
    """Test MainWindow initialization."""

    def test_window_title(self, main_window):
        """Test window has correct title."""
        assert main_window.windowTitle() == "Darin Audio Assistant"

    def test_window_geometry(self, main_window):
        """Test window has correct initial geometry."""
        geometry = main_window.geometry()
        assert geometry.width() == 1000
        assert geometry.height() == 700

    def test_initial_processing_state(self, main_window):
        """Test window initializes with processing=False."""
        assert main_window.is_processing is False

    def test_initial_transcript(self, main_window):
        """Test window initializes with empty transcript."""
        assert main_window.current_transcript == ""

    def test_recorder_initialized(self, main_window, mock_recorder):
        """Test recorder is initialized."""
        assert main_window.recorder is not None

    def test_api_client_initialized(self, main_window, mock_api_client):
        """Test API client is initialized."""
        assert main_window.api_client is not None

    def test_html_state_initialized(self, main_window):
        """Test HTML streaming state is initialized."""
        assert main_window._buffer_io.getvalue() == ""
        assert main_window._current_element is None
        assert main_window._element_stack == []
        assert main_window._is_first_update is True
        assert main_window._current_list_items == []

    def test_sentiment_state_initialized(self, main_window):
        """Test sentiment analysis state is initialized."""
        assert main_window._first_line_received is False


class TestThreadSafeProperties:
    """Test thread-safe property accessors."""

    def test_current_transcript_getter(self, main_window):
        """Test current_transcript property getter is thread-safe."""
        main_window._current_transcript = "Test transcript"
        assert main_window.current_transcript == "Test transcript"

    def test_current_transcript_setter(self, main_window):
        """Test current_transcript property setter is thread-safe."""
        main_window.current_transcript = "New transcript"
        assert main_window._current_transcript == "New transcript"

    def test_is_processing_getter(self, main_window):
        """Test is_processing property getter is thread-safe."""
        main_window._is_processing = True
        assert main_window.is_processing is True

    def test_is_processing_setter(self, main_window):
        """Test is_processing property setter is thread-safe."""
        main_window.is_processing = True
        assert main_window._is_processing is True
        main_window.is_processing = False
        assert main_window._is_processing is False

    def test_concurrent_transcript_access(self, main_window):
        """Test concurrent access to transcript property doesn't cause race conditions."""
        import threading

        results = []
        errors = []

        def writer(value):
            try:
                for _ in range(100):
                    main_window.current_transcript = value
            except Exception as e:
                errors.append(e)

        def reader():
            try:
                for _ in range(100):
                    _ = main_window.current_transcript
                    results.append(True)
            except Exception as e:
                errors.append(e)

        threads = [
            threading.Thread(target=writer, args=("Thread1",)),
            threading.Thread(target=writer, args=("Thread2",)),
            threading.Thread(target=reader),
            threading.Thread(target=reader),
        ]

        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert len(errors) == 0
        assert len(results) == 200  # 2 readers * 100 iterations

    def test_concurrent_processing_access(self, main_window):
        """Test concurrent access to is_processing property doesn't cause race conditions."""
        import threading

        errors = []

        def toggle_processing():
            try:
                for _ in range(100):
                    main_window.is_processing = True
                    main_window.is_processing = False
            except Exception as e:
                errors.append(e)

        threads = [
            threading.Thread(target=toggle_processing),
            threading.Thread(target=toggle_processing),
        ]

        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert len(errors) == 0
        # Final state should be False
        assert main_window.is_processing is False


class TestSignalConnections:
    """Test signal/slot connections."""

    def test_custom_signals_defined(self, main_window):
        """Test all custom signals are defined."""
        assert hasattr(main_window, "recording_started")
        assert hasattr(main_window, "recording_stopped")
        assert hasattr(main_window, "transcription_complete")
        assert hasattr(main_window, "processing_complete")
        assert hasattr(main_window, "progress_update")
        assert hasattr(main_window, "stream_update")

    def test_controls_panel_signals_connected(self, main_window):
        """Test controls panel signals are connected."""
        # Verify controls panel exists
        assert hasattr(main_window, "controls_panel")
        assert main_window.controls_panel is not None

    def test_output_panel_exists(self, main_window):
        """Test output panel is created."""
        assert hasattr(main_window, "output_panel")
        assert main_window.output_panel is not None

    def test_content_splitter_exists(self, main_window):
        """Test content splitter is created."""
        assert hasattr(main_window, "content_splitter")
        assert main_window.content_splitter is not None


class TestUIComponents:
    """Test UI component initialization."""

    def test_controls_panel_max_width(self, main_window):
        """Test controls panel has maximum width set."""
        assert main_window.controls_panel.maximumWidth() == 300

    def test_splitter_proportions(self, main_window):
        """Test splitter is configured with correct proportions."""
        # Splitter should have 2 widgets
        assert main_window.content_splitter.count() == 2
        # Stretch factors: 1 for controls, 3 for output
        assert main_window.content_splitter.stretchFactor(0) == 1
        assert main_window.content_splitter.stretchFactor(1) == 3


class TestClearOutput:
    """Test clear_output method."""

    def test_clear_output_resets_transcript(self, main_window):
        """Test clear_output resets transcript."""
        main_window.current_transcript = "Test transcript"
        main_window.clear_output()
        assert main_window.current_transcript == ""

    def test_clear_output_resets_html_state(self, main_window):
        """Test clear_output resets HTML streaming state."""
        main_window._buffer_io.write("<li>Test</li>")
        main_window._current_element = {"type": "test"}
        main_window._element_stack = [{"type": "test"}]
        main_window._is_first_update = False
        main_window._current_list_items = ["item1"]

        main_window.clear_output()

        assert main_window._buffer_io.getvalue() == ""
        assert main_window._current_element is None
        assert main_window._element_stack == []
        assert main_window._is_first_update is True
        assert main_window._current_list_items == []

    def test_clear_output_resets_sentiment_flag(self, main_window):
        """Test clear_output resets sentiment received flag."""
        main_window._first_line_received = True
        main_window.clear_output()
        assert main_window._first_line_received is False
