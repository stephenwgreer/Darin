import threading
import traceback

from loguru import logger
from PyQt6.QtCore import QObject, QRunnable, QThreadPool, pyqtSignal

# Assuming api.client and audio.recorder are structured appropriately
from api.client import ApiClient
from audio.recorder import ContinuousRecorder

# Assuming prompts are accessible
from prompts.templates import ANSWER_QUESTION_PROMPT, PRACTITIONER_INSIGHTS_STREAMING_PROMPT


class WorkerSignals(QObject):
    """
    Defines the signals available from a running worker thread.
    Supported signals are:
    finished
        No data
    error
        tuple (exctype, value, traceback.format_exc())
    result
        object data returned from processing, anything
    progress
        str update message
    stream
        str chunk of streaming data
    """

    finished = pyqtSignal()
    error = pyqtSignal(tuple)
    result = pyqtSignal(object)
    progress = pyqtSignal(str)
    stream = pyqtSignal(str)


class Worker(QRunnable):
    """
    Worker thread

    Inherits from QRunnable to handler worker thread setup, signals and wrap-up.

    :param callback: The function callback to run on this worker thread. Supplied args and
                     kwargs will be passed through to the runner.
    :type callback: function
    :param args: Arguments to pass to the callback function
    :param kwargs: Keywords to pass to the callback function

    """

    def __init__(self, fn, *args, **kwargs):
        super().__init__()

        # Store constructor arguments (re-used for processing)
        self.fn = fn
        self.args = args
        self.kwargs = kwargs
        self.signals = WorkerSignals()

        # Add the callback to our kwargs
        # self.kwargs['progress_callback'] = self.signals.progress # Example if function supports it

    def run(self):
        """
        Initialise the runner function with passed args, kwargs.
        """
        # Retrieve args/kwargs here; and fire processing using them
        try:
            result = self.fn(*self.args, **self.kwargs)
        except Exception as e:
            trace = traceback.format_exc()
            self.signals.error.emit((type(e), e, trace))
        else:
            self.signals.result.emit(result)  # Return the result of the processing
        finally:
            self.signals.finished.emit()  # Done


# --- Analysis Controller ---


class AnalysisController(QObject):
    # Signals to communicate back to the UI
    processing_started = pyqtSignal()
    processing_finished = pyqtSignal()
    transcription_complete = pyqtSignal(str)  # Emits the transcript text or error message
    analysis_complete = pyqtSignal(dict)  # Emits {result: text} or {error: text}
    stream_update = pyqtSignal(str)  # Emits chunks of text during streaming
    progress_update = pyqtSignal(str)  # Emits status messages

    def __init__(self, api_client: ApiClient, recorder: ContinuousRecorder, parent=None):
        super().__init__(parent)
        self.api_client = api_client
        self.recorder = recorder
        # Thread-safe transcript storage
        self._current_transcript = ""
        self._transcript_lock = threading.Lock()
        self._is_processing = False  # Internal flag to prevent concurrent operations

    # Thread-safe properties
    @property
    def current_transcript(self):
        """Thread-safe property for current transcript"""
        with self._transcript_lock:
            return self._current_transcript

    @current_transcript.setter
    def current_transcript(self, value):
        """Thread-safe setter for current transcript"""
        with self._transcript_lock:
            self._current_transcript = value

    @property
    def is_processing(self):
        return self._is_processing

    def _set_processing(self, state: bool):
        self._is_processing = state
        if state:
            self.processing_started.emit()
        else:
            self.processing_finished.emit()

    # --- Public Methods to be called by MainWindow ---

    def start_transcription(self, use_last_30s: bool = False):
        """Initiates transcription of the buffer (or last 30s)."""
        if self.is_processing:
            logger.warning("AnalysisController: Already processing.")
            return

        audio_data = None
        if use_last_30s:
            self.progress_update.emit("Getting last 30s of audio...")
            audio_data = self.recorder.get_last_n_seconds(30)
            if audio_data is None:
                self.transcription_complete.emit("Error: Not enough audio in buffer (last 30s).")
                return
        else:
            self.progress_update.emit("Getting audio buffer...")
            audio_data = self.recorder.save_buffer()  # Note: save_buffer also saves to disk
            if audio_data is None:
                self.transcription_complete.emit("Error: No audio in buffer.")
                return

        self._set_processing(True)
        self.progress_update.emit("Starting transcription...")

        # Run transcription in background thread
        worker = Worker(self._transcribe_task, audio_data, self.recorder.sample_rate)
        worker.signals.result.connect(self._handle_transcription_result)
        worker.signals.error.connect(self._handle_error)
        worker.signals.finished.connect(
            lambda: self._set_processing(False)
        )  # Mark as finished when worker done

        QThreadPool.globalInstance().start(worker)

    def start_analysis(
        self, prompt_template, title=None
    ):  # Keep title for potential future use/logging
        """
        Initiates analysis using a prompt. Transcribes first if necessary.
        Handles streaming internally via callbacks passed to the worker.
        """
        if self.is_processing:
            print("AnalysisController: Already processing.")
            return

        self._set_processing(True)

        # --- Logic to decide if transcription is needed ---
        if self.current_transcript:
            self.progress_update.emit("Using existing transcript for analysis...")
            # Directly start analysis task if transcript exists
            worker = Worker(self._analyze_task, self.current_transcript, prompt_template)
            # Connect signals for analysis worker (might differ slightly)
            worker.signals.result.connect(
                self._handle_analysis_result
            )  # Final result (if non-streaming)
            worker.signals.error.connect(self._handle_error)
            # Finished signal will just mark processing as done
            worker.signals.finished.connect(lambda: self._set_processing(False))
            # Stream/Progress updates are handled via callbacks within _analyze_task

            QThreadPool.globalInstance().start(worker)
        else:
            # Need to transcribe first, then analyze
            self.progress_update.emit("Transcription required for analysis...")

            # Determine if we need only 30s or full buffer for this analysis
            use_last_30s = prompt_template in [
                PRACTITIONER_INSIGHTS_STREAMING_PROMPT,
                ANSWER_QUESTION_PROMPT,
            ]

            audio_data = None
            if use_last_30s:
                audio_data = self.recorder.get_last_n_seconds(30)
                if audio_data is None:
                    self._handle_error(
                        ("ValueError", "Not enough audio (last 30s) in buffer to process", "")
                    )
                    self._set_processing(False)
                    return
            else:
                audio_data = self.recorder.save_buffer()
                if audio_data is None:
                    self._handle_error(("ValueError", "No audio in buffer to process", ""))
                    self._set_processing(False)
                    return

            # Start combined transcribe-then-analyze task
            worker = Worker(
                self._transcribe_and_analyze_task,
                audio_data,
                self.recorder.sample_rate,
                prompt_template,
            )
            # Connect signals for combined worker
            worker.signals.result.connect(self._handle_analysis_result)  # Final result of analysis
            worker.signals.error.connect(self._handle_error)
            worker.signals.finished.connect(lambda: self._set_processing(False))
            # Stream/Progress/Transcript updates are handled via callbacks within the task

            QThreadPool.globalInstance().start(worker)

    # --- Private Worker Methods (Executed in Background Threads) ---

    def _transcribe_task(self, audio_data, sample_rate):
        """Worker function for transcription only."""
        try:
            # Emit progress from the worker thread if needed (using signals)
            # worker_signals.progress.emit("Transcribing with Deepgram...") # Example
            text = self.api_client.transcribe_with_deepgram(audio_data, sample_rate)
            # Check if Deepgram returned an error string
            if text.startswith("Error:") or text.startswith("Transcription error:"):
                raise Exception(text)  # Raise exception to trigger error signal
            return text  # Return transcript on success
        except Exception as e:
            # Re-raise to be caught by the Worker's error handling
            print(f"Error during transcription task: {e}")
            raise e

    def _analyze_task(self, transcript, prompt_template):
        """Worker function for analysis only (can be streaming)."""
        try:
            self.progress_update.emit("Processing with Claude...")  # Emit progress

            def stream_callback(chunk):
                # This callback runs in the worker thread, emit signal
                self.stream_update.emit(chunk)

            # process_with_anthropic needs to accept the stream callback
            result = self.api_client.process_with_anthropic(
                transcript,
                prompt_template,
                stream=True,  # Assuming we always want streaming for analysis now
                callback=stream_callback,
            )
            # For streaming, the final 'result' might be the concatenated text,
            # or None if all data was sent via callback. We primarily rely on the stream_update signal.
            # Let's return a confirmation dict.
            return {
                "result": "Streaming complete."
            }  # Or return the full concatenated text if available
        except Exception as e:
            print(f"Error during analysis task: {e}")
            raise e  # Re-raise

    def _transcribe_and_analyze_task(self, audio_data, sample_rate, prompt_template):
        """Worker function for combined transcription and analysis."""
        try:
            # 1. Transcribe
            self.progress_update.emit("Transcribing audio...")
            transcript = self.api_client.transcribe_with_deepgram(audio_data, sample_rate)
            if transcript.startswith("Error:") or transcript.startswith("Transcription error:"):
                raise Exception(transcript)

            # Emit transcript *before* starting analysis
            # We need a way for the worker to signal this *intermediate* result.
            # Option 1: Add a specific signal to WorkerSignals (e.g., intermediate_result)
            # Option 2: Emit a progress update with a specific format UI can parse (less clean)
            # Option 3: Pass the controller instance or its signals directly to the worker (can be complex)
            # Let's emit the transcript via the main transcription_complete signal for now,
            # although this might slightly change the timing compared to the original.
            self.transcription_complete.emit(transcript)
            self.current_transcript = transcript  # Update controller state

            # 2. Analyze (using the _analyze_task logic)
            self.progress_update.emit("Processing transcript with Claude...")

            def stream_callback(chunk):
                self.stream_update.emit(chunk)

            result = self.api_client.process_with_anthropic(
                transcript, prompt_template, stream=True, callback=stream_callback
            )
            return {"result": "Streaming complete."}  # Or return full text
        except Exception as e:
            print(f"Error during transcribe_and_analyze task: {e}")
            raise e

    # --- Private Slots to Handle Worker Results/Errors (Executed in Main Thread) ---

    def _handle_transcription_result(self, transcript: str):
        """Handles successful transcription from worker."""
        self.current_transcript = transcript
        self.transcription_complete.emit(transcript)
        # Note: _set_processing(False) is handled by the finished signal connection

    def _handle_analysis_result(self, result: object):
        """Handles successful analysis from worker."""
        # 'result' here is the final return value from the worker task
        # For streaming, this might just be a confirmation message.
        # The actual data came via stream_update signals.
        if isinstance(result, dict):
            self.analysis_complete.emit(result)
        else:
            # Handle cases where analysis task returns something else unexpected
            self.analysis_complete.emit({"result": str(result) if result else "Analysis finished."})
        # Note: _set_processing(False) is handled by the finished signal connection

    def _handle_error(self, error_tuple):
        """Handles errors from worker threads."""
        exctype, value, trace = error_tuple
        error_message = f"Error: {value}\nTrace: {trace}"
        print(f"AnalysisController Error: {exctype} - {value}")
        # Decide whether to emit transcription_complete or analysis_complete with error
        # This distinction might be lost here, maybe emit a generic error signal?
        # For now, send to analysis_complete as it's the more general case.
        self.analysis_complete.emit({"error": str(value)})
        self._set_processing(False)  # Ensure processing is marked false on error

    def clear_transcript(self):
        """Clears the stored transcript."""
        self.current_transcript = ""
        print("AnalysisController: Transcript cleared.")
