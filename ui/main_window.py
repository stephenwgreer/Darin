import html
import io
import json
import re
import threading
from pathlib import Path

from loguru import logger
from PyQt6.QtCore import Qt, pyqtSignal, pyqtSlot
from PyQt6.QtGui import QFont, QIcon, QPixmap
from PyQt6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QSplitter,
    QVBoxLayout,
    QWidget,
)

from app_controller import AppController

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
from ui import theme
from ui.animated_label import AnimatedLabel
from ui.controls_panel import ControlsPanel
from ui.font_manager import FontManager
from ui.html_templates import create_topic_section
from ui.output_panel import OutputPanel
from ui.stream_handlers import TEMPLATE_REGISTRY, parse_first_line_value, route_stream_item


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

        # Make window frameless for custom title bar
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)

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
            format="{time:YYYY-MM-DD HH:mm:ss} | {level: <8} | {name}:{function}:{line} - {message}",
        )
        logger.info("Darin Audio Assistant initializing")

        # Load fonts
        FontManager.load_fonts()

        # Set application icon
        app_icon = QIcon("assets/Darin_ICON.png")
        self.setWindowIcon(app_icon)

        # Initialize AppController with callback→signal bridge.
        # Callbacks are invoked from background threads; they emit Qt signals
        # which are queued to the main thread automatically.
        self.controller = AppController(
            on_recording_started=lambda: self.recording_started.emit(),
            on_recording_stopped=lambda: self.recording_stopped.emit(),
            on_transcription_complete=lambda text: self.transcription_complete.emit(text),
            on_processing_complete=lambda result: self.processing_complete.emit(result),
            on_progress=lambda msg: self.progress_update.emit(msg),
            on_stream_chunk=lambda text: self.stream_update.emit(text),
        )

        logger.info("AppController initialized")

        # HTML streaming state (UI concern — stays here)
        self._html_state_lock = threading.Lock()
        self._buffer_io = io.StringIO()
        self._current_element = None
        self._element_stack = []
        self._is_first_update = True
        self._current_list_items = []

        # First-line parser state (e.g., sentiment overall value)
        self._first_line_received = False

        # Setup UI
        self.setup_ui()

        # Connect signals to slots
        self.setup_connections()

    def _create_title_bar(self):
        """Create custom title bar for frameless window"""
        title_bar = QWidget()
        title_bar.setObjectName("titleBar")
        title_bar.setFixedHeight(40)
        title_bar_layout = QHBoxLayout(title_bar)
        title_bar_layout.setContentsMargins(10, 0, 10, 0)
        title_bar_layout.setSpacing(10)

        # App title
        title_label = QLabel("Darin Audio Assistant")
        title_label.setObjectName("titleBarLabel")
        title_bar_layout.addWidget(title_label)

        title_bar_layout.addStretch()

        # Window control buttons
        minimize_btn = QPushButton("−")
        minimize_btn.setObjectName("minimizeButton")
        minimize_btn.setFixedSize(40, 30)
        minimize_btn.clicked.connect(self.showMinimized)
        title_bar_layout.addWidget(minimize_btn)

        maximize_btn = QPushButton("□")
        maximize_btn.setObjectName("maximizeButton")
        maximize_btn.setFixedSize(40, 30)
        maximize_btn.clicked.connect(self._toggle_maximize)
        title_bar_layout.addWidget(maximize_btn)

        close_btn = QPushButton("×")
        close_btn.setObjectName("closeButton")
        close_btn.setFixedSize(40, 30)
        close_btn.clicked.connect(self.close)
        title_bar_layout.addWidget(close_btn)

        # Make title bar draggable
        title_bar.mousePressEvent = self._title_bar_mouse_press
        title_bar.mouseMoveEvent = self._title_bar_mouse_move

        return title_bar

    def _toggle_maximize(self):
        """Toggle between maximized and normal window state"""
        if self.isMaximized():
            self.showNormal()
        else:
            self.showMaximized()

    def _title_bar_mouse_press(self, event):
        """Handle mouse press on title bar for dragging"""
        if event.button() == Qt.MouseButton.LeftButton:
            self._drag_pos = event.globalPosition().toPoint()

    def _title_bar_mouse_move(self, event):
        """Handle mouse move on title bar for dragging"""
        if hasattr(self, "_drag_pos"):
            delta = event.globalPosition().toPoint() - self._drag_pos
            self.move(self.pos() + delta)
            self._drag_pos = event.globalPosition().toPoint()

    def _load_stylesheet(self):
        """Load and apply the QSS stylesheet for dark theme"""
        stylesheet_path = Path(__file__).parent / "styles.qss"

        if stylesheet_path.exists():
            logger.info("Loading stylesheet from styles.qss")
            with open(stylesheet_path) as f:
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

    # Delegate thread-safe state to AppController
    @property
    def current_transcript(self):
        return self.controller.current_transcript

    @current_transcript.setter
    def current_transcript(self, value):
        self.controller.current_transcript = value

    @property
    def is_processing(self):
        return self.controller.is_processing

    @is_processing.setter
    def is_processing(self, value):
        self.controller.is_processing = value

    def _extract_html_items(self, text: str, pattern: str = r"<li[^>]*>(.*?)</li>") -> list[str]:
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
        main_widget.setObjectName("mainWidget")
        self.setCentralWidget(main_widget)
        main_layout = QVBoxLayout(main_widget)
        main_layout.setContentsMargins(0, 0, 0, 0)  # No margins for frameless window
        main_layout.setSpacing(0)  # No spacing at top level

        ########################
        # Custom Title Bar
        ########################
        self.title_bar = self._create_title_bar()
        main_layout.addWidget(self.title_bar)

        # Content container with padding
        content_container = QWidget()
        content_layout = QVBoxLayout(content_container)
        content_layout.setContentsMargins(10, 10, 10, 10)
        content_layout.setSpacing(10)

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

        content_layout.addWidget(header_widget)

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

        content_layout.addWidget(self.content_splitter)

        # Footer
        footer = QLabel("© 2025 Darin Listening Assistant")
        footer.setObjectName("footerLabel")
        footer.setAlignment(Qt.AlignmentFlag.AlignCenter)
        content_layout.addWidget(footer)

        # Add content container to main layout
        main_layout.addWidget(content_container)

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
        if not self.controller.is_recording:
            if self.controller.start_recording():
                self.controls_panel.set_recording_active(True)
        else:
            if self.controller.stop_recording():
                self.controls_panel.set_recording_active(False)

    def transcribe_buffer(self):
        """Transcribe the current audio buffer"""
        self.controls_panel.transcribe_button.setEnabled(False)
        self.controls_panel.transcribe_button.setText("Transcribing...")

        if self.controller.buffer_seconds == 0:
            self.controls_panel.transcribe_button.setText("Transcribe Buffer")
            self.controls_panel.transcribe_button.setEnabled(True)
            QMessageBox.warning(self, "Transcription Error", "No audio in buffer to transcribe")
            return

        self.controller.transcribe_buffer()

    def run_prompt_with_auto_transcribe(self, prompt_template=None, title=None):
        """Auto transcribe and then run a specific prompt via AppController"""
        # Disable all prompt buttons (UI concern)
        self.controls_panel.set_prompt_buttons_enabled(False)

        # Clear output before running new prompt
        self.clear_output()

        # Set the output panel title if provided
        if title:
            self.output_panel.set_title(title)

        self.output_panel.set_output("Capturing audio and transcribing...")

        def on_template_setup(prompt_tmpl):
            """Called from background thread — sets up static HTML template."""
            template_type = self._setup_static_template(prompt_tmpl)
            # Reset HTML streaming state for new dynamic content
            with self._html_state_lock:
                self._buffer_io = io.StringIO()
                self._current_element = None
                self._element_stack = []
                self._is_first_update = False
                self._current_list_items = []
                self._first_line_received = False
            # Store template_type on controller for on_stream_update to read
            self.controller.template_type = template_type
            return template_type

        self.controller.run_prompt(
            prompt_template,
            title=title,
            on_template_setup=on_template_setup,
        )

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
        if self.controller.buffer_seconds > 0:
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
        logger.info(
            "Processing complete signal received",
            has_error="error" in result,
            has_result="result" in result,
        )
        # Reset processing state in GUI thread (thread-safe)
        self.is_processing = False

        if "error" in result:
            logger.error("Processing completed with error", error=result["error"])
            self.output_panel.set_error(result["error"])
        elif "result" in result:
            # For registered streaming types, don't overwrite formatted content
            template_type = self.controller.template_type
            if template_type not in TEMPLATE_REGISTRY:
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
        """Process a chunk of HTML text and return complete elements if found.

        Uses io.StringIO for O(n) append, then reads into a local string for
        parsing. Only rebuilds _buffer_io when content is consumed.
        """
        with self._html_state_lock:
            self._buffer_io.seek(0, 2)
            self._buffer_io.write(chunk)
            buf = self._buffer_io.getvalue()

            while True:
                if not self._current_element:
                    start_idx = buf.find('<div class="topic-section">')
                    if start_idx == -1:
                        item_start = buf.find('<li class="insight-item">')
                        if item_start != -1:
                            item_end = buf.find("</li>", item_start)
                            if item_end != -1:
                                item = buf[item_start : item_end + 5]
                                buf = buf[:item_start] + buf[item_end + 5 :]
                                self._buffer_io = io.StringIO(buf)
                                return item
                        break

                    title_start = buf.find('<h2 class="topic-title">', start_idx)
                    title_end = buf.find("</h2>", title_start) if title_start != -1 else -1

                    if title_start != -1 and title_end != -1:
                        section_end = buf.find("</div>", title_end)
                        if section_end != -1:
                            section = buf[start_idx : section_end + 6]
                            buf = buf[:start_idx] + buf[section_end + 6 :]
                            self._buffer_io = io.StringIO(buf)
                            return section
                        else:
                            self._current_element = {
                                "type": "topic-section",
                                "title": buf[
                                    title_start + len('<h2 class="topic-title">') : title_end
                                ].strip(),
                            }
                    else:
                        self._current_element = {"type": "topic-section", "title": None}

                    self._element_stack.append(self._current_element)

                if self._current_element and self._current_element["type"] == "topic-section":
                    end_idx = buf.find("</div>", buf.find("</div>") + 1)
                    if end_idx != -1:
                        complete_element = buf[: end_idx + 6]
                        buf = buf[end_idx + 6 :]
                        self._buffer_io = io.StringIO(buf)
                        self._current_element = None
                        self._element_stack.pop()
                        return complete_element

                break

            return None

    @pyqtSlot(str)
    def on_stream_update(self, text):
        """Handle streaming updates in a thread-safe way.

        Uses TEMPLATE_REGISTRY for data-driven routing of all registered
        template types (including sentiment-analysis via first_line_parser).
        Falls back to _process_html_chunk() for unregistered templates.
        """
        # Skip status messages
        if text.startswith("Generating insights") or text.startswith("Processing topic"):
            return

        template_type = self.controller.template_type

        # Registry-driven path (covers all registered templates)
        if template_type in TEMPLATE_REGISTRY:
            config = TEMPLATE_REGISTRY[template_type]
            first_line_value = None
            items_to_append = []
            flp = config.get("first_line_parser")

            with self._html_state_lock:
                # Handle first-line parsing (e.g., sentiment overall value)
                if flp and not self._first_line_received:
                    value, text = parse_first_line_value(text, config)
                    if value:
                        first_line_value = value
                        self._first_line_received = True
                        if not text.strip():
                            # Only the first-line value, no list items yet
                            pass

                if text.strip():
                    extracted = self._extract_html_items(text, config["pattern"])
                    for item in extracted:
                        result = route_stream_item(item, config)
                        if result:
                            items_to_append.append(result)

            # UI updates outside lock
            if first_line_value and flp:
                callback = getattr(self.output_panel, flp["callback_method"], None)
                if callback:
                    callback(first_line_value)

            for list_id, item_html in items_to_append:
                if list_id == "dynamic-content":
                    self.output_panel.append_to_dynamic_content(item_html)
                else:
                    self.output_panel.append_to_list_by_id(list_id, item_html)

        # Fallback for unregistered templates (topic-section HTML chunks)
        else:
            complete_element = self._process_html_chunk(text)
            if complete_element:
                with self._html_state_lock:
                    is_first = self._is_first_update
                    if is_first:
                        self._is_first_update = False

                if is_first:
                    self.output_panel.set_output(complete_element)
                else:
                    if complete_element.startswith('<div class="topic-section">'):
                        self.output_panel.append_output(complete_element)
                    elif complete_element.startswith('<li class="insight-item">'):
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
            self._buffer_io = io.StringIO()
            self._current_element = None
            self._element_stack = []
            self._is_first_update = True
            self._current_list_items = []
            self._first_line_received = False

    def transcribe_last_30_seconds(self):
        """Transcribe only the last 30 seconds of audio"""
        self.controls_panel.transcribe_last_30_button.setEnabled(False)
        self.controls_panel.transcribe_last_30_button.setText("Transcribing...")

        if self.controller.buffer_seconds == 0:
            self.controls_panel.transcribe_last_30_button.setText("Transcribe Last 30s")
            self.controls_panel.transcribe_last_30_button.setEnabled(True)
            QMessageBox.warning(self, "Transcription Error", "Not enough audio in buffer")
            return

        self.controller.transcribe_last_n_seconds(30)
