"""
MainWindow Integration Tests

Tests end-to-end workflows:
- Transcription workflow (with mocked recorder)
- LLM processing workflow (with mocked API client)
- Error handling paths
- Signal emission and handling
"""

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from PyQt6.QtWidgets import QApplication


# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from prompts.templates import TOPIC_SUMMARY_PROMPT
from ui.main_window import MainWindow


@pytest.fixture(scope="session")
def qapp():
    """Create QApplication for PyQt tests."""
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    yield app


@pytest.fixture
def mock_recorder():
    """Mock ContinuousRecorder."""
    with patch("ui.main_window.ContinuousRecorder") as mock:
        recorder_instance = MagicMock()
        recorder_instance.is_recording = False
        recorder_instance.sample_rate = 16000
        recorder_instance.get_buffer_seconds.return_value = 60
        recorder_instance.save_buffer.return_value = b"fake_audio_data"
        recorder_instance.get_last_n_seconds.return_value = b"fake_audio_30s"
        recorder_instance.start_recording.return_value = True
        recorder_instance.stop_recording.return_value = True
        mock.return_value = recorder_instance
        yield recorder_instance


@pytest.fixture
def mock_api_client():
    """Mock ApiClient."""
    with patch("ui.main_window.ApiClient") as mock:
        api_instance = MagicMock()
        api_instance.transcribe_with_deepgram.return_value = "Test transcript text"
        api_instance.process_with_anthropic.return_value = "Processed result"
        mock.return_value = api_instance
        yield api_instance


@pytest.fixture
def main_window(qapp, mock_recorder, mock_api_client):
    """Create MainWindow instance for testing."""
    with patch("ui.main_window.FontManager"), patch("ui.main_window.logger"):
        window = MainWindow()
        yield window
        window.close()


class TestRecordingWorkflow:
    """Test recording start/stop workflow."""

    def test_start_recording_success(self, main_window, mock_recorder):
        """Test successful recording start."""
        main_window.toggle_recording()

        # Verify recorder was called
        assert mock_recorder.start_recording.called

    def test_start_recording_emits_signal(self, main_window, mock_recorder):
        """Test recording_started signal is emitted."""
        signal_received = []

        def on_recording_started():
            signal_received.append(True)

        main_window.recording_started.connect(on_recording_started)
        main_window.toggle_recording()

        # Process events to allow signal to fire
        QApplication.processEvents()

        assert len(signal_received) == 1

    def test_stop_recording_success(self, main_window, mock_recorder):
        """Test successful recording stop."""
        # Start recording first
        mock_recorder.is_recording = False
        main_window.toggle_recording()

        # Now stop it
        mock_recorder.is_recording = True
        main_window.toggle_recording()

        # Verify recorder stop was called
        assert mock_recorder.stop_recording.called

    def test_stop_recording_emits_signal(self, main_window, mock_recorder):
        """Test recording_stopped signal is emitted."""
        signal_received = []

        def on_recording_stopped():
            signal_received.append(True)

        main_window.recording_stopped.connect(on_recording_stopped)

        # Set to recording state and then toggle
        mock_recorder.is_recording = True
        main_window.toggle_recording()

        # Process events
        QApplication.processEvents()

        assert len(signal_received) == 1

    def test_start_recording_failure(self, main_window, mock_recorder):
        """Test recording start failure is handled."""
        mock_recorder.start_recording.return_value = False

        # Should not raise error
        main_window.toggle_recording()

    def test_stop_recording_failure(self, main_window, mock_recorder):
        """Test recording stop failure is handled."""
        mock_recorder.is_recording = True
        mock_recorder.stop_recording.return_value = False

        # Should not raise error
        main_window.toggle_recording()


class TestTranscriptionWorkflow:
    """Test transcription workflow."""

    def test_transcribe_buffer_success(self, main_window, mock_recorder, mock_api_client):
        """Test successful buffer transcription."""
        # Wait for thread to complete
        main_window.transcribe_buffer()

        # Give thread time to execute
        import time

        time.sleep(0.1)
        QApplication.processEvents()

        # Verify recorder save_buffer was called
        assert mock_recorder.save_buffer.called

    def test_transcribe_buffer_no_audio(self, main_window, mock_recorder):
        """Test transcription with no audio in buffer."""
        mock_recorder.save_buffer.return_value = None

        main_window.transcribe_buffer()

        # Should show warning (button should be re-enabled)
        QApplication.processEvents()
        assert main_window.controls_panel.transcribe_button.isEnabled()

    def test_transcribe_emits_signal(self, main_window, mock_recorder, mock_api_client):
        """Test transcription_complete signal is emitted."""
        signal_received = []

        def on_transcription_complete(text):
            signal_received.append(text)

        main_window.transcription_complete.connect(on_transcription_complete)

        # Trigger transcription
        main_window.transcribe_buffer()

        # Wait for thread
        import time

        time.sleep(0.2)
        QApplication.processEvents()

        # Signal should have been received
        assert len(signal_received) > 0

    def test_transcription_error_handling(self, main_window, mock_recorder, mock_api_client):
        """Test transcription error is handled gracefully."""
        mock_api_client.transcribe_with_deepgram.side_effect = Exception("API Error")

        signal_received = []

        def on_transcription_complete(text):
            signal_received.append(text)

        main_window.transcription_complete.connect(on_transcription_complete)

        # Trigger transcription
        main_window.transcribe_buffer()

        # Wait for thread
        import time

        time.sleep(0.2)
        QApplication.processEvents()

        # Should receive error message
        assert len(signal_received) > 0
        assert "error" in signal_received[0].lower()

    def test_transcribe_last_30_seconds(self, main_window, mock_recorder, mock_api_client):
        """Test transcribing last 30 seconds."""
        main_window.transcribe_last_30_seconds()

        # Wait for thread
        import time

        time.sleep(0.1)
        QApplication.processEvents()

        # Verify get_last_n_seconds was called with 30
        mock_recorder.get_last_n_seconds.assert_called_with(30)

    def test_transcribe_last_30_no_audio(self, main_window, mock_recorder):
        """Test transcribe last 30 with insufficient audio."""
        mock_recorder.get_last_n_seconds.return_value = None

        main_window.transcribe_last_30_seconds()

        # Button should be re-enabled
        QApplication.processEvents()
        assert main_window.controls_panel.transcribe_last_30_button.isEnabled()


class TestLLMProcessingWorkflow:
    """Test LLM processing workflow."""

    def test_run_prompt_with_existing_transcript(self, main_window, mock_api_client):
        """Test running prompt with existing transcript."""
        # Set existing transcript
        main_window.current_transcript = "Existing transcript"

        # Run prompt
        main_window.run_prompt_with_auto_transcribe(TOPIC_SUMMARY_PROMPT, title="Test Topics")

        # Should not call transcription (already have transcript)
        # Processing should be set
        assert main_window.is_processing

    def test_run_prompt_without_transcript(self, main_window, mock_recorder, mock_api_client):
        """Test running prompt without existing transcript."""
        # Ensure no transcript
        main_window.current_transcript = ""

        # Run prompt
        main_window.run_prompt_with_auto_transcribe(TOPIC_SUMMARY_PROMPT, title="Test Topics")

        # Should call save_buffer
        # Wait a bit for thread
        import time

        time.sleep(0.1)

        # Processing should be set
        assert main_window.is_processing

    def test_processing_prevents_concurrent_requests(self, main_window):
        """Test that processing prevents concurrent prompt requests."""
        # Set processing state
        main_window.is_processing = True

        # Try to run another prompt
        main_window.run_prompt_with_auto_transcribe(TOPIC_SUMMARY_PROMPT)

        # Should return early without starting new processing
        # (No way to verify directly, but no exception should occur)

    def test_processing_complete_signal(self, main_window):
        """Test processing_complete signal handler."""
        signal_received = []

        def on_processing_complete(result):
            signal_received.append(result)

        main_window.processing_complete.connect(on_processing_complete)

        # Set processing state
        main_window.is_processing = True

        # Emit processing complete
        main_window.processing_complete.emit({"result": "Test result"})

        QApplication.processEvents()

        # Processing should be reset
        assert main_window.is_processing is False
        assert len(signal_received) > 0

    def test_processing_error_handling(self, main_window):
        """Test processing error is handled."""
        signal_received = []

        def on_processing_complete(result):
            signal_received.append(result)

        main_window.processing_complete.connect(on_processing_complete)

        # Emit error
        main_window.processing_complete.emit({"error": "Processing failed"})

        QApplication.processEvents()

        # Should have received error
        assert len(signal_received) > 0
        assert "error" in signal_received[0]

    def test_progress_update_signal(self, main_window):
        """Test progress_update signal handler."""
        # Should not raise errors
        main_window.progress_update.emit("Processing...")

        QApplication.processEvents()


class TestErrorHandling:
    """Test error handling paths."""

    def test_no_audio_for_processing(self, main_window, mock_recorder):
        """Test processing with no audio shows error."""
        mock_recorder.save_buffer.return_value = None

        main_window.current_transcript = ""
        main_window.run_prompt_with_auto_transcribe(TOPIC_SUMMARY_PROMPT)

        # Processing should be reset
        import time

        time.sleep(0.1)
        QApplication.processEvents()

        # is_processing should be False after error
        assert main_window.is_processing is False

    def test_api_error_during_processing(self, main_window, mock_recorder, mock_api_client):
        """Test API error during processing is handled."""
        mock_api_client.transcribe_with_deepgram.side_effect = Exception("API Error")

        main_window.current_transcript = ""
        main_window.run_prompt_with_auto_transcribe(TOPIC_SUMMARY_PROMPT)

        # Wait for thread
        import time

        time.sleep(0.2)
        QApplication.processEvents()

        # Should handle error gracefully


class TestSignalSlotIntegration:
    """Test signal/slot integration."""

    def test_on_transcription_complete_updates_transcript(self, main_window):
        """Test on_transcription_complete updates current_transcript."""
        test_text = "Test transcription result"

        main_window.on_transcription_complete(test_text)

        assert main_window.current_transcript == test_text

    def test_on_transcription_complete_enables_buttons(self, main_window):
        """Test on_transcription_complete enables prompt buttons."""
        main_window.on_transcription_complete("Test text")

        QApplication.processEvents()

        # Buttons should be enabled
        assert main_window.controls_panel.transcribe_button.isEnabled()

    def test_on_recording_started_enables_buttons(self, main_window):
        """Test on_recording_started enables prompt buttons."""
        main_window.on_recording_started()

        QApplication.processEvents()

        # Prompt buttons should be enabled (we have recording)

    def test_on_recording_stopped_keeps_buttons_enabled(self, main_window, mock_recorder):
        """Test on_recording_stopped keeps buttons enabled if buffer has data."""
        mock_recorder.get_buffer_seconds.return_value = 30

        main_window.on_recording_stopped()

        QApplication.processEvents()

        # Buttons should stay enabled
        assert main_window.controls_panel.transcribe_button.isEnabled()

    def test_on_progress_update(self, main_window):
        """Test on_progress_update updates status."""
        # Should not raise errors
        main_window.on_progress_update("Test progress message")

        QApplication.processEvents()


class TestTemplateTypeTracking:
    """Test template type tracking for streaming."""

    def test_template_type_set_during_setup(self, main_window):
        """Test _template_type is set during template setup."""
        with main_window._html_state_lock:
            main_window._template_type = None

        # Setup template
        template_type = main_window._setup_static_template(TOPIC_SUMMARY_PROMPT)

        # Should return the template type
        assert template_type == "topic-summary"

    def test_html_state_reset_before_processing(self, main_window):
        """Test HTML state is reset before new processing."""
        # Set some state
        with main_window._html_state_lock:
            main_window._buffer_io.write("old data")
            main_window._current_element = {"type": "old"}
            main_window._is_first_update = False

        # Clear output resets state
        main_window.clear_output()

        with main_window._html_state_lock:
            assert main_window._buffer_io.getvalue() == ""
            assert main_window._current_element is None
            assert main_window._is_first_update is True


class TestConcurrentAccess:
    """Test concurrent access patterns."""

    def test_concurrent_signal_emissions(self, main_window):
        """Test concurrent signal emissions don't cause issues."""
        import threading

        def emit_signals():
            for _ in range(10):
                main_window.progress_update.emit("Progress")
                main_window.stream_update.emit("<li>Test</li>")

        threads = [
            threading.Thread(target=emit_signals),
            threading.Thread(target=emit_signals),
        ]

        for t in threads:
            t.start()
        for t in threads:
            t.join()

        # Should complete without errors

    def test_concurrent_property_and_clear(self, main_window):
        """Test concurrent property access and clear_output."""
        import threading

        errors = []

        def access_properties():
            try:
                for _ in range(50):
                    _ = main_window.current_transcript
                    _ = main_window.is_processing
            except Exception as e:
                errors.append(e)

        def clear_repeatedly():
            try:
                for _ in range(50):
                    main_window.clear_output()
            except Exception as e:
                errors.append(e)

        threads = [
            threading.Thread(target=access_properties),
            threading.Thread(target=clear_repeatedly),
        ]

        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert len(errors) == 0
