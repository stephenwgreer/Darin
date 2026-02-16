import html
import io
import json
import re
import threading
import time
from dataclasses import dataclass
from pathlib import Path

from loguru import logger
from PyQt6.QtCore import Qt, pyqtSignal, pyqtSlot
from PyQt6.QtGui import QFont, QIcon, QPixmap
from PyQt6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QMessageBox,
    QSplitter,
    QVBoxLayout,
    QWidget,
)

import config
from api.client import ApiClient
from audio.recorder import ContinuousRecorder

# Import from new logic_templates file
from prompts.logic_templates import (
    FIRST_PRINCIPLES_PROMPT,
    HYPOTHESIS_DRIVEN_PROMPT,
    PROBLEM_SOLVING_PROMPT,
    REFRAMING_PROMPT,
    SCQA_PROMPT,
)

# Explicit imports from prompts.templates
from prompts.templates import (
    ANSWER_QUESTION_PROMPT,
    BRAINSTORM_PROMPT,
    COMPANY_FIT_PROMPT,
    FACT_CHECKING_PROMPT,
    FILL_IN_GAPS_PROMPT,
    FOLLOW_UP_QUESTIONS_PROMPT,
    MEETING_SUMMARY_PROMPT,
    PRACTITIONER_INSIGHTS_STREAMING_PROMPT,
    SENTIMENT_ANALYSIS_PROMPT,
    TOPIC_SUMMARY_PROMPT,
)
from ui.animated_label import AnimatedLabel
from ui.controls_panel import ControlsPanel
from ui.font_manager import FontManager
from ui.output_panel import OutputPanel
from ui import theme


class MainWindow(QMainWindow):
    # Custom signals
    recording_started = pyqtSignal()
    recording_stopped = pyqtSignal()
    transcription_complete = pyqtSignal(str)
    processing_complete = pyqtSignal(dict)
    progress_update = pyqtSignal(str)  # Signal for thread-safe progress updates
    stream_update = pyqtSignal(str)  # New signal for streaming updates

    def __init__(self):
        super().__init__()
        self.setWindowTitle("Darin Audio Assistant")
        self.setGeometry(100, 100, 1000, 700)

        # Load and apply stylesheet
        self._load_stylesheet()

        # Configure logging
        log_dir = Path("logs")
        log_dir.mkdir(exist_ok=True)
        logger.add(
            log_dir / "darin_{time:YYYY-MM-DD}.log",
            rotation="00:00",  # Rotate at midnight
            retention="7 days",
            level="INFO",
            format="{time:YYYY-MM-DD HH:mm:ss} | {level: <8} | {name}:{function}:{line} - {message}"
        )
        logger.info("Darin Audio Assistant initializing")

        # Load fonts
        FontManager.load_fonts()

        # Set application icon
        app_icon = QIcon("assets/Darin_ICON.png")
        self.setWindowIcon(app_icon)

        # Initialize components
        self.recorder = ContinuousRecorder(buffer_minutes=config.BUFFER_MINUTES)
        self.api_client = ApiClient()

        logger.info("Components initialized", buffer_minutes=config.BUFFER_MINUTES)

        # Threading locks for shared state protection
        self._transcript_lock = threading.Lock()
        self._processing_lock = threading.Lock()
        self._html_state_lock = threading.Lock()

        # Thread-safe shared state (private variables with property access)
        self._current_transcript = ""
        self._is_processing = False

        # HTML streaming state
        self._html_buffer = ""  # Buffer for accumulating HTML chunks
        self._buffer_io = io.StringIO()  # Efficient buffer for O(n) string building
        self._current_element = None  # Track the current HTML element being built
        self._element_stack = []  # Stack to track nested HTML elements
        self._is_first_update = True  # Track if this is the first stream update
        self._current_list_items = []  # Track list items for the current section
        self._template_type = None  # Track the current template type

        # Sentiment analysis specific state
        self._overall_sentiment_received = False

        # Setup UI
        self.setup_ui()

        # Connect signals to slots
        self.setup_connections()

    def _load_stylesheet(self):
        """Load and apply the QSS stylesheet for dark theme"""
        stylesheet_path = Path(__file__).parent / "styles.qss"

        if stylesheet_path.exists():
            logger.info("Loading stylesheet from styles.qss")
            with open(stylesheet_path, 'r') as f:
                self.setStyleSheet(f.read())
        else:
            # Fallback to inline QSS if file missing
            logger.warning("styles.qss not found, using inline fallback")
            self.setStyleSheet(f"""
                QMainWindow {{ background-color: {theme.COLORS.bg_primary}; }}
                QWidget {{ background-color: {theme.COLORS.bg_secondary}; color: {theme.COLORS.text_primary}; }}
                QPushButton {{
                    background-color: {theme.COLORS.bg_tertiary};
                    color: {theme.COLORS.text_primary};
                    border: 1px solid {theme.COLORS.border_primary};
                    border-radius: 4px;
                    padding: 8px 16px;
                }}
                QPushButton:hover {{
                    background-color: {theme.COLORS.bg_hover};
                    border-color: {theme.COLORS.accent_primary};
                }}
            """)

    # Thread-safe properties for shared state
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
        """Thread-safe property for processing state"""
        with self._processing_lock:
            return self._is_processing

    @is_processing.setter
    def is_processing(self, value):
        """Thread-safe setter for processing state"""
        with self._processing_lock:
            self._is_processing = value

    def _extract_html_items(self, text: str, pattern: str = r'<li[^>]*>(.*?)</li>') -> list[str]:
        """
        Shared HTML stream parsing logic for all template handlers.

        Efficiently extracts HTML list items from streaming text using io.StringIO
        for O(n) performance instead of O(n²) string concatenation.

        Thread Safety:
        - All buffer operations happen under self._html_state_lock (caller responsibility)
        - This method assumes the lock is already held by the caller

        Performance (fixes BUG-2026-02-09-005):
        - Uses io.StringIO for O(1) amortized append operations
        - Collects all extractions before buffer modification

        Security Note:
        - Extracts HTML from LLM responses without sanitization
        - Accepted risk: LLM output from Anthropic API is trusted source
        - Mitigation: Use only official Anthropic API, validate API keys at startup
        - Future enhancement: Add HTML sanitization library (e.g., bleach) for defense-in-depth
        - Single buffer reconstruction instead of repeated string slicing

        Args:
            text: New chunk of HTML text from streaming response
            pattern: Regex pattern for extraction (default: any <li> tag)

        Returns:
            List of extracted HTML items as strings

        Example:
            # In a handler (with lock already held):
            items = self._extract_html_items(text, r'<li class="question">(.*?)</li>')
            for item in items:
                # Format and append to UI
                self.output_panel.append_to_dynamic_content(item)
        """
        # Append new text to buffer (O(1) amortized)
        # Seek to end before writing to ensure append behavior
        self._buffer_io.seek(0, 2)
        self._buffer_io.write(text)
        buffer_content = self._buffer_io.getvalue()

        # Extract all matches
        extracted_items = []
        matches = list(re.finditer(pattern, buffer_content, re.DOTALL))

        if not matches:
            return extracted_items

        # Collect all extracted items and their positions
        removals = []
        for match in matches:
            extracted_items.append(match.group(0))  # Full match including tags
            removals.append((match.start(), match.end()))

        # Remove extracted portions in reverse order (preserves positions)
        for start, end in reversed(removals):
            buffer_content = buffer_content[:start] + buffer_content[end:]

        # Reset buffer with remaining content
        # Create fresh StringIO to ensure clean state
        self._buffer_io = io.StringIO(buffer_content)

        return extracted_items

    def setup_ui(self):
        ########################
        # Main widget and layout
        ########################
        main_widget = QWidget()
        self.setCentralWidget(main_widget)
        main_layout = QVBoxLayout(main_widget)
        main_layout.setContentsMargins(10, 10, 10, 10)  # Add some padding around the edges
        main_layout.setSpacing(10)  # Space between elements

        ########################
        # Header section
        ########################
        header_widget = QWidget()
        header_layout = QHBoxLayout(header_widget)
        header_layout.setContentsMargins(0, 0, 0, 0)

        # Add logo on left
        logo_label = QLabel()
        small_logo = QPixmap("assets/Darin_Round.png")
        small_logo = small_logo.scaled(60, 60, Qt.AspectRatioMode.KeepAspectRatio)
        logo_label.setPixmap(small_logo)
        header_layout.addWidget(logo_label)

        # Add spacing between logo and title
        header_layout.addSpacing(10)

        # App title with typing animation
        app_title = AnimatedLabel("Welcome to Darin, your intern")
        app_title.setFont(FontManager.get_font(18, QFont.Weight.Bold))
        header_layout.addWidget(app_title)

        header_layout.addStretch()

        main_layout.addWidget(header_widget)

        ########################
        # Content section with splitter
        ########################
        self.content_splitter = QSplitter(Qt.Orientation.Horizontal)
        self.content_splitter.setHandleWidth(2)  # Splitter handle visibility

        # Left panel (controls)
        self.controls_panel = ControlsPanel()
        self.controls_panel.setMaximumWidth(300)  # Limit the width of controls panel

        # Right panel (output)
        self.output_panel = OutputPanel()

        # Add panels to splitter
        self.content_splitter.addWidget(self.controls_panel)
        self.content_splitter.addWidget(self.output_panel)

        # Set the proportions (25% controls, 75% output)
        self.content_splitter.setStretchFactor(0, 1)  # Controls take 1 part
        self.content_splitter.setStretchFactor(1, 3)  # Output takes 3 parts

        # Set initial sizes
        total_width = self.width()
        self.content_splitter.setSizes([int(total_width * 0.25), int(total_width * 0.75)])

        main_layout.addWidget(self.content_splitter)

        # Footer
        footer = QLabel("© 2025 Darin Listening Assistant")
        footer.setObjectName("footerLabel")
        footer.setAlignment(Qt.AlignmentFlag.AlignCenter)
        main_layout.addWidget(footer)

    def setup_connections(self):
        # Connect control panel signals
        self.controls_panel.record_clicked.connect(self.toggle_recording)
        self.controls_panel.transcribe_clicked.connect(self.transcribe_buffer)
        self.controls_panel.transcribe_last_30_clicked.connect(self.transcribe_last_30_seconds)
        self.controls_panel.clear_output_clicked.connect(self.clear_output)

        # Original prompt buttons
        self.controls_panel.topics_clicked.connect(
            lambda: self.run_prompt_with_auto_transcribe(TOPIC_SUMMARY_PROMPT, title="Key Topics")
        )
        self.controls_panel.insights_clicked.connect(
            lambda: self.run_prompt_with_auto_transcribe(
                PRACTITIONER_INSIGHTS_STREAMING_PROMPT, title="Banking Practitioner Insights"
            )
        )
        self.controls_panel.summary_clicked.connect(
            lambda: self.run_prompt_with_auto_transcribe(
                MEETING_SUMMARY_PROMPT, title="Meeting Summary"
            )
        )
        self.controls_panel.questions_clicked.connect(
            lambda: self.run_prompt_with_auto_transcribe(
                FOLLOW_UP_QUESTIONS_PROMPT, title="Follow-up Questions"
            )
        )
        self.controls_panel.sentiment_clicked.connect(
            lambda: self.run_prompt_with_auto_transcribe(
                SENTIMENT_ANALYSIS_PROMPT, title="Sentiment Analysis"
            )
        )

        # New prompt buttons
        self.controls_panel.fill_gaps_clicked.connect(
            lambda: self.run_prompt_with_auto_transcribe(
                FILL_IN_GAPS_PROMPT, title="Gaps in Reasoning"
            )
        )
        self.controls_panel.brainstorm_clicked.connect(
            lambda: self.run_prompt_with_auto_transcribe(
                BRAINSTORM_PROMPT, title="Brainstorm Questions"
            )
        )
        self.controls_panel.company_fit_clicked.connect(
            lambda: self.run_prompt_with_auto_transcribe(
                COMPANY_FIT_PROMPT, title="SAS Viya Alignment"
            )
        )
        self.controls_panel.fact_check_clicked.connect(
            lambda: self.run_prompt_with_auto_transcribe(
                FACT_CHECKING_PROMPT, title="Fact Check Analysis"
            )
        )
        self.controls_panel.answer_question_clicked.connect(
            lambda: self.run_prompt_with_auto_transcribe(
                ANSWER_QUESTION_PROMPT, title="Answer Question"
            )
        )
        self.controls_panel.problem_solving_clicked.connect(
            lambda: self.run_prompt_with_auto_transcribe(
                PROBLEM_SOLVING_PROMPT, title="Issue Tree Logic"
            )
        )
        self.controls_panel.scqa_clicked.connect(
            lambda: self.run_prompt_with_auto_transcribe(SCQA_PROMPT, title="SCQA Framework")
        )
        self.controls_panel.hypothesis_driven_clicked.connect(
            lambda: self.run_prompt_with_auto_transcribe(
                HYPOTHESIS_DRIVEN_PROMPT, title="Hypothesis Thinking"
            )
        )
        self.controls_panel.first_principles_clicked.connect(
            lambda: self.run_prompt_with_auto_transcribe(
                FIRST_PRINCIPLES_PROMPT, title="First Principles"
            )
        )
        self.controls_panel.reframing_clicked.connect(
            lambda: self.run_prompt_with_auto_transcribe(REFRAMING_PROMPT, title="Reframing")
        )

        # Connect custom signals to slots
        self.recording_started.connect(self.on_recording_started)
        self.recording_stopped.connect(self.on_recording_stopped)
        self.transcription_complete.connect(self.on_transcription_complete)
        self.processing_complete.connect(self.on_processing_complete)
        self.progress_update.connect(self.on_progress_update)
        self.stream_update.connect(self.on_stream_update)

    def toggle_recording(self):
        if not self.recorder.is_recording:
            # Start recording
            logger.info("Starting audio recording")
            if self.recorder.start_recording():
                logger.info("Audio recording started successfully")
                self.recording_started.emit()
                # Update UI to show recording state
                self.controls_panel.set_recording_active(True)
            else:
                logger.error("Failed to start audio recording")
        else:
            # Stop recording
            logger.info("Stopping audio recording")
            if self.recorder.stop_recording():
                logger.info("Audio recording stopped successfully")
                self.recording_stopped.emit()
                # Update UI to show stopped state
                self.controls_panel.set_recording_active(False)
            else:
                logger.error("Failed to stop audio recording")

    def transcribe_buffer(self):
        """Transcribe the current audio buffer"""
        logger.info("Transcribe buffer requested")
        # Disable button to prevent multiple clicks
        self.controls_panel.transcribe_button.setEnabled(False)
        self.controls_panel.transcribe_button.setText("Transcribing...")

        # Get audio data from buffer
        audio_data = self.recorder.save_buffer()

        if audio_data is None:
            logger.warning("Transcription failed: No audio in buffer")
            self.controls_panel.transcribe_button.setText("Transcribe Buffer")
            self.controls_panel.transcribe_button.setEnabled(True)
            QMessageBox.warning(self, "Transcription Error", "No audio in buffer to transcribe")
            return

        logger.info("Starting transcription from buffer", buffer_size_bytes=len(audio_data), sample_rate=self.recorder.sample_rate)
        # Start transcription in a separate thread
        threading.Thread(
            target=self._transcribe_thread, args=(audio_data, self.recorder.sample_rate)
        ).start()

    def _transcribe_thread(self, audio_data, sample_rate):
        """Background thread for transcription - emits signal, doesn't write directly"""
        start_time = time.perf_counter()
        logger.info("Transcription thread started", buffer_size_bytes=len(audio_data), sample_rate=sample_rate)
        try:
            text = self.api_client.transcribe_with_deepgram(audio_data, sample_rate)
            duration_ms = (time.perf_counter() - start_time) * 1000
            logger.info("Transcription complete", transcript_length=len(text), duration_ms=f"{duration_ms:.2f}")
            # Emit signal to update transcript in GUI thread (thread-safe)
            self.transcription_complete.emit(text)
        except Exception as e:
            duration_ms = (time.perf_counter() - start_time) * 1000
            logger.error("Transcription failed", error=str(e), duration_ms=f"{duration_ms:.2f}", exc_info=True)
            self.transcription_complete.emit(f"Transcription error: {str(e)}")

    def run_prompt_with_auto_transcribe(self, prompt_template=None, title=None):
        """Auto transcribe and then run a specific prompt"""
        logger.info("Prompt with auto-transcribe requested", title=title)
        # Atomic check-and-set for processing state
        with self._processing_lock:
            if self._is_processing:
                logger.warning("Prompt request rejected: already processing")
                return
            self._is_processing = True

        # Disable all prompt buttons
        self.controls_panel.set_prompt_buttons_enabled(False)

        # Clear output before running new prompt
        self.clear_output()

        # Set the output panel title if provided
        if title:
            self.output_panel.set_title(title)

        # Update output to show progress
        self.output_panel.set_output("Capturing audio and transcribing...")

        # If we already have a transcript, use it directly
        # Read atomically to avoid race condition
        with self._transcript_lock:
            has_transcript = bool(self._current_transcript)
            transcript_copy = self._current_transcript if has_transcript else None

        if has_transcript:
            self._run_specific_prompt(transcript_copy, prompt_template)
            return

        # Otherwise get audio data
        audio_data = None  # Initialize audio_data
        # For specific prompts, only use last 30s if no transcript exists
        use_last_30s = prompt_template in [
            PRACTITIONER_INSIGHTS_STREAMING_PROMPT,
            ANSWER_QUESTION_PROMPT,
        ]

        if use_last_30s and not self.current_transcript:
            audio_data = self.recorder.get_last_n_seconds(30)
            if audio_data is None:
                logger.warning("Processing failed: Not enough audio in buffer (last 30s)")
                QMessageBox.warning(
                    self, "Processing Error", "Not enough audio (last 30s) in buffer to process"
                )
                self.controls_panel.set_prompt_buttons_enabled(True)
                self.is_processing = False  # Property handles locking
                return  # Return early if 30s failed

        # If we didn't get 30s audio (either not applicable or it succeeded but we proceed),
        # get the full buffer instead.
        if audio_data is None:  # This means we need the full buffer
            audio_data = self.recorder.save_buffer()
            if audio_data is None:
                # Check if getting the full buffer failed
                logger.warning("Processing failed: No audio in buffer")
                QMessageBox.warning(self, "Processing Error", "No audio in buffer to process")
                self.controls_panel.set_prompt_buttons_enabled(True)
                self.is_processing = False  # Property handles locking
                return  # Return early if full buffer failed

        # We should now have valid audio_data (either 30s or full buffer)
        # Start transcription and processing in a separate thread
        threading.Thread(
            target=self._transcribe_and_process_thread,
            args=(audio_data, self.recorder.sample_rate, prompt_template),
        ).start()

    def _transcribe_and_process_thread(self, audio_data, sample_rate, prompt_template):
        """Background thread for transcription followed by processing with a specific prompt"""
        start_time = time.perf_counter()
        logger.info("Transcribe and process thread started", buffer_size_bytes=len(audio_data), sample_rate=sample_rate)
        try:
            # First transcribe
            self.progress_update.emit("Transcribing audio...")
            text = self.api_client.transcribe_with_deepgram(audio_data, sample_rate)
            transcribe_duration_ms = (time.perf_counter() - start_time) * 1000
            logger.info("Transcription phase complete", transcript_length=len(text), duration_ms=f"{transcribe_duration_ms:.2f}")

            # Update UI with transcript via signal (thread-safe)
            # The slot handler will set self.current_transcript
            self.transcription_complete.emit(text)

            # Then process with the specific prompt
            self._run_specific_prompt(text, prompt_template)
            total_duration_ms = (time.perf_counter() - start_time) * 1000
            logger.info("Transcribe and process complete", total_duration_ms=f"{total_duration_ms:.2f}")
        except Exception as e:
            duration_ms = (time.perf_counter() - start_time) * 1000
            logger.error("Transcribe and process failed", error=str(e), duration_ms=f"{duration_ms:.2f}", exc_info=True)
            self.processing_complete.emit({"error": str(e)})
        finally:
            # Emit signal to update processing state in GUI thread (thread-safe)
            # We need to emit processing_complete which will handle this
            pass  # is_processing will be set to False by on_processing_complete slot

    def _run_specific_prompt(self, transcript, prompt_template):
        """Process transcript with a specific prompt template"""
        start_time = time.perf_counter()
        logger.info("Starting LLM processing", transcript_length=len(transcript), template_type=str(prompt_template)[:50])
        try:
            # Update output to show progress
            self.progress_update.emit("Processing with Claude...")

            # Set up the static template based on the prompt type
            template_type = self._setup_static_template(prompt_template)
            logger.info("Template set up", template_type=template_type)

            # Reset HTML streaming state for new dynamic content
            with self._html_state_lock:
                self._html_buffer = ""
                self._current_element = None
                self._element_stack = []
                self._is_first_update = False  # Already set up the template
                self._current_list_items = []
                self._template_type = template_type  # Store the template type for use in streaming

            def handle_stream(text):
                """Callback to handle streaming text"""
                self.stream_update.emit(text)

            # Process with the template
            result = self.api_client.process_with_anthropic(
                transcript, prompt_template, stream=True, callback=handle_stream
            )
            duration_ms = (time.perf_counter() - start_time) * 1000
            logger.info("LLM processing complete", template_type=template_type, duration_ms=f"{duration_ms:.2f}", result_length=len(str(result)))

            # Final update with complete response
            self.processing_complete.emit({"result": result})
        except Exception as e:
            duration_ms = (time.perf_counter() - start_time) * 1000
            logger.error("LLM processing failed", template_type=str(prompt_template)[:50], error=str(e), duration_ms=f"{duration_ms:.2f}", exc_info=True)
            self.processing_complete.emit({"error": str(e)})

    def _setup_static_template(self, prompt_template):
        """Set up a static template based on the prompt type"""
        if prompt_template == FOLLOW_UP_QUESTIONS_PROMPT:
            # Static template for follow-up questions (matches sentiment analysis style)
            static_template = """
            <div class="insight-block" style="margin-top: 0; padding-top: 10px;">
                 <ul class="insight-list" id="dynamic-content" style="list-style-type: disc; margin-top: 0; padding-left: 25px;">
                    <!-- Dynamic list items will be inserted here -->
                 </ul>
            </div>
            """
            self.output_panel.set_output(static_template)
            return "follow-up-questions"
        elif prompt_template == MEETING_SUMMARY_PROMPT:
            # Static template for meeting summary (matches insight block style)
            static_template = """
            <div class="insight-block" style="margin-top: 0; padding-top: 10px;">
                 <ul class="insight-list" id="dynamic-content" style="list-style-type: disc; margin-top: 0; padding-left: 25px;">
                    <!-- Dynamic list items will be inserted here -->
                 </ul>
            </div>
            """
            self.output_panel.set_output(static_template)
            return "meeting-summary"
        elif prompt_template == TOPIC_SUMMARY_PROMPT:
            # Static template for topic summary (matches insight block style)
            static_template = """
            <div class="insight-block" style="margin-top: 0; padding-top: 10px;">
                 <ul class="insight-list" id="dynamic-content" style="list-style-type: disc; margin-top: 0; padding-left: 25px;">
                    <!-- Dynamic list items will be inserted here -->
                 </ul>
            </div>
            """
            self.output_panel.set_output(static_template)
            return "topic-summary"
        elif prompt_template == SENTIMENT_ANALYSIS_PROMPT:
            # Static template for sentiment analysis
            static_template = """
            <div class="insight-block" style="margin-top: 0; padding-top: 10px;">
                <h3 style="font-weight: bold;">Overall Sentiment</h3>
                <p id="overall-sentiment-value" style="margin-left: 10px;"></p> 
                <h3 style="font-weight: bold; margin-top: 20px;">Key Emotional Moments</h3>
                <ul class="insight-list" id="dynamic-content" style="list-style-type: disc; margin-top: 0; padding-left: 25px;">
                    <!-- Dynamic list items will be inserted here -->
                </ul>
            </div>
            """
            self.output_panel.set_output(static_template)
            return "sentiment-analysis"
        elif prompt_template == PRACTITIONER_INSIGHTS_STREAMING_PROMPT:
            # Static template for practitioner insights (matches insight block style)
            static_template = """
            <div class="insight-block" style="margin-top: 0; padding-top: 10px;">
                 <ul class="insight-list" id="dynamic-content" style="list-style-type: disc; margin-top: 0; padding-left: 25px;">
                    <!-- Dynamic list items will be inserted here -->
                 </ul>
            </div>
            """
            self.output_panel.set_output(static_template)
            return "practitioner-insights"
        elif prompt_template == FILL_IN_GAPS_PROMPT:
            # Static template for Fill Gaps in Reasoning
            static_template = """
            <div class="insight-block" style="margin-top: 0; padding-top: 10px;">
                <h3 style="font-weight: bold;">CORE THINKING</h3>
                <ul id="core-thinking-list" style="list-style-type: disc; margin-top: 0; padding-left: 25px;">
                    <!-- Core thinking item will be inserted here -->
                </ul>
                <h3 style="font-weight: bold; margin-top: 20px;">GAPS</h3>
                <ul id="gaps-list" style="list-style-type: disc; margin-top: 0; padding-left: 25px;">
                    <!-- Gap items will be inserted here -->
                </ul>
                <h3 style="font-weight: bold; margin-top: 20px;">RECOMMENDATIONS</h3>
                <ul id="recommendations-list" style="list-style-type: disc; margin-top: 0; padding-left: 25px;">
                    <!-- Recommendation items will be inserted here -->
                </ul>
            </div>
            """
            self.output_panel.set_output(static_template)
            return "fill-gaps"
        elif prompt_template == BRAINSTORM_PROMPT:
            # Static template for Brainstorm Questions
            static_template = """
            <div class="insight-block" style="margin-top: 0; padding-top: 10px;">
                <h3 style="font-weight: bold;">CHALLENGE QUESTIONS</h3>
                <ul id="challenge-questions-list" style="list-style-type: disc; margin-top: 0; padding-left: 25px;">
                    <!-- Challenge question items will be inserted here -->
                </ul>
                <h3 style="font-weight: bold; margin-top: 20px;">ALTERNATIVE FRAMES</h3>
                <ul id="alternative-frames-list" style="list-style-type: disc; margin-top: 0; padding-left: 25px;">
                    <!-- Alternative frame items will be inserted here -->
                </ul>
                <h3 style="font-weight: bold; margin-top: 20px;">PROVOCATIVE IDEAS</h3>
                <ul id="provocative-ideas-list" style="list-style-type: disc; margin-top: 0; padding-left: 25px;">
                    <!-- Provocative idea items will be inserted here -->
                </ul>
            </div>
            """
            self.output_panel.set_output(static_template)
            return "brainstorm"
        elif prompt_template == COMPANY_FIT_PROMPT:
            # Static template for Company Fit / SAS Viya Alignment
            static_template = """
            <div class="insight-block" style="margin-top: 0; padding-top: 10px;">
                <h3 style="font-weight: bold;">KEY TOPICS</h3>
                <ul id="key-topics-list" style="list-style-type: disc; margin-top: 0; padding-left: 25px;">
                    <!-- Key topic items will be inserted here -->
                </ul>
                <h3 style="font-weight: bold; margin-top: 20px;">SAS VIYA CONNECTIONS</h3>
                <ul id="viya-connections-list" style="list-style-type: disc; margin-top: 0; padding-left: 25px;">
                    <!-- Viya connection items will be inserted here -->
                </ul>
                <h3 style="font-weight: bold; margin-top: 20px;">MISSING CONSIDERATIONS</h3>
                <ul id="missing-considerations-list" style="list-style-type: disc; margin-top: 0; padding-left: 25px;">
                    <!-- Missing consideration items will be inserted here -->
                </ul>
            </div>
            """
            self.output_panel.set_output(static_template)
            return "company-fit"
        elif prompt_template == FACT_CHECKING_PROMPT:
            # Static template for Fact Checking
            static_template = """
            <div class="insight-block" style="margin-top: 0; padding-top: 10px;">
                <h3 style="font-weight: bold;">Fact Check Analysis</h3>
                <ul id="fact-check-list" style="list-style-type: none; margin-top: 0; padding-left: 0;"> 
                    <!-- Fact check items will be inserted here -->
                </ul>
            </div>
            """
            self.output_panel.set_output(static_template)
            return "fact-check"
        elif prompt_template == ANSWER_QUESTION_PROMPT:
            # Static template for Answer Question with sections
            static_template = """
            <div class="insight-block" style="margin-top: 0; padding-top: 10px;">
                <h3 style="font-weight: bold;">ANSWER</h3>
                <ul id="answer-list" style="list-style-type: disc; margin-top: 0; padding-left: 25px;">
                    <!-- Answer items will be inserted here -->
                </ul>
                <h3 style="font-weight: bold; margin-top: 20px;">RATIONALE</h3>
                <ul id="rationale-list" style="list-style-type: disc; margin-top: 0; padding-left: 25px;">
                    <!-- Rationale items will be inserted here -->
                </ul>
                <h3 style="font-weight: bold; margin-top: 20px;">EXAMPLES</h3>
                <ul id="examples-list" style="list-style-type: disc; margin-top: 0; padding-left: 25px;">
                    <!-- Example items will be inserted here -->
                </ul>
            </div>
            """
            self.output_panel.set_output(static_template)
            return "answer-question"
        elif prompt_template == PROBLEM_SOLVING_PROMPT:
            # Static template for Problem Solving / Issue Tree Logic
            static_template = """
            <div class="insight-block" style="margin-top: 0; padding-top: 10px;">
                <h3 style="font-weight: bold;">CORE PROBLEM/OBJECTIVE</h3>
                <ul id="core-problem-list" style="list-style-type: none; margin-top: 0; padding-left: 0;">
                    <!-- Core problem item -->
                </ul>
                <h3 style="font-weight: bold; margin-top: 20px;">LOGIC TREE COMPONENTS</h3>
                <ul id="logic-tree-list" style="list-style-type: none; margin-top: 0; padding-left: 0;">
                    <!-- Logic tree components -->
                </ul>
                <h3 style="font-weight: bold; margin-top: 20px;">EVALUATION</h3>
                <ul id="evaluation-list" style="list-style-type: disc; margin-top: 0; padding-left: 25px;">
                    <!-- Evaluation items (MECE, Assumptions, Logic, Data) -->
                </ul>
                <h3 style="font-weight: bold; margin-top: 20px;">CHALLENGE & REFRAME</h3>
                <ul id="challenge-list" style="list-style-type: disc; margin-top: 0; padding-left: 25px;">
                    <!-- Challenge items (Weakness, Questions, Reframe) -->
                </ul>
            </div>
            """
            self.output_panel.set_output(static_template)
            return "problem-solving"
        elif prompt_template == SCQA_PROMPT:
            # Static template for SCQA Framework
            static_template = """
            <div class="insight-block" style="margin-top: 0; padding-top: 10px;">
                <h3 style="font-weight: bold;">SITUATION</h3>
                <ul id="scqa-situation-list" style="list-style-type: none; margin-top: 0; padding-left: 0;">
                    <!-- Situation items -->
                </ul>
                <h3 style="font-weight: bold; margin-top: 20px;">COMPLICATION</h3>
                <ul id="scqa-complication-list" style="list-style-type: none; margin-top: 0; padding-left: 0;">
                    <!-- Complication items -->
                </ul>
                <h3 style="font-weight: bold; margin-top: 20px;">QUESTION</h3>
                <ul id="scqa-question-list" style="list-style-type: none; margin-top: 0; padding-left: 0;">
                    <!-- Question item -->
                </ul>
                <h3 style="font-weight: bold; margin-top: 20px;">ANSWER</h3>
                <ul id="scqa-answer-list" style="list-style-type: none; margin-top: 0; padding-left: 0;">
                    <!-- Answer items -->
                </ul>
                <h3 style="font-weight: bold; margin-top: 20px;">CRITICAL ASSESSMENT</h3>
                <ul id="scqa-assessment-list" style="list-style-type: disc; margin-top: 0; padding-left: 25px;">
                    <!-- Assessment items -->
                </ul>
                <h3 style="font-weight: bold; margin-top: 20px;">IMPLEMENTATION ROADMAP</h3>
                <ul id="scqa-roadmap-list" style="list-style-type: disc; margin-top: 0; padding-left: 25px;">
                    <!-- Roadmap items -->
                </ul>
            </div>
            """
            self.output_panel.set_output(static_template)
            return "scqa"
        elif prompt_template == HYPOTHESIS_DRIVEN_PROMPT:
            # Static template for Hypothesis Driven Thinking
            static_template = """
            <div class="insight-block" style="margin-top: 0; padding-top: 10px;">
                <h3 style="font-weight: bold;">PROBLEM STATEMENT</h3>
                <ul id="hypothesis-problem-list" style="list-style-type: none; margin-top: 0; padding-left: 0;">
                    <!-- Problem statement item -->
                </ul>
                <h3 style="font-weight: bold; margin-top: 20px;">HYPOTHESES</h3>
                <ul id="hypothesis-hypothesis-list" style="list-style-type: disc; margin-top: 0; padding-left: 25px;">
                    <!-- Hypothesis items -->
                </ul>
                <h3 style="font-weight: bold; margin-top: 20px;">EVIDENCE ANALYSIS</h3>
                <ul id="hypothesis-evidence-list" style="list-style-type: none; margin-top: 0; padding-left: 0;">
                    <!-- Evidence items (Support, Contradict, Missing) -->
                </ul>
                <h3 style="font-weight: bold; margin-top: 20px;">HYPOTHESIS PRIORITIZATION</h3>
                <ul id="hypothesis-priority-list" style="list-style-type: none; margin-top: 0; padding-left: 0;">
                    <!-- Priority items -->
                </ul>
                <h3 style="font-weight: bold; margin-top: 20px;">TESTING PLAN</h3>
                <ul id="hypothesis-testing-list" style="list-style-type: disc; margin-top: 0; padding-left: 25px;">
                    <!-- Testing plan items -->
                </ul>
                <h3 style="font-weight: bold; margin-top: 20px;">DECISION FRAMEWORK</h3>
                <ul id="hypothesis-decision-list" style="list-style-type: disc; margin-top: 0; padding-left: 25px;">
                    <!-- Decision framework items -->
                </ul>
                <h3 style="font-weight: bold; margin-top: 20px;">TRANSCRIPT ASSESSMENT</h3>
                <ul id="hypothesis-assessment-list" style="list-style-type: disc; margin-top: 0; padding-left: 25px;">
                    <!-- Assessment items -->
                </ul>
            </div>
            """
            self.output_panel.set_output(static_template)
            return "hypothesis-driven"
        elif prompt_template == FIRST_PRINCIPLES_PROMPT:
            # Static template for First Principles Thinking
            static_template = """
            <div class="insight-block" style="margin-top: 0; padding-top: 10px;">
                <h3 style="font-weight: bold;">CONVENTIONAL THINKING</h3>
                <ul id="fp-conventional-list" style="list-style-type: disc; margin-top: 0; padding-left: 25px;">
                    <!-- Conventional thinking items -->
                </ul>
                <h3 style="font-weight: bold; margin-top: 20px;">FUNDAMENTALS</h3>
                <ul id="fp-fundamental-list" style="list-style-type: disc; margin-top: 0; padding-left: 25px;">
                    <!-- Fundamental truths -->
                </ul>
                <h3 style="font-weight: bold; margin-top: 20px;">ASSUMPTION CHALLENGES</h3>
                <ul id="fp-assumption-list" style="list-style-type: none; margin-top: 0; padding-left: 0;">
                    <!-- Assumption challenges -->
                </ul>
                <h3 style="font-weight: bold; margin-top: 20px;">REBUILD FROM FIRST PRINCIPLES</h3>
                <ul id="fp-rebuild-list" style="list-style-type: disc; margin-top: 0; padding-left: 25px;">
                    <!-- Rebuilt approaches -->
                </ul>
                <h3 style="font-weight: bold; margin-top: 20px;">NOVEL INSIGHTS</h3>
                <ul id="fp-insight-list" style="list-style-type: disc; margin-top: 0; padding-left: 25px;">
                    <!-- Novel insights -->
                </ul>
                <h3 style="font-weight: bold; margin-top: 20px;">IMPLEMENTATION FRAMEWORK</h3>
                <ul id="fp-implementation-list" style="list-style-type: disc; margin-top: 0; padding-left: 25px;">
                    <!-- Implementation steps -->
                </ul>
                <h3 style="font-weight: bold; margin-top: 20px;">METACOGNITIVE ASSESSMENT</h3>
                <ul id="fp-metacognitive-list" style="list-style-type: disc; margin-top: 0; padding-left: 25px;">
                    <!-- Metacognitive points -->
                </ul>
            </div>
            """
            self.output_panel.set_output(static_template)
            return "first-principles"
        elif prompt_template == REFRAMING_PROMPT:
            # Static template for Reframing
            static_template = """
            <div class="insight-block" style="margin-top: 0; padding-top: 10px;">
                <h3 style="font-weight: bold;">REFRAMED STATEMENT</h3>
                <ul id="reframing-statement-list" style="list-style-type: none; margin-top: 0; padding-left: 0;">
                    <!-- Reframed statement item -->
                </ul>
                <h3 style="font-weight: bold; margin-top: 20px;">SUPPORTING POINTS</h3>
                <ul id="reframing-point-list" style="list-style-type: disc; margin-top: 0; padding-left: 25px;">
                    <!-- Supporting point items -->
                </ul>
            </div>
            """
            self.output_panel.set_output(static_template)
            return "reframing"
        else:
            # Generic template for other prompt types
            static_template = """
            <div class="topic-section">
                <h2 class="topic-title">Results</h2>
                <div class="insight-block" id="dynamic-content">
                    <!-- Dynamic content will be inserted here -->
                </div>
            </div>
            """
            self.output_panel.set_output(static_template)
            return "generic"

    # Slots for custom signals
    @pyqtSlot()
    def on_recording_started(self):
        # Enable prompt buttons when recording starts
        self.controls_panel.set_prompt_buttons_enabled(True)

    @pyqtSlot()
    def on_recording_stopped(self):
        # Keep buttons enabled even when recording stops
        # as long as we have buffer data
        if self.recorder.get_buffer_seconds() > 0:
            self.controls_panel.transcribe_button.setEnabled(True)
            self.controls_panel.set_prompt_buttons_enabled(True)

    @pyqtSlot(str)
    def on_transcription_complete(self, text):
        logger.info("Transcription complete signal received", text_length=len(text))
        # Update transcript in GUI thread (thread-safe via property)
        self.current_transcript = text

        # Display transcript in the output panel (sanitize to prevent XSS)
        self.output_panel.set_output(f"<div class='transcript-text'>{html.escape(text)}</div>")

        # Reset both transcribe buttons
        self.controls_panel.transcribe_button.setText("Transcribe Buffer")
        self.controls_panel.transcribe_button.setEnabled(True)
        self.controls_panel.transcribe_last_30_button.setText("Transcribe Last 30s")
        self.controls_panel.transcribe_last_30_button.setEnabled(True)

        # Enable all prompt buttons when we have a transcript
        self.controls_panel.set_prompt_buttons_enabled(True)

    @pyqtSlot(dict)
    def on_processing_complete(self, result):
        logger.info("Processing complete signal received", has_error="error" in result, has_result="result" in result)
        # Reset processing state in GUI thread (thread-safe)
        self.is_processing = False

        if "error" in result:
            logger.error("Processing completed with error", error=result["error"])
            # Show error using template
            self.output_panel.set_error(result["error"])
        elif "result" in result:
            # For specific streaming types, we don't want to overwrite our formatted content
            # as the final output might be raw text without the template structure.
            if not hasattr(self, "_template_type") or self._template_type not in [
                "follow-up-questions",
                "sentiment-analysis",
                "meeting-summary",
                "practitioner-insights",
                "topic-summary",
                "fill-gaps",
                "brainstorm",
                "company-fit",
                "fact-check",
                "answer-question",
                "problem-solving",
                "scqa",
                "hypothesis-driven",
                "first-principles",
                "reframing",
            ]:
                # Show result text for other non-streaming or differently handled types
                self.output_panel.set_output(result["result"])
        else:
            # Format the result as a topic section
            content = json.dumps(result, indent=2)
            # Escape JSON content to prevent XSS if result contains malicious strings
            self.output_panel.set_output(
                create_topic_section("Processing Results", f"<pre>{html.escape(content)}</pre>")
            )

        # Re-enable prompt buttons
        self.controls_panel.set_prompt_buttons_enabled(True)

    def _process_html_chunk(self, chunk):
        """
        Process a chunk of HTML text and return complete elements if found.

        Fixes O(n²) bug by using io.StringIO for efficient buffer management.
        """
        with self._html_state_lock:
            # Use shared buffer_io for O(n) append (fixes BUG-2026-02-09-005)
            self._buffer_io.write(chunk)
            self._html_buffer = self._buffer_io.getvalue()

            # Look for complete HTML elements
            while True:
                # If we don't have a current element, look for the start of one
                if not self._current_element:
                    # Find the next opening tag for a topic section
                    start_idx = self._html_buffer.find('<div class="topic-section">')
                    if start_idx == -1:
                        # If no topic section, look for individual list items
                        item_start = self._html_buffer.find('<li class="insight-item">')
                        if item_start != -1:
                            item_end = self._html_buffer.find("</li>", item_start)
                            if item_end != -1:
                                # Extract the complete list item
                                item = self._html_buffer[item_start : item_end + 5]
                                # Remove the processed item from buffer - update both representations
                                self._html_buffer = (
                                    self._html_buffer[:item_start]
                                    + self._html_buffer[item_end + 5 :]
                                )
                                self._buffer_io = io.StringIO(self._html_buffer)
                                return item
                        break  # No new elements found

                    # Found a topic section, extract the title if present
                    title_start = self._html_buffer.find('<h2 class="topic-title">', start_idx)
                    title_end = (
                        self._html_buffer.find("</h2>", title_start) if title_start != -1 else -1
                    )

                    if title_start != -1 and title_end != -1:
                        # Found a title, extract the complete section
                        section_end = self._html_buffer.find("</div>", title_end)
                        if section_end != -1:
                            # Extract the complete section
                            section = self._html_buffer[start_idx : section_end + 6]
                            # Remove the processed section from buffer - update both representations
                            self._html_buffer = (
                                self._html_buffer[:start_idx] + self._html_buffer[section_end + 6 :]
                            )
                            self._buffer_io = io.StringIO(self._html_buffer)
                            return section
                        else:
                            # Title found but section not complete
                            self._current_element = {
                                "type": "topic-section",
                                "title": self._html_buffer[
                                    title_start + len('<h2 class="topic-title">') : title_end
                                ].strip(),
                            }
                    else:
                        # No title found yet, keep accumulating
                        self._current_element = {"type": "topic-section", "title": None}

                    self._element_stack.append(self._current_element)

                # If we have a current element, try to complete it
                if self._current_element and self._current_element["type"] == "topic-section":
                    # Look for the end of the section
                    end_idx = self._html_buffer.find("</div>", self._html_buffer.find("</div>") + 1)
                    if end_idx != -1:
                        # Section is complete, extract it all
                        complete_element = self._html_buffer[: end_idx + 6]
                        # Update both representations
                        self._html_buffer = self._html_buffer[end_idx + 6 :]
                        self._buffer_io = io.StringIO(self._html_buffer)
                        self._current_element = None
                        self._element_stack.pop()
                        return complete_element

                break  # No complete elements found

            return None

    @pyqtSlot(str)
    def on_stream_update(self, text):
        """Handle streaming updates in a thread-safe way"""
        # Skip status messages
        if text.startswith("Generating insights") or text.startswith("Processing topic"):
            return

        # Get template type with lock
        with self._html_state_lock:
            template_type = self._template_type if hasattr(self, "_template_type") else None

        # Handle follow-up questions streaming
        if template_type == "follow-up-questions":
            items_to_append = []
            with self._html_state_lock:
                # Use shared extraction function (fixes O(n²) bug)
                extracted_items = self._extract_html_items(text, r'<li[^>]*>.*?</li>')

                for item in extracted_items:
                    # Add formatting if needed (ensure class and style)
                    if "class=" not in item:
                        item = item.replace(
                            "<li",
                            '<li class="insight-item" style="display: list-item !important; list-style-type: disc !important; font-weight: bold !important;"',
                        )
                    elif 'style="' not in item:
                        item = item.replace(
                            'class="',
                            'class="insight-item" style="display: list-item !important; list-style-type: disc !important; font-weight: bold !important;"',
                        )

                    items_to_append.append(item)

            # Update UI without lock
            for item in items_to_append:
                self.output_panel.append_to_dynamic_content(item)

        # Handle sentiment analysis streaming
        elif template_type == "sentiment-analysis":
            overall_sentiment_value = None
            items_to_append = []

            with self._html_state_lock:
                if not self._overall_sentiment_received:
                    # First line should be the overall sentiment
                    lines = text.split("\n", 1)
                    overall_sentiment = lines[0].strip()
                    if overall_sentiment in ["Positive", "Negative", "Neutral"]:
                        overall_sentiment_value = overall_sentiment
                        self._overall_sentiment_received = True
                        # Process the rest of the text if any
                        if len(lines) > 1:
                            text = lines[1]
                        else:
                            # Will set sentiment below and return
                            pass
                    else:
                        # If first line isn't sentiment, buffer it for list item processing
                        pass  # Fall through to list item processing

            # Update overall sentiment UI outside lock
            if overall_sentiment_value:
                self.output_panel.set_overall_sentiment(overall_sentiment_value)
                if "\n" not in text or text == overall_sentiment_value:
                    return  # Wait for next chunk

            # Process subsequent lines as list items
            with self._html_state_lock:
                # Use shared extraction function (fixes O(n²) bug)
                extracted_items = self._extract_html_items(text, r'<li[^>]*>.*?</li>')

                for item in extracted_items:
                    # Add formatting if needed (ensure class and style)
                    if "class=" not in item:
                        item = item.replace(
                            "<li",
                            '<li class="insight-item" style="display: list-item !important; list-style-type: disc !important; font-weight: bold !important;"',
                        )
                    elif 'style="' not in item:
                        item = item.replace(
                            'class="',
                            'class="insight-item" style="display: list-item !important; list-style-type: disc !important; font-weight: bold !important;"',
                        )

                    items_to_append.append(item)

            # Update UI without lock
            for item in items_to_append:
                self.output_panel.append_to_dynamic_content(item)

        # Handle meeting summary streaming
        elif template_type == "meeting-summary":
            items_to_append = []
            with self._html_state_lock:
                # Use shared extraction function (fixes O(n²) bug)
                extracted_items = self._extract_html_items(text, r'<li[^>]*>.*?</li>')

                for item in extracted_items:
                    # Add formatting if needed (ensure class and style, no bold)
                    if "class=" not in item:
                        item = item.replace(
                            "<li",
                            '<li class="insight-item" style="display: list-item !important; list-style-type: disc !important;"',
                        )
                    elif 'style="' not in item:
                        item = item.replace(
                            'class="',
                            'class="insight-item" style="display: list-item !important; list-style-type: disc !important;"',
                        )

                    items_to_append.append(item)

            # Update UI without lock
            for item in items_to_append:
                self.output_panel.append_to_dynamic_content(item)

        # Handle practitioner insights streaming
        elif template_type == "practitioner-insights":
            items_to_append = []
            with self._html_state_lock:
                # Use shared extraction function (fixes O(n²) bug)
                extracted_items = self._extract_html_items(text, r'<li[^>]*>.*?</li>')

                for item in extracted_items:
                    # Add formatting if needed (ensure class and style, no bold)
                    if "class=" not in item:
                        item = item.replace(
                            "<li",
                            '<li class="insight-item" style="display: list-item !important; list-style-type: disc !important;"',
                        )
                    elif 'style="' not in item:
                        item = item.replace(
                            'class="',
                            'class="insight-item" style="display: list-item !important; list-style-type: disc !important;"',
                        )

                    items_to_append.append(item)

            # Update UI without lock
            for item in items_to_append:
                self.output_panel.append_to_dynamic_content(item)

        # Handle topic summary streaming
        elif template_type == "topic-summary":
            items_to_append = []
            with self._html_state_lock:
                # Use shared extraction function (fixes O(n²) bug)
                extracted_items = self._extract_html_items(text, r'<li[^>]*>.*?</li>')

                for item in extracted_items:
                    # Add formatting if needed (ensure class and style, no bold)
                    if "class=" not in item:
                        item = item.replace(
                            "<li",
                            '<li class="insight-item" style="display: list-item !important; list-style-type: disc !important;"',
                        )
                    elif 'style="' not in item:
                        item = item.replace(
                            'class="',
                            'class="insight-item" style="display: list-item !important; list-style-type: disc !important;"',
                        )

                    items_to_append.append(item)

            # Update UI without lock
            for item in items_to_append:
                self.output_panel.append_to_dynamic_content(item)

        # Handle Fill Gaps streaming
        elif template_type == "fill-gaps":
            items_to_append = []
            with self._html_state_lock:
                # Use shared extraction function (fixes O(n²) bug)
                extracted_items = self._extract_html_items(text, r'<li[^>]*>.*?</li>')

                for item in extracted_items:
                    # Determine target list based on class
                    target_list_id = None
                    if 'class="core-thinking"' in item:
                        target_list_id = "core-thinking-list"
                    elif 'class="gap-item"' in item:
                        target_list_id = "gaps-list"
                    elif 'class="recommendation-item"' in item:
                        target_list_id = "recommendations-list"

                    if target_list_id:
                        items_to_append.append((target_list_id, item))

            # Update UI without lock
            for target_list_id, item in items_to_append:
                self.output_panel.append_to_list_by_id(target_list_id, item)

        # Handle Brainstorm Questions streaming
        elif template_type == "brainstorm":
            items_to_append = []
            with self._html_state_lock:
                # Use shared extraction function (fixes O(n²) bug)
                extracted_items = self._extract_html_items(text, r'<li[^>]*>.*?</li>')

                for item in extracted_items:
                    # Determine target list based on class
                    target_list_id = None
                    if 'class="challenge-question"' in item:
                        target_list_id = "challenge-questions-list"
                    elif 'class="alternative-frame"' in item:
                        target_list_id = "alternative-frames-list"
                    elif 'class="provocative-idea"' in item:
                        target_list_id = "provocative-ideas-list"

                    if target_list_id:
                        items_to_append.append((target_list_id, item))

            # Update UI without lock
            for target_list_id, item in items_to_append:
                self.output_panel.append_to_list_by_id(target_list_id, item)

        # Handle Company Fit streaming
        elif template_type == "company-fit":
            items_to_append = []
            with self._html_state_lock:
                # Use shared extraction function (fixes O(n²) bug)
                extracted_items = self._extract_html_items(text, r'<li[^>]*>.*?</li>')

                for item in extracted_items:
                    # Determine target list based on class
                    target_list_id = None
                    if 'class="key-topic"' in item:
                        target_list_id = "key-topics-list"
                    elif 'class="viya-connection"' in item:
                        target_list_id = "viya-connections-list"
                    elif 'class="missing-consideration"' in item:
                        target_list_id = "missing-considerations-list"

                    if target_list_id:
                        items_to_append.append((target_list_id, item))

            # Update UI without lock
            for target_list_id, item in items_to_append:
                self.output_panel.append_to_list_by_id(target_list_id, item)

        # Handle Fact Checking streaming
        elif template_type == "fact-check":
            items_to_append = []
            with self._html_state_lock:
                # Use shared extraction function with specific pattern (fixes O(n²) bug)
                extracted_items = self._extract_html_items(text, r'<li class=["\']fact-check-item["\']>.*?</li>')

                items_to_append.extend(extracted_items)

            # Update UI without lock
            for item in items_to_append:
                self.output_panel.append_to_list_by_id("fact-check-list", item)

        # Handle Answer Question streaming
        elif template_type == "answer-question":
            items_to_append = []
            with self._html_state_lock:
                # Use shared extraction function (fixes O(n²) bug)
                # Pattern matches any of the three class types
                extracted_items = self._extract_html_items(
                    text,
                    r'<li class=["\'](?:answer-item|rationale-item|example-item)["\']>.*?</li>'
                )

                for item in extracted_items:
                    # Determine target list based on class
                    target_list_id = None
                    if 'class="answer-item"' in item or "class='answer-item'" in item:
                        target_list_id = "answer-list"
                    elif 'class="rationale-item"' in item or "class='rationale-item'" in item:
                        target_list_id = "rationale-list"
                    elif 'class="example-item"' in item or "class='example-item'" in item:
                        target_list_id = "examples-list"

                    # Append the complete item to the correct list
                    if target_list_id:
                        items_to_append.append((target_list_id, item))

            # Update UI without lock
            for target_list_id, item in items_to_append:
                self.output_panel.append_to_list_by_id(target_list_id, item)

        # Handle Problem Solving / Issue Tree Logic streaming
        elif template_type == "problem-solving":
            items_to_append = []
            with self._html_state_lock:
                # Use shared extraction function (fixes O(n²) bug)
                # Pattern matches all 9 class types
                extracted_items = self._extract_html_items(
                    text,
                    r'<li class=["\'](?:core-problem|logic-tree-component|evaluation-(?:mece|assumption|logic|data)|challenge-(?:weakness|question|reframe))["\']>.*?</li>'
                )

                for item in extracted_items:
                    # Determine target list based on class
                    target_list_id = None
                    if 'class="core-problem"' in item or "class='core-problem'" in item:
                        target_list_id = "core-problem-list"
                    elif 'class="logic-tree-component"' in item or "class='logic-tree-component'" in item:
                        target_list_id = "logic-tree-list"
                    elif any(cls in item for cls in ['evaluation-mece', 'evaluation-assumption', 'evaluation-logic', 'evaluation-data']):
                        target_list_id = "evaluation-list"
                    elif any(cls in item for cls in ['challenge-weakness', 'challenge-question', 'challenge-reframe']):
                        target_list_id = "challenge-list"

                    # Append the complete item to the correct list
                    if target_list_id:
                        items_to_append.append((target_list_id, item))

            # Update UI without lock
            for target_list_id, item in items_to_append:
                self.output_panel.append_to_list_by_id(target_list_id, item)

        # Handle SCQA Framework streaming
        elif template_type == "scqa":
            items_to_append = []
            with self._html_state_lock:
                # Use shared extraction function (fixes O(n²) bug)
                # Pattern matches all 6 SCQA class types
                extracted_items = self._extract_html_items(
                    text,
                    r'<li class=["\']scqa-(?:situation|complication|question|answer|assessment|roadmap)["\']>.*?</li>'
                )

                for item in extracted_items:
                    # Extract class name and map to list ID
                    # Find the class attribute value
                    class_match = re.search(r'class=["\']([^"\']+)["\']', item)
                    if class_match:
                        target_list_id = f"{class_match.group(1)}-list"
                        items_to_append.append((target_list_id, item))

            # Update UI without lock
            for target_list_id, item in items_to_append:
                self.output_panel.append_to_list_by_id(target_list_id, item)

        # Handle Hypothesis Driven Thinking streaming
        elif template_type == "hypothesis-driven":
            items_to_append = []
            with self._html_state_lock:
                # Use shared extraction function (fixes O(n²) bug)
                # Pattern matches all 9 hypothesis class types
                extracted_items = self._extract_html_items(
                    text,
                    r'<li class=["\']hypothesis-(?:problem|hypothesis|evidence-(?:support|contradict|missing)|priority|testing|decision|assessment)["\']>.*?</li>'
                )

                for item in extracted_items:
                    # Determine target list based on class
                    target_list_id = None
                    if 'hypothesis-problem' in item:
                        target_list_id = "hypothesis-problem-list"
                    elif 'hypothesis-hypothesis' in item:
                        target_list_id = "hypothesis-hypothesis-list"
                    elif any(cls in item for cls in ['hypothesis-evidence-support', 'hypothesis-evidence-contradict', 'hypothesis-evidence-missing']):
                        target_list_id = "hypothesis-evidence-list"
                    elif 'hypothesis-priority' in item:
                        target_list_id = "hypothesis-priority-list"
                    elif 'hypothesis-testing' in item:
                        target_list_id = "hypothesis-testing-list"
                    elif 'hypothesis-decision' in item:
                        target_list_id = "hypothesis-decision-list"
                    elif 'hypothesis-assessment' in item:
                        target_list_id = "hypothesis-assessment-list"

                    # Append the complete item to the correct list
                    if target_list_id:
                        items_to_append.append((target_list_id, item))

            # Update UI without lock
            for target_list_id, item in items_to_append:
                self.output_panel.append_to_list_by_id(target_list_id, item)

        # Handle First Principles Thinking streaming
        elif template_type == "first-principles":
            items_to_append = []
            with self._html_state_lock:
                # Use shared extraction function (fixes O(n²) bug)
                # Pattern matches all 7 first-principles class types
                extracted_items = self._extract_html_items(
                    text,
                    r'<li class=["\']fp-(?:conventional|fundamental|assumption|rebuild|insight|implementation|metacognitive)["\']>.*?</li>'
                )

                for item in extracted_items:
                    # Extract class name and map to list ID
                    class_match = re.search(r'class=["\']([^"\']+)["\']', item)
                    if class_match:
                        target_list_id = f"{class_match.group(1)}-list"
                        items_to_append.append((target_list_id, item))

            # Update UI without lock
            for target_list_id, item in items_to_append:
                self.output_panel.append_to_list_by_id(target_list_id, item)

        # Handle Reframing streaming
        elif template_type == "reframing":
            items_to_append = []
            with self._html_state_lock:
                # Use shared extraction function (fixes O(n²) bug)
                # Pattern matches both reframing class types
                extracted_items = self._extract_html_items(
                    text,
                    r'<li class=["\']reframing-(?:statement|point)["\']>.*?</li>'
                )

                for item in extracted_items:
                    # Extract class name and map to list ID
                    class_match = re.search(r'class=["\']([^"\']+)["\']', item)
                    if class_match:
                        target_list_id = f"{class_match.group(1)}-list"
                        items_to_append.append((target_list_id, item))

            # Update UI without lock
            for target_list_id, item in items_to_append:
                self.output_panel.append_to_list_by_id(target_list_id, item)

        # Default behavior for other template types
        else:
            complete_element = self._process_html_chunk(text)
            if complete_element:
                # Check is_first_update with lock
                with self._html_state_lock:
                    is_first = self._is_first_update
                    if is_first:
                        self._is_first_update = False

                # If this is the first update, set the output
                if is_first:
                    self.output_panel.set_output(complete_element)
                else:
                    # For subsequent elements, we want to append only new content
                    # First, check if this is a new section or a list item
                    if complete_element.startswith('<div class="topic-section">'):
                        # This is a new section, append it
                        self.output_panel.append_output(complete_element)
                    elif complete_element.startswith('<li class="insight-item">'):
                        # This is a list item, append it to the current list
                        self.output_panel.append_output(
                            f"""<div class="insight-block">
            <ul class="insight-list">
                {complete_element}
            </ul>
        </div>"""
                        )

    @pyqtSlot(str)
    def on_progress_update(self, message):
        """Handle progress updates in a thread-safe way"""
        logger.debug("Progress update", message=message)
        self.output_panel.set_status(message)

    def clear_output(self):
        """Clear the output panel and reset HTML streaming state"""
        logger.info("Clearing output panel and resetting state")
        self.output_panel.set_output("")
        self.output_panel.set_title("Output")  # Reset title to default
        # Clear transcript (property handles locking)
        self.current_transcript = ""
        with self._html_state_lock:
            self._html_buffer = ""
            self._current_element = None
            self._element_stack = []
            self._is_first_update = True
            self._current_list_items = []
            self._overall_sentiment_received = False  # Reset sentiment flag

    def transcribe_last_30_seconds(self):
        """Transcribe only the last 30 seconds of audio"""
        logger.info("Transcribe last 30 seconds requested")
        # Disable button to prevent multiple clicks
        self.controls_panel.transcribe_last_30_button.setEnabled(False)
        self.controls_panel.transcribe_last_30_button.setText("Transcribing...")

        # Get last 30 seconds of audio data
        audio_data = self.recorder.get_last_n_seconds(30)

        if audio_data is None:
            logger.warning("Transcription failed: Not enough audio in buffer (last 30s)")
            self.controls_panel.transcribe_last_30_button.setText("Transcribe Last 30s")
            self.controls_panel.transcribe_last_30_button.setEnabled(True)
            QMessageBox.warning(self, "Transcription Error", "Not enough audio in buffer")
            return

        logger.info("Starting transcription from last 30s", buffer_size_bytes=len(audio_data), sample_rate=self.recorder.sample_rate)
        # Start transcription in a separate thread
        threading.Thread(
            target=self._transcribe_thread, args=(audio_data, self.recorder.sample_rate)
        ).start()
