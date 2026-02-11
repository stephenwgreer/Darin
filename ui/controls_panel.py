from datetime import datetime

from PyQt6.QtCore import Qt, QTimer, pyqtSignal
from PyQt6.QtGui import QAction, QFont
from PyQt6.QtWidgets import QLabel, QMenu, QPushButton, QVBoxLayout, QWidget

from ui.font_manager import FontManager


class ControlsPanel(QWidget):
    """Left panel containing recording controls and prompt buttons"""

    # Signals
    record_clicked = pyqtSignal()
    transcribe_clicked = pyqtSignal()
    transcribe_last_30_clicked = pyqtSignal()
    topics_clicked = pyqtSignal()
    insights_clicked = pyqtSignal()
    summary_clicked = pyqtSignal()
    questions_clicked = pyqtSignal()
    sentiment_clicked = pyqtSignal()
    fill_gaps_clicked = pyqtSignal()
    brainstorm_clicked = pyqtSignal()
    company_fit_clicked = pyqtSignal()
    fact_check_clicked = pyqtSignal()
    answer_question_clicked = pyqtSignal()
    problem_solving_clicked = pyqtSignal()
    scqa_clicked = pyqtSignal()
    hypothesis_driven_clicked = pyqtSignal()
    first_principles_clicked = pyqtSignal()
    reframing_clicked = pyqtSignal()
    clear_output_clicked = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setup_ui()
        self._recording_start_time = None
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._update_timestamp)

    def setup_ui(self):
        layout = QVBoxLayout(self)

        # Recording controls section
        controls_label = QLabel("Recording Controls")
        controls_label.setFont(FontManager.get_font(14, QFont.Weight.Normal))
        layout.addWidget(controls_label)

        # Record button
        self.record_button = QPushButton("Start Recording")
        self.record_button.setFont(FontManager.get_font(12, QFont.Weight.Normal))
        self.record_button.clicked.connect(self.record_clicked.emit)
        layout.addWidget(self.record_button)

        # Timestamp label
        self.timestamp_label = QLabel("00:00:00")
        self.timestamp_label.setFont(FontManager.get_font(12, QFont.Weight.Normal))
        self.timestamp_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.timestamp_label.setStyleSheet("color: #666666;")
        self.timestamp_label.hide()
        layout.addWidget(self.timestamp_label)

        # Transcribe button
        self.transcribe_button = QPushButton("Transcribe Buffer")
        self.transcribe_button.setFont(FontManager.get_font(12, QFont.Weight.Normal))
        self.transcribe_button.clicked.connect(self.transcribe_clicked.emit)
        self.transcribe_button.setEnabled(False)
        layout.addWidget(self.transcribe_button)

        # Transcribe last 30 seconds button
        self.transcribe_last_30_button = QPushButton("Transcribe Last 30s")
        self.transcribe_last_30_button.setFont(FontManager.get_font(12, QFont.Weight.Normal))
        self.transcribe_last_30_button.clicked.connect(self.transcribe_last_30_clicked.emit)
        self.transcribe_last_30_button.setEnabled(False)
        layout.addWidget(self.transcribe_last_30_button)

        # Clear output button
        self.clear_button = QPushButton("Clear Output")
        self.clear_button.setFont(FontManager.get_font(12, QFont.Weight.Normal))
        self.clear_button.clicked.connect(self.clear_output_clicked.emit)
        self.clear_button.setStyleSheet("background-color: #ffebee; color: #c62828;")
        layout.addWidget(self.clear_button)

        # Spacer
        layout.addSpacing(20)

        # Prompt buttons section
        prompt_label = QLabel("Specific Prompts")
        prompt_label.setFont(FontManager.get_font(14, QFont.Weight.Normal))
        layout.addWidget(prompt_label)

        # --- Transcript Processing Menu Button ---
        self.processing_menu_button = QPushButton("Transcript Processing")
        self.processing_menu_button.setFont(FontManager.get_font(12, QFont.Weight.Light))

        processing_menu = QMenu(self)

        # Extract Topics Action
        self.topic_action = QAction("Extract Topics", self)
        self.topic_action.triggered.connect(self.topics_clicked.emit)
        processing_menu.addAction(self.topic_action)

        # Meeting Summary Action
        self.summary_action = QAction("Meeting Summary", self)
        self.summary_action.triggered.connect(self.summary_clicked.emit)
        processing_menu.addAction(self.summary_action)

        # Sentiment Analysis Action
        self.sentiment_action = QAction("Sentiment Analysis", self)
        self.sentiment_action.triggered.connect(self.sentiment_clicked.emit)
        processing_menu.addAction(self.sentiment_action)

        self.processing_menu_button.setMenu(processing_menu)
        self.processing_menu_button.setEnabled(False)  # Start disabled
        layout.addWidget(self.processing_menu_button)
        # --- End Transcript Processing Menu ---

        # --- Logic Menu Button ---
        self.logic_menu_button = QPushButton("Logic")
        self.logic_menu_button.setFont(FontManager.get_font(12, QFont.Weight.Light))

        logic_menu = QMenu(self)

        # First Principles Action
        self.first_principles_action = QAction("First Principles", self)
        self.first_principles_action.triggered.connect(self.first_principles_clicked.emit)
        logic_menu.addAction(self.first_principles_action)

        # SCQA Framework Action
        self.scqa_action = QAction("SCQA Framework", self)
        self.scqa_action.triggered.connect(self.scqa_clicked.emit)
        logic_menu.addAction(self.scqa_action)

        # Hypothesis Thinking Action
        self.hypothesis_action = QAction("Hypothesis Thinking", self)
        self.hypothesis_action.triggered.connect(self.hypothesis_driven_clicked.emit)
        logic_menu.addAction(self.hypothesis_action)

        # Issue Tree Logic Action
        self.problem_solving_action = QAction("Issue Tree Logic", self)
        self.problem_solving_action.triggered.connect(self.problem_solving_clicked.emit)
        logic_menu.addAction(self.problem_solving_action)

        self.logic_menu_button.setMenu(logic_menu)
        self.logic_menu_button.setEnabled(False)  # Start disabled
        layout.addWidget(self.logic_menu_button)
        # --- End Logic Menu ---

        # Banking insights
        self.insights_button = QPushButton("Practitioner Insights")
        self.insights_button.setFont(FontManager.get_font(12, QFont.Weight.Light))
        self.insights_button.clicked.connect(self.insights_clicked.emit)
        self.insights_button.setEnabled(False)
        layout.addWidget(self.insights_button)

        # Follow-up questions
        self.questions_button = QPushButton("Follow-up Questions")
        self.questions_button.setFont(FontManager.get_font(12, QFont.Weight.Light))
        self.questions_button.clicked.connect(self.questions_clicked.emit)
        self.questions_button.setEnabled(False)
        layout.addWidget(self.questions_button)

        # Reframing button (New)
        self.reframing_button = QPushButton("Reframing")
        self.reframing_button.setFont(FontManager.get_font(12, QFont.Weight.Light))
        self.reframing_button.clicked.connect(self.reframing_clicked.emit)
        self.reframing_button.setEnabled(False)
        layout.addWidget(self.reframing_button)

        # Fill in gaps in reasoning
        self.fill_gaps_button = QPushButton("Gaps in Reasoning")
        self.fill_gaps_button.setFont(FontManager.get_font(12, QFont.Weight.Light))
        self.fill_gaps_button.clicked.connect(self.fill_gaps_clicked.emit)
        self.fill_gaps_button.setEnabled(False)
        layout.addWidget(self.fill_gaps_button)

        # Brainstorm
        self.brainstorm_button = QPushButton("Brainstorming")
        self.brainstorm_button.setFont(FontManager.get_font(12, QFont.Weight.Light))
        self.brainstorm_button.clicked.connect(self.brainstorm_clicked.emit)
        self.brainstorm_button.setEnabled(False)
        layout.addWidget(self.brainstorm_button)

        # Company fit
        self.company_fit_button = QPushButton("SAS Viya Alignment")
        self.company_fit_button.setFont(FontManager.get_font(12, QFont.Weight.Light))
        self.company_fit_button.clicked.connect(self.company_fit_clicked.emit)
        self.company_fit_button.setEnabled(False)
        layout.addWidget(self.company_fit_button)

        # Fact checking
        self.fact_check_button = QPushButton("Fact Check")
        self.fact_check_button.setFont(FontManager.get_font(12, QFont.Weight.Light))
        self.fact_check_button.clicked.connect(self.fact_check_clicked.emit)
        self.fact_check_button.setEnabled(False)
        layout.addWidget(self.fact_check_button)

        # Answer Question button
        self.answer_question_button = QPushButton("Answer Question")
        self.answer_question_button.setFont(FontManager.get_font(12, QFont.Weight.Light))
        self.answer_question_button.clicked.connect(self.answer_question_clicked.emit)
        self.answer_question_button.setEnabled(False)
        layout.addWidget(self.answer_question_button)

        # Add stretch at the bottom
        layout.addStretch()

    def set_recording_active(self, active):
        """Update UI state when recording starts/stops"""
        self.record_button.setText("Stop Recording" if active else "Start Recording")
        self.transcribe_button.setEnabled(True)
        self.transcribe_last_30_button.setEnabled(True)

        if active:
            self._recording_start_time = datetime.now()
            self._timer.start(1000)  # Update every second
            self.timestamp_label.show()
        else:
            self._timer.stop()
            self.timestamp_label.hide()
            self.timestamp_label.setText("00:00:00")

    def _update_timestamp(self):
        """Update the timestamp display"""
        if self._recording_start_time:
            elapsed = datetime.now() - self._recording_start_time
            hours = elapsed.seconds // 3600
            minutes = (elapsed.seconds % 3600) // 60
            seconds = elapsed.seconds % 60
            self.timestamp_label.setText(f"{hours:02d}:{minutes:02d}:{seconds:02d}")

    def set_prompt_buttons_enabled(self, enabled):
        """Enable or disable all prompt buttons"""
        # Enable/disable the menu buttons
        self.processing_menu_button.setEnabled(enabled)
        self.logic_menu_button.setEnabled(enabled)

        # Enable/disable other buttons as before
        self.insights_button.setEnabled(enabled)
        self.questions_button.setEnabled(enabled)
        self.reframing_button.setEnabled(enabled)
        self.fill_gaps_button.setEnabled(enabled)
        self.brainstorm_button.setEnabled(enabled)
        self.company_fit_button.setEnabled(enabled)
        self.fact_check_button.setEnabled(enabled)
        self.answer_question_button.setEnabled(enabled)
