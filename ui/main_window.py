import json
import threading
from datetime import datetime

from PyQt6.QtWidgets import (QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, 
                           QLabel, QSplitter, QMessageBox, QInputDialog, QLineEdit)
from PyQt6.QtCore import Qt, QTimer, pyqtSignal, pyqtSlot
from PyQt6.QtGui import QFont, QPixmap, QIcon

import config
from audio.recorder import ContinuousRecorder
from api.client import ApiClient
from ui.controls_panel import ControlsPanel
from ui.output_panel import OutputPanel
from ui.animated_label import AnimatedLabel
from ui.font_manager import FontManager
# Explicit imports from prompts.templates
from prompts.templates import (
    PRACTITIONER_INSIGHTS_STREAMING_PROMPT,
    MEETING_SUMMARY_PROMPT,
    FILL_IN_GAPS_PROMPT,
    BRAINSTORM_PROMPT,
    COMPANY_FIT_PROMPT,
    FACT_CHECKING_PROMPT,
    FOLLOW_UP_QUESTIONS_PROMPT,
    SENTIMENT_ANALYSIS_PROMPT,
    TOPIC_SUMMARY_PROMPT,
    ANSWER_QUESTION_PROMPT
)
# Import from new logic_templates file
from prompts.logic_templates import PROBLEM_SOLVING_PROMPT, SCQA_PROMPT, HYPOTHESIS_DRIVEN_PROMPT, FIRST_PRINCIPLES_PROMPT, REFRAMING_PROMPT

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

        # Load fonts
        FontManager.load_fonts()

        # Set application icon
        app_icon = QIcon("assets/Darin_ICON.png")
        self.setWindowIcon(app_icon)
            
        # Initialize components
        self.recorder = ContinuousRecorder(buffer_minutes=config.BUFFER_MINUTES)
        self.api_client = ApiClient()
        self.current_transcript = ""
        self.is_processing = False  # Track if we're currently processing
        
        # HTML streaming state
        self._html_buffer = ""  # Buffer for accumulating HTML chunks
        self._current_element = None  # Track the current HTML element being built
        self._element_stack = []  # Stack to track nested HTML elements
        self._is_first_update = True  # Track if this is the first stream update
        self._current_list_items = []  # Track list items for the current section
        self._template_type = None # Track the current template type

        # Sentiment analysis specific state
        self._overall_sentiment_received = False
        
        # Setup UI
        self.setup_ui()
        
        # Connect signals to slots
        self.setup_connections()
    
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
        self.content_splitter.setHandleWidth(1)  # Make splitter handle less visible
        
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
        footer.setAlignment(Qt.AlignmentFlag.AlignCenter)
        footer.setStyleSheet("color: #666666; font-size: 11px;")
        main_layout.addWidget(footer)
    
    def setup_connections(self):
        # Connect control panel signals
        self.controls_panel.record_clicked.connect(self.toggle_recording)
        self.controls_panel.transcribe_clicked.connect(self.transcribe_buffer)
        self.controls_panel.transcribe_last_30_clicked.connect(self.transcribe_last_30_seconds)
        self.controls_panel.clear_output_clicked.connect(self.clear_output)
        
        # Original prompt buttons
        self.controls_panel.topics_clicked.connect(lambda: self.run_prompt_with_auto_transcribe(TOPIC_SUMMARY_PROMPT, title="Key Topics"))
        self.controls_panel.insights_clicked.connect(lambda: self.run_prompt_with_auto_transcribe(PRACTITIONER_INSIGHTS_STREAMING_PROMPT, title="Banking Practitioner Insights"))
        self.controls_panel.summary_clicked.connect(lambda: self.run_prompt_with_auto_transcribe(MEETING_SUMMARY_PROMPT, title="Meeting Summary"))
        self.controls_panel.questions_clicked.connect(lambda: self.run_prompt_with_auto_transcribe(FOLLOW_UP_QUESTIONS_PROMPT, title="Follow-up Questions"))
        self.controls_panel.sentiment_clicked.connect(lambda: self.run_prompt_with_auto_transcribe(SENTIMENT_ANALYSIS_PROMPT, title="Sentiment Analysis"))
        
        # New prompt buttons
        self.controls_panel.fill_gaps_clicked.connect(lambda: self.run_prompt_with_auto_transcribe(FILL_IN_GAPS_PROMPT, title="Gaps in Reasoning"))
        self.controls_panel.brainstorm_clicked.connect(lambda: self.run_prompt_with_auto_transcribe(BRAINSTORM_PROMPT, title="Brainstorm Questions"))
        self.controls_panel.company_fit_clicked.connect(lambda: self.run_prompt_with_auto_transcribe(COMPANY_FIT_PROMPT, title="SAS Viya Alignment"))
        self.controls_panel.fact_check_clicked.connect(lambda: self.run_prompt_with_auto_transcribe(FACT_CHECKING_PROMPT, title="Fact Check Analysis"))
        self.controls_panel.answer_question_clicked.connect(lambda: self.run_prompt_with_auto_transcribe(ANSWER_QUESTION_PROMPT, title="Answer Question"))
        self.controls_panel.problem_solving_clicked.connect(lambda: self.run_prompt_with_auto_transcribe(PROBLEM_SOLVING_PROMPT, title="Issue Tree Logic"))
        self.controls_panel.scqa_clicked.connect(lambda: self.run_prompt_with_auto_transcribe(SCQA_PROMPT, title="SCQA Framework"))
        self.controls_panel.hypothesis_driven_clicked.connect(lambda: self.run_prompt_with_auto_transcribe(HYPOTHESIS_DRIVEN_PROMPT, title="Hypothesis Thinking"))
        self.controls_panel.first_principles_clicked.connect(lambda: self.run_prompt_with_auto_transcribe(FIRST_PRINCIPLES_PROMPT, title="First Principles"))
        self.controls_panel.reframing_clicked.connect(lambda: self.run_prompt_with_auto_transcribe(REFRAMING_PROMPT, title="Reframing"))
        
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
            if self.recorder.start_recording():
                self.recording_started.emit()
                # Update UI to show recording state
                self.controls_panel.set_recording_active(True)
        else:
            # Stop recording
            if self.recorder.stop_recording():
                self.recording_stopped.emit()
                # Update UI to show stopped state
                self.controls_panel.set_recording_active(False)
    
    def transcribe_buffer(self):
        """Transcribe the current audio buffer"""
        # Disable button to prevent multiple clicks
        self.controls_panel.transcribe_button.setEnabled(False)
        self.controls_panel.transcribe_button.setText("Transcribing...")
        
        # Get audio data from buffer
        audio_data = self.recorder.save_buffer()
        
        if audio_data is None:
            self.controls_panel.transcribe_button.setText("Transcribe Buffer")
            self.controls_panel.transcribe_button.setEnabled(True)
            QMessageBox.warning(self, "Transcription Error", "No audio in buffer to transcribe")
            return
        
        # Start transcription in a separate thread
        threading.Thread(target=self._transcribe_thread, 
                        args=(audio_data, self.recorder.sample_rate)).start()
    
    def _transcribe_thread(self, audio_data, sample_rate):
        """Background thread for transcription"""
        try:
            text = self.api_client.transcribe_with_deepgram(audio_data, sample_rate)
            self.current_transcript = text
            self.transcription_complete.emit(text)
        except Exception as e:
            self.transcription_complete.emit(f"Transcription error: {str(e)}")
    
    def run_prompt_with_auto_transcribe(self, prompt_template=None, title=None):
        """Auto transcribe and then run a specific prompt"""
        if self.is_processing:
            return
            
        self.is_processing = True
        
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
        if self.current_transcript:
            self._run_specific_prompt(self.current_transcript, prompt_template)
            return
            
        # Otherwise get audio data
        audio_data = None # Initialize audio_data
        # For specific prompts, only use last 30s if no transcript exists
        use_last_30s = prompt_template in [PRACTITIONER_INSIGHTS_STREAMING_PROMPT, ANSWER_QUESTION_PROMPT]
        
        if use_last_30s and not self.current_transcript:
            audio_data = self.recorder.get_last_n_seconds(30)
            if audio_data is None:
                QMessageBox.warning(self, "Processing Error", "Not enough audio (last 30s) in buffer to process")
                self.controls_panel.set_prompt_buttons_enabled(True)
                self.is_processing = False
                return # Return early if 30s failed
        
        # If we didn't get 30s audio (either not applicable or it succeeded but we proceed),
        # get the full buffer instead.
        if audio_data is None: # This means we need the full buffer
            audio_data = self.recorder.save_buffer()
            if audio_data is None:
                 # Check if getting the full buffer failed
                 QMessageBox.warning(self, "Processing Error", "No audio in buffer to process")
                 self.controls_panel.set_prompt_buttons_enabled(True)
                 self.is_processing = False
                 return # Return early if full buffer failed
        
        # We should now have valid audio_data (either 30s or full buffer)
        # Start transcription and processing in a separate thread
        threading.Thread(
            target=self._transcribe_and_process_thread, 
            args=(audio_data, self.recorder.sample_rate, prompt_template)
        ).start()
    
    def _transcribe_and_process_thread(self, audio_data, sample_rate, prompt_template):
        """Background thread for transcription followed by processing with a specific prompt"""
        try:
            # First transcribe
            self.progress_update.emit("Transcribing audio...")
            text = self.api_client.transcribe_with_deepgram(audio_data, sample_rate)
            self.current_transcript = text
            
            # Update UI with transcript
            self.transcription_complete.emit(text)
            
            # Then process with the specific prompt
            self._run_specific_prompt(text, prompt_template)
        except Exception as e:
            self.processing_complete.emit({"error": str(e)})
        finally:
            self.is_processing = False
    
    def _run_specific_prompt(self, transcript, prompt_template):
        """Process transcript with a specific prompt template"""
        try:
            # Update output to show progress
            self.progress_update.emit("Processing with Claude...")
            
            # Set up the static template based on the prompt type
            template_type = self._setup_static_template(prompt_template)
            
            # Reset HTML streaming state for new dynamic content
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
                transcript, 
                prompt_template,
                stream=True,
                callback=handle_stream
            )
            
            # Final update with complete response
            self.processing_complete.emit({"result": result})
        except Exception as e:
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
        # Display transcript in the output panel
        self.output_panel.set_output(f"<div class='transcript-text'>{text}</div>")
        
        # Reset both transcribe buttons
        self.controls_panel.transcribe_button.setText("Transcribe Buffer")
        self.controls_panel.transcribe_button.setEnabled(True)
        self.controls_panel.transcribe_last_30_button.setText("Transcribe Last 30s")
        self.controls_panel.transcribe_last_30_button.setEnabled(True)
        
        # Enable all prompt buttons when we have a transcript
        self.controls_panel.set_prompt_buttons_enabled(True)
    
    @pyqtSlot(dict)
    def on_processing_complete(self, result):
        if "error" in result:
            # Show error using template
            self.output_panel.set_error(result["error"])
        elif "result" in result:
            # For specific streaming types, we don't want to overwrite our formatted content
            # as the final output might be raw text without the template structure.
            if not hasattr(self, '_template_type') or self._template_type not in ["follow-up-questions", "sentiment-analysis", "meeting-summary", "practitioner-insights", "topic-summary", "fill-gaps", "brainstorm", "company-fit", "fact-check", "answer-question", "problem-solving", "scqa", "hypothesis-driven", "first-principles", "reframing"]:
                # Show result text for other non-streaming or differently handled types
                self.output_panel.set_output(result["result"])
        else:
            # Format the result as a topic section
            content = json.dumps(result, indent=2)
            self.output_panel.set_output(create_topic_section("Processing Results", f"<pre>{content}</pre>"))
        
        # Re-enable prompt buttons
        self.controls_panel.set_prompt_buttons_enabled(True)
    
    def _process_html_chunk(self, chunk):
        """Process a chunk of HTML text and return complete elements if found."""
        self._html_buffer += chunk
        
        # Look for complete HTML elements
        while True:
            # If we don't have a current element, look for the start of one
            if not self._current_element:
                # Find the next opening tag for a topic section
                start_idx = self._html_buffer.find("<div class=\"topic-section\">")
                if start_idx == -1:
                    # If no topic section, look for individual list items
                    item_start = self._html_buffer.find("<li class=\"insight-item\">")
                    if item_start != -1:
                        item_end = self._html_buffer.find("</li>", item_start)
                        if item_end != -1:
                            # Extract the complete list item
                            item = self._html_buffer[item_start:item_end + 5]
                            # Remove the processed item from buffer
                            self._html_buffer = self._html_buffer[:item_start] + self._html_buffer[item_end + 5:]
                            return item
                    break  # No new elements found
                
                # Found a topic section, extract the title if present
                title_start = self._html_buffer.find("<h2 class=\"topic-title\">", start_idx)
                title_end = self._html_buffer.find("</h2>", title_start) if title_start != -1 else -1
                
                if title_start != -1 and title_end != -1:
                    # Found a title, extract the complete section
                    section_end = self._html_buffer.find("</div>", title_end)
                    if section_end != -1:
                        # Extract the complete section
                        section = self._html_buffer[start_idx:section_end + 6]
                        # Remove the processed section from buffer
                        self._html_buffer = self._html_buffer[:start_idx] + self._html_buffer[section_end + 6:]
                        return section
                    else:
                        # Title found but section not complete
                        self._current_element = {
                            "type": "topic-section",
                            "title": self._html_buffer[title_start + len("<h2 class=\"topic-title\">"):title_end].strip()
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
                    complete_element = self._html_buffer[:end_idx + 6]
                    self._html_buffer = self._html_buffer[end_idx + 6:]
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
        
        # Handle follow-up questions streaming
        if hasattr(self, '_template_type') and self._template_type == "follow-up-questions":
            self._html_buffer += text
            while True:
                item_start = self._html_buffer.find("<li")
                if item_start == -1:
                    break
                item_end = self._html_buffer.find("</li>", item_start)
                if item_end == -1:
                    break
                    
                item = self._html_buffer[item_start:item_end + 5]
                self._html_buffer = self._html_buffer[item_start + len(item):]

                # Add formatting if needed (ensure class and style)
                if "class=" not in item:
                    item = item.replace("<li", '<li class="insight-item" style="display: list-item !important; list-style-type: disc !important; font-weight: bold !important;"')
                elif 'style="' not in item:
                    item = item.replace('class="', 'class="insight-item" style="display: list-item !important; list-style-type: disc !important; font-weight: bold !important;"')

                self.output_panel.append_to_dynamic_content(item)
        
        # Handle sentiment analysis streaming
        elif hasattr(self, '_template_type') and self._template_type == "sentiment-analysis":
            if not self._overall_sentiment_received:
                # First line should be the overall sentiment
                lines = text.split('\n', 1)
                overall_sentiment = lines[0].strip()
                if overall_sentiment in ["Positive", "Negative", "Neutral"]:
                    self.output_panel.set_overall_sentiment(overall_sentiment)
                    self._overall_sentiment_received = True
                    # Process the rest of the text if any
                    if len(lines) > 1:
                        text = lines[1]
                    else:
                        return # Wait for next chunk
                else:
                    # If first line isn't sentiment, buffer it for list item processing
                    pass # Fall through to list item processing

            # Process subsequent lines as list items
            self._html_buffer += text
            while True:
                item_start = self._html_buffer.find("<li")
                if item_start == -1:
                    break
                item_end = self._html_buffer.find("</li>", item_start)
                if item_end == -1:
                    break
                    
                item = self._html_buffer[item_start:item_end + 5]
                self._html_buffer = self._html_buffer[item_start + len(item):]

                # Add formatting if needed (ensure class and style)
                if "class=" not in item:
                    item = item.replace("<li", '<li class="insight-item" style="display: list-item !important; list-style-type: disc !important; font-weight: bold !important;"')
                elif 'style="' not in item:
                    item = item.replace('class="', 'class="insight-item" style="display: list-item !important; list-style-type: disc !important; font-weight: bold !important;"')

                self.output_panel.append_to_dynamic_content(item)

        # Handle meeting summary streaming
        elif hasattr(self, '_template_type') and self._template_type == "meeting-summary":
            self._html_buffer += text
            while True:
                item_start = self._html_buffer.find("<li")
                if item_start == -1:
                    break
                item_end = self._html_buffer.find("</li>", item_start)
                if item_end == -1:
                    break
                    
                item = self._html_buffer[item_start:item_end + 5]
                self._html_buffer = self._html_buffer[item_start + len(item):]

                # Add formatting if needed (ensure class and style, no bold)
                if "class=" not in item:
                    item = item.replace("<li", '<li class="insight-item" style="display: list-item !important; list-style-type: disc !important;"')
                elif 'style="' not in item:
                    item = item.replace('class="', 'class="insight-item" style="display: list-item !important; list-style-type: disc !important;"')

                self.output_panel.append_to_dynamic_content(item)

        # Handle practitioner insights streaming
        elif hasattr(self, '_template_type') and self._template_type == "practitioner-insights":
            self._html_buffer += text
            while True:
                item_start = self._html_buffer.find("<li")
                if item_start == -1:
                    break
                item_end = self._html_buffer.find("</li>", item_start)
                if item_end == -1:
                    break
                    
                item = self._html_buffer[item_start:item_end + 5]
                self._html_buffer = self._html_buffer[item_start + len(item):]

                # Add formatting if needed (ensure class and style, no bold)
                if "class=" not in item:
                    item = item.replace("<li", '<li class="insight-item" style="display: list-item !important; list-style-type: disc !important;"')
                elif 'style="' not in item:
                    item = item.replace('class="', 'class="insight-item" style="display: list-item !important; list-style-type: disc !important;"')
                
                self.output_panel.append_to_dynamic_content(item)

        # Handle topic summary streaming
        elif hasattr(self, '_template_type') and self._template_type == "topic-summary":
            self._html_buffer += text
            while True:
                item_start = self._html_buffer.find("<li")
                if item_start == -1:
                    break
                item_end = self._html_buffer.find("</li>", item_start)
                if item_end == -1:
                    break
                    
                item = self._html_buffer[item_start:item_end + 5]
                self._html_buffer = self._html_buffer[item_start + len(item):]

                # Add formatting if needed (ensure class and style, no bold)
                if "class=" not in item:
                    item = item.replace("<li", '<li class="insight-item" style="display: list-item !important; list-style-type: disc !important;"')
                elif 'style="' not in item:
                    item = item.replace('class="', 'class="insight-item" style="display: list-item !important; list-style-type: disc !important;"')

                self.output_panel.append_to_dynamic_content(item)

        # Handle Fill Gaps streaming
        elif hasattr(self, '_template_type') and self._template_type == "fill-gaps":
            self._html_buffer += text
            while True:
                item_start = self._html_buffer.find("<li")
                if item_start == -1:
                    break
                item_end = self._html_buffer.find("</li>", item_start)
                if item_end == -1:
                    break
                    
                item = self._html_buffer[item_start:item_end + 5]
                self._html_buffer = self._html_buffer[item_start + len(item):]

                # Determine target list based on class
                target_list_id = None
                if 'class="core-thinking"' in item:
                    target_list_id = "core-thinking-list"
                elif 'class="gap-item"' in item:
                    target_list_id = "gaps-list"
                elif 'class="recommendation-item"' in item:
                    target_list_id = "recommendations-list"
                
                if target_list_id:
                    # Use the new method to append to the correct list
                    self.output_panel.append_to_list_by_id(target_list_id, item)

        # Handle Brainstorm Questions streaming
        elif hasattr(self, '_template_type') and self._template_type == "brainstorm":
            self._html_buffer += text
            while True:
                item_start = self._html_buffer.find("<li")
                if item_start == -1:
                    break
                item_end = self._html_buffer.find("</li>", item_start)
                if item_end == -1:
                    break
                    
                item = self._html_buffer[item_start:item_end + 5]
                self._html_buffer = self._html_buffer[item_start + len(item):]

                # Determine target list based on class
                target_list_id = None
                if 'class="challenge-question"' in item:
                    target_list_id = "challenge-questions-list"
                elif 'class="alternative-frame"' in item:
                    target_list_id = "alternative-frames-list"
                elif 'class="provocative-idea"' in item:
                    target_list_id = "provocative-ideas-list"
                
                if target_list_id:
                    # Use the method to append to the correct list (non-bold)
                    self.output_panel.append_to_list_by_id(target_list_id, item)

        # Handle Company Fit streaming
        elif hasattr(self, '_template_type') and self._template_type == "company-fit":
            self._html_buffer += text
            while True:
                item_start = self._html_buffer.find("<li")
                if item_start == -1:
                    break
                item_end = self._html_buffer.find("</li>", item_start)
                if item_end == -1:
                    break
                    
                item = self._html_buffer[item_start:item_end + 5]
                self._html_buffer = self._html_buffer[item_start + len(item):]

                # Determine target list based on class
                target_list_id = None
                if 'class="key-topic"' in item:
                    target_list_id = "key-topics-list"
                elif 'class="viya-connection"' in item:
                    target_list_id = "viya-connections-list"
                elif 'class="missing-consideration"' in item:
                    target_list_id = "missing-considerations-list"
                
                if target_list_id:
                    # Use the method to append to the correct list (non-bold)
                    self.output_panel.append_to_list_by_id(target_list_id, item)

        # Handle Fact Checking streaming
        elif hasattr(self, '_template_type') and self._template_type == "fact-check":
            self._html_buffer += text
            while True:
                # Fact check items can be multi-line, look for the start and end <li> tags
                item_start = self._html_buffer.find("<li class=\"fact-check-item\">") 
                if item_start == -1:
                    item_start = self._html_buffer.find("<li class='fact-check-item'>") # Check single quotes too
                    if item_start == -1:
                       break # No start tag found

                item_end = self._html_buffer.find("</li>", item_start)
                if item_end == -1:
                    break # End tag not found yet
                    
                item = self._html_buffer[item_start : item_end + 5]
                self._html_buffer = self._html_buffer[item_end + 5 :]

                # Append the complete item to the fact-check list
                self.output_panel.append_to_list_by_id("fact-check-list", item)

        # Handle Answer Question streaming
        elif hasattr(self, '_template_type') and self._template_type == "answer-question":
            self._html_buffer += text
            while True:
                # Find the start of any relevant list item
                item_start = -1
                possible_classes = ["answer-item", "rationale-item", "example-item"]
                start_positions = {}
                for cls in possible_classes:
                    pos_double = self._html_buffer.find(f'<li class="{cls}">')
                    pos_single = self._html_buffer.find(f"<li class='{cls}'>")
                    if pos_double != -1:
                        start_positions[pos_double] = cls
                    if pos_single != -1:
                        start_positions[pos_single] = cls
                
                if not start_positions:
                    break # No relevant item start found
                
                # Find the earliest starting position
                item_start = min(start_positions.keys())
                item_class = start_positions[item_start]

                item_end = self._html_buffer.find("</li>", item_start)
                if item_end == -1:
                    break # No end tag yet
                    
                item = self._html_buffer[item_start : item_end + 5]
                self._html_buffer = self._html_buffer[item_end + 5 :]

                # Determine target list based on class
                target_list_id = None
                if item_class == "answer-item":
                    target_list_id = "answer-list"
                elif item_class == "rationale-item":
                    target_list_id = "rationale-list"
                elif item_class == "example-item":
                    target_list_id = "examples-list"

                # Append the complete item to the correct list
                if target_list_id:
                    self.output_panel.append_to_list_by_id(target_list_id, item)

        # Handle Problem Solving / Issue Tree Logic streaming
        elif hasattr(self, '_template_type') and self._template_type == "problem-solving":
            self._html_buffer += text
            while True:
                # Find the start of any relevant list item
                item_start = -1
                possible_classes = [
                    "core-problem", "logic-tree-component", 
                    "evaluation-mece", "evaluation-assumption", "evaluation-logic", "evaluation-data",
                    "challenge-weakness", "challenge-question", "challenge-reframe"
                ]
                start_positions = {}
                for cls in possible_classes:
                    # Check for class="cls" and class='cls'
                    pos_double = self._html_buffer.find(f'<li class="{cls}">')
                    pos_single = self._html_buffer.find(f'<li class=\'{cls}\'>') # Use \ to escape single quote in f-string
                    
                    current_pos = -1
                    if pos_double != -1 and (current_pos == -1 or pos_double < current_pos):
                        current_pos = pos_double
                    if pos_single != -1 and (current_pos == -1 or pos_single < current_pos):
                        current_pos = pos_single
                        
                    if current_pos != -1:
                         # Store the earliest found position for this class
                         if cls not in start_positions or current_pos < start_positions[cls][0]:
                              start_positions[cls] = (current_pos, cls)
                
                if not start_positions:
                    break # No relevant item start found
                
                # Find the earliest starting position among all found classes
                earliest_pos = -1
                item_class = None
                for cls, (pos, _) in start_positions.items():
                     if earliest_pos == -1 or pos < earliest_pos:
                          earliest_pos = pos
                          item_class = cls
                
                item_start = earliest_pos
                if item_start == -1: # Should not happen if start_positions is not empty
                     break

                item_end = self._html_buffer.find("</li>", item_start)
                if item_end == -1:
                    break # No end tag yet
                    
                item = self._html_buffer[item_start : item_end + 5]
                self._html_buffer = self._html_buffer[item_end + 5 :]

                # Determine target list based on class
                target_list_id = None
                if item_class == "core-problem":
                    target_list_id = "core-problem-list"
                elif item_class == "logic-tree-component":
                    target_list_id = "logic-tree-list"
                elif item_class in ["evaluation-mece", "evaluation-assumption", "evaluation-logic", "evaluation-data"]:
                    target_list_id = "evaluation-list"
                elif item_class in ["challenge-weakness", "challenge-question", "challenge-reframe"]:
                    target_list_id = "challenge-list"

                # Append the complete item to the correct list
                if target_list_id:
                    self.output_panel.append_to_list_by_id(target_list_id, item)

        # Handle SCQA Framework streaming
        elif hasattr(self, '_template_type') and self._template_type == "scqa":
            self._html_buffer += text
            while True:
                # Find the start of any relevant list item
                item_start = -1
                possible_classes = [
                    "scqa-situation", "scqa-complication", "scqa-question", 
                    "scqa-answer", "scqa-assessment", "scqa-roadmap"
                ]
                start_positions = {}
                for cls in possible_classes:
                    # Check for class="cls" and class='cls'
                    pos_double = self._html_buffer.find(f'<li class="{cls}">')
                    pos_single = self._html_buffer.find(f'<li class=\'{cls}\'>')
                    
                    current_pos = -1
                    if pos_double != -1 and (current_pos == -1 or pos_double < current_pos):
                        current_pos = pos_double
                    if pos_single != -1 and (current_pos == -1 or pos_single < current_pos):
                        current_pos = pos_single
                        
                    if current_pos != -1:
                         if cls not in start_positions or current_pos < start_positions[cls][0]:
                              start_positions[cls] = (current_pos, cls)
                
                if not start_positions:
                    break # No relevant item start found
                
                earliest_pos = -1
                item_class = None
                for cls, (pos, _) in start_positions.items():
                     if earliest_pos == -1 or pos < earliest_pos:
                          earliest_pos = pos
                          item_class = cls
                
                item_start = earliest_pos
                if item_start == -1: break

                item_end = self._html_buffer.find("</li>", item_start)
                if item_end == -1:
                    break # No end tag yet
                    
                item = self._html_buffer[item_start : item_end + 5]
                self._html_buffer = self._html_buffer[item_end + 5 :]

                # Determine target list based on class
                target_list_id = f"{item_class}-list" # Map class directly to list ID

                # Append the complete item to the correct list
                if target_list_id:
                    self.output_panel.append_to_list_by_id(target_list_id, item)

        # Handle Hypothesis Driven Thinking streaming
        elif hasattr(self, '_template_type') and self._template_type == "hypothesis-driven":
            self._html_buffer += text
            while True:
                # Find the start of any relevant list item
                item_start = -1
                possible_classes = [
                    "hypothesis-problem", "hypothesis-hypothesis", 
                    "hypothesis-evidence-support", "hypothesis-evidence-contradict", "hypothesis-evidence-missing",
                    "hypothesis-priority", "hypothesis-testing", "hypothesis-decision", "hypothesis-assessment"
                ]
                start_positions = {}
                for cls in possible_classes:
                    # Check for class="cls" and class='cls'
                    pos_double = self._html_buffer.find(f'<li class="{cls}">')
                    pos_single = self._html_buffer.find(f'<li class=\'{cls}\'>')
                    
                    current_pos = -1
                    if pos_double != -1 and (current_pos == -1 or pos_double < current_pos):
                        current_pos = pos_double
                    if pos_single != -1 and (current_pos == -1 or pos_single < current_pos):
                        current_pos = pos_single
                        
                    if current_pos != -1:
                         if cls not in start_positions or current_pos < start_positions[cls][0]:
                              start_positions[cls] = (current_pos, cls)
                
                if not start_positions:
                    break # No relevant item start found
                
                earliest_pos = -1
                item_class = None
                for cls, (pos, _) in start_positions.items():
                     if earliest_pos == -1 or pos < earliest_pos:
                          earliest_pos = pos
                          item_class = cls
                
                item_start = earliest_pos
                if item_start == -1: break

                item_end = self._html_buffer.find("</li>", item_start)
                if item_end == -1:
                    break # No end tag yet
                    
                item = self._html_buffer[item_start : item_end + 5]
                self._html_buffer = self._html_buffer[item_end + 5 :]

                # Determine target list based on class
                target_list_id = None
                if item_class == "hypothesis-problem": target_list_id = "hypothesis-problem-list"
                elif item_class == "hypothesis-hypothesis": target_list_id = "hypothesis-hypothesis-list"
                elif item_class in ["hypothesis-evidence-support", "hypothesis-evidence-contradict", "hypothesis-evidence-missing"]: target_list_id = "hypothesis-evidence-list"
                elif item_class == "hypothesis-priority": target_list_id = "hypothesis-priority-list"
                elif item_class == "hypothesis-testing": target_list_id = "hypothesis-testing-list"
                elif item_class == "hypothesis-decision": target_list_id = "hypothesis-decision-list"
                elif item_class == "hypothesis-assessment": target_list_id = "hypothesis-assessment-list"

                # Append the complete item to the correct list
                if target_list_id:
                    self.output_panel.append_to_list_by_id(target_list_id, item)

        # Handle First Principles Thinking streaming
        elif hasattr(self, '_template_type') and self._template_type == "first-principles":
            self._html_buffer += text
            while True:
                # Find the start of any relevant list item
                item_start = -1
                possible_classes = [
                    "fp-conventional", "fp-fundamental", "fp-assumption", 
                    "fp-rebuild", "fp-insight", "fp-implementation", "fp-metacognitive"
                ]
                start_positions = {}
                for cls in possible_classes:
                    # Check for class="cls" and class='cls'
                    pos_double = self._html_buffer.find(f'<li class="{cls}">')
                    pos_single = self._html_buffer.find(f'<li class=\'{cls}\'>')
                    
                    current_pos = -1
                    if pos_double != -1 and (current_pos == -1 or pos_double < current_pos):
                        current_pos = pos_double
                    if pos_single != -1 and (current_pos == -1 or pos_single < current_pos):
                        current_pos = pos_single
                        
                    if current_pos != -1:
                         if cls not in start_positions or current_pos < start_positions[cls][0]:
                              start_positions[cls] = (current_pos, cls)
                
                if not start_positions:
                    break # No relevant item start found
                
                earliest_pos = -1
                item_class = None
                for cls, (pos, _) in start_positions.items():
                     if earliest_pos == -1 or pos < earliest_pos:
                          earliest_pos = pos
                          item_class = cls
                
                item_start = earliest_pos
                if item_start == -1: break

                item_end = self._html_buffer.find("</li>", item_start)
                if item_end == -1:
                    break # No end tag yet
                    
                item = self._html_buffer[item_start : item_end + 5]
                self._html_buffer = self._html_buffer[item_end + 5 :]

                # Determine target list based on class (map class directly to list ID)
                target_list_id = f"{item_class}-list"

                # Append the complete item to the correct list
                if target_list_id:
                    self.output_panel.append_to_list_by_id(target_list_id, item)

        # Handle Reframing streaming
        elif hasattr(self, '_template_type') and self._template_type == "reframing":
            self._html_buffer += text
            while True:
                # Find the start of any relevant list item
                item_start = -1
                possible_classes = ["reframing-statement", "reframing-point"]
                start_positions = {}
                for cls in possible_classes:
                    # Check for class="cls" and class='cls'
                    pos_double = self._html_buffer.find(f'<li class="{cls}">')
                    pos_single = self._html_buffer.find(f'<li class=\'{cls}\'>')
                    
                    current_pos = -1
                    if pos_double != -1 and (current_pos == -1 or pos_double < current_pos):
                        current_pos = pos_double
                    if pos_single != -1 and (current_pos == -1 or pos_single < current_pos):
                        current_pos = pos_single
                        
                    if current_pos != -1:
                         if cls not in start_positions or current_pos < start_positions[cls][0]:
                              start_positions[cls] = (current_pos, cls)
                
                if not start_positions:
                    break # No relevant item start found
                
                earliest_pos = -1
                item_class = None
                for cls, (pos, _) in start_positions.items():
                     if earliest_pos == -1 or pos < earliest_pos:
                          earliest_pos = pos
                          item_class = cls
                
                item_start = earliest_pos
                if item_start == -1: break

                item_end = self._html_buffer.find("</li>", item_start)
                if item_end == -1:
                    break # No end tag yet
                    
                item = self._html_buffer[item_start : item_end + 5]
                self._html_buffer = self._html_buffer[item_end + 5 :]

                # Determine target list based on class
                target_list_id = f"{item_class}-list" # Map class directly to list ID

                # Append the complete item to the correct list
                if target_list_id:
                    self.output_panel.append_to_list_by_id(target_list_id, item)

            # Default behavior for other template types
        else:
            complete_element = self._process_html_chunk(text)
            if complete_element:
                # If this is the first update, set the output
                if self._is_first_update:
                    self.output_panel.set_output(complete_element)
                    self._is_first_update = False
                else:
                    # For subsequent elements, we want to append only new content
                    # First, check if this is a new section or a list item
                    if complete_element.startswith("<div class=\"topic-section\">"):
                        # This is a new section, append it
                        self.output_panel.append_output(complete_element)
                    elif complete_element.startswith("<li class=\"insight-item\">"):
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
        self.output_panel.set_status(message)

    def clear_output(self):
        """Clear the output panel and reset HTML streaming state"""
        self.output_panel.set_output("")
        self.output_panel.set_title("Output")  # Reset title to default
        self.current_transcript = ""
        self._html_buffer = ""
        self._current_element = None
        self._element_stack = []
        self._is_first_update = True
        self._current_list_items = []
        self._overall_sentiment_received = False # Reset sentiment flag

    def transcribe_last_30_seconds(self):
        """Transcribe only the last 30 seconds of audio"""
        # Disable button to prevent multiple clicks
        self.controls_panel.transcribe_last_30_button.setEnabled(False)
        self.controls_panel.transcribe_last_30_button.setText("Transcribing...")
        
        # Get last 30 seconds of audio data
        audio_data = self.recorder.get_last_n_seconds(30)
        
        if audio_data is None:
            self.controls_panel.transcribe_last_30_button.setText("Transcribe Last 30s")
            self.controls_panel.transcribe_last_30_button.setEnabled(True)
            QMessageBox.warning(self, "Transcription Error", "Not enough audio in buffer")
            return
        
        # Start transcription in a separate thread
        threading.Thread(target=self._transcribe_thread, 
                        args=(audio_data, self.recorder.sample_rate)).start()