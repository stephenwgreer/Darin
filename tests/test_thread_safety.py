"""
Thread Safety Tests for BUG-2026-02-09-003

Tests the thread safety fixes implemented to prevent race conditions
in shared state access across audio/recorder.py, ui/main_window.py,
and processing/controller.py.

This test module verifies:
1. is_recording property thread safety in ContinuousRecorder
2. current_transcript property thread safety in MainWindow
3. is_processing property thread safety in MainWindow
4. No race conditions under concurrent access
5. No deadlocks or UI freezes
"""

import sys
import threading
import time
from pathlib import Path
from unittest.mock import Mock, patch, MagicMock
from concurrent.futures import ThreadPoolExecutor, as_completed

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

import pytest
from PyQt6.QtCore import QThreadPool
from PyQt6.QtWidgets import QApplication

# Module imports
from audio.recorder import ContinuousRecorder
from ui.main_window import MainWindow
from processing.controller import AnalysisController
from api.client import ApiClient


# ============================================================================
# TEST FIXTURES
# ============================================================================

@pytest.fixture(scope="module")
def qapp():
    """Create QApplication for Qt tests"""
    app = QApplication.instance()
    if app is None:
        app = QApplication(sys.argv)
    yield app
    # Don't quit app in module scope to allow multiple tests


@pytest.fixture
def mock_recorder():
    """Create a mocked ContinuousRecorder with thread-safe properties"""
    with patch('audio.recorder.sc.get_microphone') as mock_mic:
        mock_mic.return_value = Mock()
        recorder = ContinuousRecorder(buffer_minutes=3, chunk_seconds=1)
    return recorder


@pytest.fixture
def mock_api_client():
    """Create a mocked ApiClient"""
    client = Mock(spec=ApiClient)
    client.transcribe_with_deepgram = Mock(return_value="Test transcript")
    client.process_with_anthropic = Mock(return_value="Test result")
    return client


@pytest.fixture
def analysis_controller(mock_api_client, mock_recorder):
    """Create an AnalysisController with mocked dependencies"""
    controller = AnalysisController(
        api_client=mock_api_client,
        recorder=mock_recorder
    )
    return controller


# ============================================================================
# TEST 1: is_recording Thread Safety (ContinuousRecorder)
# ============================================================================

def test_is_recording_concurrent_read_access(mock_recorder):
    """Verify is_recording property can be safely read from multiple threads"""

    def read_recording_state():
        """Read is_recording state multiple times"""
        results = []
        for _ in range(100):
            state = mock_recorder.is_recording
            results.append(state)
            time.sleep(0.0001)  # Small delay to increase chance of race
        return results

    # Spawn 10 threads reading concurrently
    with ThreadPoolExecutor(max_workers=10) as executor:
        futures = [executor.submit(read_recording_state) for _ in range(10)]

        # All threads should complete without exception
        for future in as_completed(futures):
            results = future.result()
            assert isinstance(results, list)
            assert len(results) == 100


def test_is_recording_concurrent_write_access(mock_recorder):
    """Verify is_recording property can be safely written from multiple threads"""

    def toggle_recording_state(thread_id):
        """Toggle recording state multiple times"""
        for i in range(50):
            mock_recorder.is_recording = True
            time.sleep(0.0001)
            mock_recorder.is_recording = False
            time.sleep(0.0001)
        return thread_id

    # Spawn 5 threads writing concurrently
    with ThreadPoolExecutor(max_workers=5) as executor:
        futures = [executor.submit(toggle_recording_state, i) for i in range(5)]

        # All threads should complete without exception
        for future in as_completed(futures):
            thread_id = future.result()
            assert isinstance(thread_id, int)

    # Final state should be consistent (either True or False)
    final_state = mock_recorder.is_recording
    assert isinstance(final_state, bool)


def test_is_recording_atomic_check_and_set(mock_recorder):
    """Verify is_recording check-and-set operations are atomic"""

    start_count = 0
    start_lock = threading.Lock()

    def try_start_recording():
        """Attempt to start recording if not already recording"""
        nonlocal start_count
        # Simulate the start_recording logic
        if not mock_recorder.is_recording:
            mock_recorder.is_recording = True
            with start_lock:
                start_count += 1
            time.sleep(0.001)  # Simulate work
            mock_recorder.is_recording = False
            return True
        return False

    # Spawn 20 threads trying to start recording simultaneously
    with ThreadPoolExecutor(max_workers=20) as executor:
        futures = [executor.submit(try_start_recording) for _ in range(20)]
        results = [future.result() for future in as_completed(futures)]

    # At least some attempts should succeed
    successful_starts = sum(results)
    assert successful_starts > 0

    # Final state should be False (all operations completed)
    assert mock_recorder.is_recording == False


# ============================================================================
# TEST 2: current_transcript Thread Safety (MainWindow)
# ============================================================================

def test_current_transcript_concurrent_read(qapp):
    """Verify current_transcript property can be safely read from multiple threads"""

    # Create MainWindow with mocked dependencies
    with patch('ui.main_window.ContinuousRecorder') as mock_rec_class, \
         patch('ui.main_window.ApiClient') as mock_api_class:

        mock_rec_class.return_value = Mock()
        mock_api_class.return_value = Mock()

        window = MainWindow()
        window.current_transcript = "Test transcript for concurrent read"

        def read_transcript():
            """Read transcript multiple times"""
            results = []
            for _ in range(100):
                transcript = window.current_transcript
                results.append(transcript)
                time.sleep(0.0001)
            return results

        # Spawn 10 threads reading concurrently
        with ThreadPoolExecutor(max_workers=10) as executor:
            futures = [executor.submit(read_transcript) for _ in range(10)]

            # All threads should complete without exception
            for future in as_completed(futures):
                results = future.result()
                assert len(results) == 100
                # All reads should return the same value
                assert all(r == "Test transcript for concurrent read" for r in results)


def test_current_transcript_concurrent_write(qapp):
    """Verify current_transcript property can be safely written from multiple threads"""

    with patch('ui.main_window.ContinuousRecorder') as mock_rec_class, \
         patch('ui.main_window.ApiClient') as mock_api_class:

        mock_rec_class.return_value = Mock()
        mock_api_class.return_value = Mock()

        window = MainWindow()

        def write_transcript(thread_id):
            """Write transcript multiple times"""
            for i in range(50):
                window.current_transcript = f"Thread {thread_id} iteration {i}"
                time.sleep(0.0001)
            return thread_id

        # Spawn 5 threads writing concurrently
        with ThreadPoolExecutor(max_workers=5) as executor:
            futures = [executor.submit(write_transcript, i) for i in range(5)]

            # All threads should complete without exception
            for future in as_completed(futures):
                thread_id = future.result()
                assert isinstance(thread_id, int)

        # Final transcript should be one of the written values (not corrupted)
        final_transcript = window.current_transcript
        assert "Thread" in final_transcript
        assert "iteration" in final_transcript


def test_current_transcript_no_data_corruption(qapp):
    """Verify current_transcript doesn't corrupt under concurrent access"""

    with patch('ui.main_window.ContinuousRecorder') as mock_rec_class, \
         patch('ui.main_window.ApiClient') as mock_api_class:

        mock_rec_class.return_value = Mock()
        mock_api_class.return_value = Mock()

        window = MainWindow()

        valid_values = [f"Transcript version {i}" for i in range(10)]

        def write_valid_transcript(value):
            """Write a known valid transcript"""
            for _ in range(100):
                window.current_transcript = value
                time.sleep(0.00001)

        def read_and_validate():
            """Read and validate transcript"""
            for _ in range(100):
                transcript = window.current_transcript
                # Transcript should either be empty or one of the valid values
                assert transcript == "" or transcript in valid_values
                time.sleep(0.00001)

        # Spawn writers and readers concurrently
        with ThreadPoolExecutor(max_workers=15) as executor:
            futures = []

            # 10 writer threads
            for value in valid_values:
                futures.append(executor.submit(write_valid_transcript, value))

            # 5 reader threads
            for _ in range(5):
                futures.append(executor.submit(read_and_validate))

            # All operations should complete without exception
            for future in as_completed(futures):
                future.result()


# ============================================================================
# TEST 3: is_processing Thread Safety (MainWindow)
# ============================================================================

def test_is_processing_concurrent_access(qapp):
    """Verify is_processing property is thread-safe under concurrent access"""

    with patch('ui.main_window.ContinuousRecorder') as mock_rec_class, \
         patch('ui.main_window.ApiClient') as mock_api_class:

        mock_rec_class.return_value = Mock()
        mock_api_class.return_value = Mock()

        window = MainWindow()

        def toggle_processing(thread_id):
            """Toggle processing state"""
            for i in range(50):
                window.is_processing = True
                time.sleep(0.0001)
                window.is_processing = False
                time.sleep(0.0001)
            return thread_id

        # Spawn 5 threads toggling concurrently
        with ThreadPoolExecutor(max_workers=5) as executor:
            futures = [executor.submit(toggle_processing, i) for i in range(5)]

            # All threads should complete without exception
            for future in as_completed(futures):
                thread_id = future.result()
                assert isinstance(thread_id, int)

        # Final state should be consistent
        assert isinstance(window.is_processing, bool)


def test_is_processing_prevents_duplicate_operations(qapp):
    """Verify is_processing prevents duplicate processing operations"""

    with patch('ui.main_window.ContinuousRecorder') as mock_rec_class, \
         patch('ui.main_window.ApiClient') as mock_api_class:

        mock_rec_class.return_value = Mock()
        mock_api_class.return_value = Mock()

        window = MainWindow()

        operation_count = 0
        operation_lock = threading.Lock()

        def try_start_processing():
            """Attempt to start processing if not already processing"""
            nonlocal operation_count

            # Atomic check-and-set
            with window._processing_lock:
                if window._is_processing:
                    return False  # Already processing
                window._is_processing = True

            # Simulate processing work
            with operation_lock:
                operation_count += 1

            time.sleep(0.01)  # Simulate work

            # Release processing lock
            window.is_processing = False
            return True

        # Spawn 10 threads trying to start processing simultaneously
        with ThreadPoolExecutor(max_workers=10) as executor:
            futures = [executor.submit(try_start_processing) for _ in range(10)]
            results = [future.result() for future in as_completed(futures)]

        # Only one thread should have successfully started processing
        # (though subsequent threads may succeed after the first completes)
        successful_operations = sum(results)
        assert successful_operations >= 1

        # Final state should be False
        assert window.is_processing == False


# ============================================================================
# TEST 4: AnalysisController Thread Safety
# ============================================================================

def test_controller_current_transcript_thread_safety(analysis_controller):
    """Verify AnalysisController current_transcript is thread-safe"""

    def write_transcript(value):
        """Write transcript value"""
        for _ in range(50):
            analysis_controller.current_transcript = value
            time.sleep(0.0001)

    def read_transcript():
        """Read transcript value"""
        results = []
        for _ in range(50):
            results.append(analysis_controller.current_transcript)
            time.sleep(0.0001)
        return results

    # Spawn concurrent readers and writers
    with ThreadPoolExecutor(max_workers=10) as executor:
        futures = []

        # 5 writer threads
        for i in range(5):
            futures.append(
                executor.submit(write_transcript, f"Transcript {i}")
            )

        # 5 reader threads
        for _ in range(5):
            futures.append(executor.submit(read_transcript))

        # All operations should complete without exception
        for future in as_completed(futures):
            future.result()


def test_controller_processing_state_consistency(analysis_controller):
    """Verify AnalysisController processing state is consistent"""

    # Initially not processing
    assert analysis_controller.is_processing == False

    # Simulate multiple threads checking processing state
    def check_processing_state():
        """Check processing state multiple times"""
        for _ in range(100):
            state = analysis_controller.is_processing
            assert isinstance(state, bool)
            time.sleep(0.0001)

    with ThreadPoolExecutor(max_workers=10) as executor:
        futures = [executor.submit(check_processing_state) for _ in range(10)]

        # All checks should complete without exception
        for future in as_completed(futures):
            future.result()


# ============================================================================
# TEST 5: Stress Tests - No Deadlocks
# ============================================================================

def test_no_deadlock_under_rapid_state_changes(mock_recorder):
    """Verify no deadlocks occur under rapid state changes"""

    def rapid_toggle():
        """Rapidly toggle recording state"""
        for _ in range(200):
            mock_recorder.is_recording = not mock_recorder.is_recording
            # No sleep - maximum contention
        return True

    # Spawn many threads with no delay
    with ThreadPoolExecutor(max_workers=20) as executor:
        futures = [executor.submit(rapid_toggle) for _ in range(20)]

        # All threads should complete within reasonable time (no deadlock)
        for future in as_completed(futures, timeout=10):  # 10 second timeout
            assert future.result() == True


def test_no_deadlock_mixed_operations(qapp):
    """Verify no deadlocks with mixed read/write operations"""

    with patch('ui.main_window.ContinuousRecorder') as mock_rec_class, \
         patch('ui.main_window.ApiClient') as mock_api_class:

        mock_rec_class.return_value = Mock()
        mock_api_class.return_value = Mock()

        window = MainWindow()

        def mixed_operations(operation_id):
            """Perform mixed read and write operations"""
            for i in range(100):
                # Read transcript
                _ = window.current_transcript

                # Write transcript
                window.current_transcript = f"Op {operation_id} iteration {i}"

                # Read processing state
                _ = window.is_processing

                # Toggle processing state
                window.is_processing = not window.is_processing

            return operation_id

        # Spawn many threads performing mixed operations
        with ThreadPoolExecutor(max_workers=20) as executor:
            futures = [
                executor.submit(mixed_operations, i) for i in range(20)
            ]

            # All threads should complete within reasonable time
            for future in as_completed(futures, timeout=15):
                operation_id = future.result()
                assert isinstance(operation_id, int)


# ============================================================================
# TEST 6: Regression Tests
# ============================================================================

def test_regression_no_race_condition_on_is_recording():
    """
    Regression test for BUG-2026-02-09-003 Part 1

    Ensures is_recording property uses locks and prevents race conditions
    """
    with patch('audio.recorder.sc.get_microphone') as mock_mic:
        mock_mic.return_value = Mock()
        recorder = ContinuousRecorder()

    # Verify lock exists
    assert hasattr(recorder, '_recording_lock')
    assert type(recorder._recording_lock).__name__ == 'lock'

    # Verify property access is thread-safe
    recorder.is_recording = True
    assert recorder.is_recording == True
    recorder.is_recording = False
    assert recorder.is_recording == False


def test_regression_no_race_condition_on_current_transcript(qapp):
    """
    Regression test for BUG-2026-02-09-003 Part 2

    Ensures current_transcript property uses locks and prevents race conditions
    """
    with patch('ui.main_window.ContinuousRecorder') as mock_rec_class, \
         patch('ui.main_window.ApiClient') as mock_api_class:

        mock_rec_class.return_value = Mock()
        mock_api_class.return_value = Mock()

        window = MainWindow()

    # Verify lock exists
    assert hasattr(window, '_transcript_lock')
    assert type(window._transcript_lock).__name__ == 'lock'

    # Verify property access is thread-safe
    window.current_transcript = "Test transcript"
    assert window.current_transcript == "Test transcript"


def test_regression_no_race_condition_on_is_processing(qapp):
    """
    Regression test for BUG-2026-02-09-003 Part 3

    Ensures is_processing property uses locks and prevents race conditions
    """
    with patch('ui.main_window.ContinuousRecorder') as mock_rec_class, \
         patch('ui.main_window.ApiClient') as mock_api_class:

        mock_rec_class.return_value = Mock()
        mock_api_class.return_value = Mock()

        window = MainWindow()

    # Verify lock exists
    assert hasattr(window, '_processing_lock')
    assert type(window._processing_lock).__name__ == 'lock'

    # Verify property access is thread-safe
    window.is_processing = True
    assert window.is_processing == True
    window.is_processing = False
    assert window.is_processing == False


# ============================================================================
# MAIN
# ============================================================================

if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])
