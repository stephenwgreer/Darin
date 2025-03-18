from PyQt6.QtWidgets import (QWidget, QVBoxLayout, QLabel, QPushButton, 
                         QProgressBar, QSpacerItem, QSizePolicy)
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QFont

from ui.font_manager import FontManager

class ControlsPanel(QWidget):
    """Left panel containing recording controls and prompt buttons"""
    
    # Signals
    record_clicked = pyqtSignal()
    save_clicked = pyqtSignal()
    transcribe_clicked = pyqtSignal()
    topics_clicked = pyqtSignal()
    insights_clicked = pyqtSignal()
    summary_clicked = pyqtSignal()
    questions_clicked = pyqtSignal()
    sentiment_clicked = pyqtSignal()
    fill_gaps_clicked = pyqtSignal()
    brainstorm_clicked = pyqtSignal()
    company_fit_clicked = pyqtSignal()
    fact_check_clicked = pyqtSignal()
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setup_ui()
    
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
        
        # Save button
        self.save_button = QPushButton("Save Current Buffer")
        self.save_button.setFont(FontManager.get_font(12, QFont.Weight.Normal))
        self.save_button.clicked.connect(self.save_clicked.emit)
        self.save_button.setEnabled(False)
        layout.addWidget(self.save_button)
        
        # Transcribe button
        self.transcribe_button = QPushButton("Transcribe Buffer")
        self.transcribe_button.setFont(FontManager.get_font(12, QFont.Weight.Normal))
        self.transcribe_button.clicked.connect(self.transcribe_clicked.emit)
        self.transcribe_button.setEnabled(False)
        layout.addWidget(self.transcribe_button)
        
        # Spacer
        layout.addSpacing(20)
        
        # Prompt buttons section
        prompt_label = QLabel("Specific Prompts")
        prompt_label.setFont(FontManager.get_font(14, QFont.Weight.Normal))
        layout.addWidget(prompt_label)
        
        # Topic extraction
        self.topic_button = QPushButton("Extract Topics")
        self.topic_button.setFont(FontManager.get_font(12, QFont.Weight.Light))
        self.topic_button.clicked.connect(self.topics_clicked.emit)
        self.topic_button.setEnabled(False)
        layout.addWidget(self.topic_button)
        
        # Meeting summary
        self.summary_button = QPushButton("Meeting Summary")
        self.summary_button.setFont(FontManager.get_font(12, QFont.Weight.Light))
        self.summary_button.clicked.connect(self.summary_clicked.emit)
        self.summary_button.setEnabled(False)
        layout.addWidget(self.summary_button)
        
        # Banking insights
        self.insights_button = QPushButton("Banking Practitioner Insights")
        self.insights_button.setFont(FontManager.get_font(12, QFont.Weight.Light))
        self.insights_button.clicked.connect(self.insights_clicked.emit)
        self.insights_button.setEnabled(False)
        layout.addWidget(self.insights_button)
        
        # Follow-up questions
        self.questions_button = QPushButton("Generate Follow-up Questions")
        self.questions_button.setFont(FontManager.get_font(12, QFont.Weight.Light))
        self.questions_button.clicked.connect(self.questions_clicked.emit)
        self.questions_button.setEnabled(False)
        layout.addWidget(self.questions_button)
        
        # Sentiment analysis
        self.sentiment_button = QPushButton("Sentiment Analysis")
        self.sentiment_button.setFont(FontManager.get_font(12, QFont.Weight.Light))
        self.sentiment_button.clicked.connect(self.sentiment_clicked.emit)
        self.sentiment_button.setEnabled(False)
        layout.addWidget(self.sentiment_button)
        
        # Fill in gaps in reasoning
        self.fill_gaps_button = QPushButton("Fill Gaps in Reasoning")
        self.fill_gaps_button.setFont(FontManager.get_font(12, QFont.Weight.Light))
        self.fill_gaps_button.clicked.connect(self.fill_gaps_clicked.emit)
        self.fill_gaps_button.setEnabled(False)
        layout.addWidget(self.fill_gaps_button)
        
        # Brainstorm
        self.brainstorm_button = QPushButton("Brainstorm Questions")
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
        self.fact_check_button = QPushButton("Fact Check Transcript")
        self.fact_check_button.setFont(FontManager.get_font(12, QFont.Weight.Light))
        self.fact_check_button.clicked.connect(self.fact_check_clicked.emit)
        self.fact_check_button.setEnabled(False)
        layout.addWidget(self.fact_check_button)
        
        # Spacer
        layout.addSpacing(20)
        
        # Buffer info section
        buffer_label = QLabel("Buffer Status")
        buffer_label.setFont(FontManager.get_font(14, QFont.Weight.Normal))
        layout.addWidget(buffer_label)
        
        # Buffer progress bar
        self.buffer_progress = QProgressBar()
        self.buffer_progress.setRange(0, 100)
        self.buffer_progress.setValue(0)
        layout.addWidget(self.buffer_progress)
        
        # Buffer info text
        self.buffer_info = QLabel("Buffer: 0 seconds / 0 minutes")
        self.buffer_info.setFont(FontManager.get_font(12, QFont.Weight.Normal))
        layout.addWidget(self.buffer_info)
        
        # Add stretch at the bottom
        layout.addStretch()
    
    def set_recording_active(self, is_recording):
        """Update UI for recording state"""
        if is_recording:
            self.record_button.setText("Stop Recording")
            self.save_button.setEnabled(True)
            self.transcribe_button.setEnabled(True)
        else:
            self.record_button.setText("Start Recording")
    
    def set_prompt_buttons_enabled(self, enabled):
        """Enable or disable all prompt buttons"""
        self.topic_button.setEnabled(enabled)
        self.insights_button.setEnabled(enabled)
        self.summary_button.setEnabled(enabled)
        self.questions_button.setEnabled(enabled)
        self.sentiment_button.setEnabled(enabled)
        self.fill_gaps_button.setEnabled(enabled)
        self.brainstorm_button.setEnabled(enabled)
        self.company_fit_button.setEnabled(enabled)
        self.fact_check_button.setEnabled(enabled)
    
    def update_buffer_info(self, seconds, max_minutes):
        """Update buffer information display"""
        minutes = seconds / 60
        progress = min(100, int((seconds / (max_minutes * 60)) * 100))
        
        self.buffer_progress.setValue(progress)
        self.buffer_info.setText(f"Buffer: {seconds:.1f} seconds / {minutes:.2f} minutes")