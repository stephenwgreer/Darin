import json
import threading
from datetime import datetime

from PyQt6.QtWidgets import (QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, 
                           QLabel, QSplitter, QMessageBox, QInputDialog, QLineEdit)
from PyQt6.QtCore import Qt, QTimer, pyqtSignal, pyqtSlot
from PyQt6.QtGui import QFont, QPixmap, QIcon

from audio.recorder import ContinuousRecorder
from api.client import ApiClient
from ui.controls_panel import ControlsPanel
from ui.output_panel import OutputPanel
from ui.animated_label import AnimatedLabel
from ui.font_manager import FontManager
from prompts.templates import *

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
        self.recorder = ContinuousRecorder(buffer_minutes=3)
        self.api_client = ApiClient()
        self.current_transcript = ""
        self.is_processing = False  # Track if we're currently processing
        
        # HTML streaming state
        self._html_buffer = ""  # Buffer for accumulating HTML chunks
        self._current_element = None  # Track the current HTML element being built
        self._element_stack = []  # Stack to track nested HTML elements
        self._is_first_update = True  # Track if this is the first stream update
        self._current_list_items = []  # Track list items for the current section
        
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
        
        ########################
        # Header section
        ########################
        header_widget = QWidget()
        header_layout = QHBoxLayout(header_widget)
        
        # Add logo on left
        logo_label = QLabel()
        small_logo = QPixmap("assets/Darin_Round.png")  # Create assets folder with your logo
        small_logo = small_logo.scaled(80, 80, Qt.AspectRatioMode.KeepAspectRatio)
        logo_label.setPixmap(small_logo)
        header_layout.addWidget(logo_label)
        
        # Add spacing between logo and title
        header_layout.addSpacing(10)
        
        # App title with typing animation
        app_title = AnimatedLabel("Welcome to Darin, your intern")
        header_layout.addWidget(app_title)
        
        header_layout.addStretch()
        
        main_layout.addWidget(header_widget)
        
        ########################
        # Content section with splitter
        ########################
        self.content_splitter = QSplitter(Qt.Orientation.Horizontal)
        self.content_splitter.setHandleWidth(5)  # Make splitter handle more visible
        
        # Left panel (controls)
        self.controls_panel = ControlsPanel()
        
        # Right panel (output)
        self.output_panel = OutputPanel()
        
        # Add panels to splitter
        self.content_splitter.addWidget(self.controls_panel)
        self.content_splitter.addWidget(self.output_panel)
        
        # Set the proportions
        self.content_splitter.setStretchFactor(0, 1)  # Controls take 1/3
        self.content_splitter.setStretchFactor(1, 2)  # Output takes 2/3
        
        main_layout.addWidget(self.content_splitter)
        
        # Footer
        footer = QLabel("© 2025 Darin Listening Assistant")
        footer.setAlignment(Qt.AlignmentFlag.AlignCenter)
        main_layout.addWidget(footer)
    
    def setup_connections(self):
        # Connect control panel signals
        self.controls_panel.record_clicked.connect(self.toggle_recording)
        self.controls_panel.transcribe_clicked.connect(self.transcribe_buffer)
        self.controls_panel.transcribe_last_30_clicked.connect(self.transcribe_last_30_seconds)
        self.controls_panel.clear_output_clicked.connect(self.clear_output)
        
        # Original prompt buttons
        self.controls_panel.topics_clicked.connect(lambda: self.run_prompt_with_auto_transcribe(TOPIC_SUMMARY_PROMPT))
        self.controls_panel.insights_clicked.connect(lambda: self.run_prompt_with_auto_transcribe(None, is_insights=True))
        self.controls_panel.summary_clicked.connect(lambda: self.run_prompt_with_auto_transcribe(MEETING_SUMMARY_PROMPT))
        self.controls_panel.questions_clicked.connect(lambda: self.run_prompt_with_auto_transcribe(FOLLOW_UP_QUESTIONS_PROMPT))
        self.controls_panel.sentiment_clicked.connect(lambda: self.run_prompt_with_auto_transcribe(SENTIMENT_ANALYSIS_PROMPT))
        
        # New prompt buttons
        self.controls_panel.fill_gaps_clicked.connect(lambda: self.run_prompt_with_auto_transcribe(FILL_IN_GAPS_PROMPT))
        self.controls_panel.brainstorm_clicked.connect(lambda: self.run_prompt_with_auto_transcribe(BRAINSTORM_PROMPT))
        self.controls_panel.company_fit_clicked.connect(lambda: self.run_prompt_with_auto_transcribe(COMPANY_FIT_PROMPT))
        self.controls_panel.fact_check_clicked.connect(lambda: self.run_prompt_with_auto_transcribe(FACT_CHECKING_PROMPT))
        
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
    
    def run_prompt_with_auto_transcribe(self, prompt_template=None, is_insights=False):
        """Auto transcribe and then run a specific prompt"""
        if self.is_processing:
            return
            
        self.is_processing = True
        
        # Disable all prompt buttons
        self.controls_panel.set_prompt_buttons_enabled(False)
        
        # Clear output before running new prompt
        self.clear_output()
        
        # Update output to show progress
        self.output_panel.set_output("Capturing audio and transcribing...")
        
        # If we already have a transcript, use it directly
        if self.current_transcript:
            if is_insights:
                self._run_practitioner_insights(self.current_transcript)
            else:
                self._run_specific_prompt(self.current_transcript, prompt_template)
            return
            
        # Otherwise get audio data from buffer
        audio_data = self.recorder.save_buffer()
        
        if audio_data is None:
            self.controls_panel.set_prompt_buttons_enabled(True)
            self.is_processing = False
            QMessageBox.warning(self, "Processing Error", "No audio in buffer to process")
            return
        
        # Start transcription and processing in a separate thread
        if is_insights:
            threading.Thread(
                target=self._transcribe_and_insights_thread, 
                args=(audio_data, self.recorder.sample_rate)
            ).start()
        else:
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
            self.is_processing = False
            
    def _transcribe_and_insights_thread(self, audio_data, sample_rate):
        """Background thread for transcription followed by practitioner insights"""
        try:
            # First transcribe
            self.progress_update.emit("Transcribing audio...")
            text = self.api_client.transcribe_with_deepgram(audio_data, sample_rate)
            self.current_transcript = text
            
            # Update UI with transcript
            self.transcription_complete.emit(text)
            
            # Then process for insights
            self._run_practitioner_insights(text)
        except Exception as e:
            self.processing_complete.emit({"error": str(e)})
            self.is_processing = False
    
    def _run_specific_prompt(self, transcript, prompt_template):
        """Process transcript with a specific prompt template"""
        try:
            # Update output to show progress
            self.progress_update.emit("Processing with Claude...")
            self.output_panel.set_output("")  # Clear the output
            
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
        finally:
            self.is_processing = False
    
    def _run_practitioner_insights(self, transcript):
        """Process transcript to get banking practitioner insights"""
        try:
            # Get client from API wrapper
            self.progress_update.emit("Extracting main topics...")
            self.output_panel.set_output("")  # Clear the output
            
            def handle_stream(text):
                """Callback to handle streaming text"""
                self.stream_update.emit(text)
            
            # Extract topics first
            topics_result = self.api_client.process_with_anthropic(
                transcript, 
                DEFAULT_TOPIC_EXTRACTION_PROMPT,
                stream=True,
                callback=handle_stream
            )
            
            # Parse topics from JSON with better error handling
            try:
                topics_data = json.loads(topics_result)
                
                # Verify we got a dictionary back
                if not isinstance(topics_data, dict):
                    self.progress_update.emit(f"Unexpected response format: {topics_result}")
                    topics_data = {"topic1": "General banking topics"}
            except json.JSONDecodeError as e:
                self.progress_update.emit(f"Error parsing topics: {str(e)}\nRaw response: {topics_result}")
                # Fallback to a default topic
                topics_data = {"topic1": "General banking topics"}
            
            # Clear any previous status messages
            self.output_panel.set_output("")
            
            # For each topic, get practitioner insights and update UI through signals
            for key, topic in topics_data.items():
                # Format the prompt with the topic
                formatted_prompt = PRACTITIONER_INSIGHTS_PROMPT.format(topic=topic)
                
                # Get insights for this topic
                insight = self.api_client.process_with_anthropic(
                    transcript, 
                    formatted_prompt,
                    stream=True,
                    callback=handle_stream
                )
            
        except Exception as e:
            import traceback
            error_details = traceback.format_exc()
            self.output_panel.set_error(f"Error processing insights: {str(e)}\n\n{error_details}")
        finally:
            self.is_processing = False
    
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
        self.output_panel.set_transcript(text)
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
            # Show result text
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
                # Find the next opening tag
                start_idx = self._html_buffer.find("<div class=\"topic-section\">")
                if start_idx == -1:
                    break  # No new element found
                    
                # Found a new element, initialize the section
                self._current_element = "topic-section"
                self._element_stack.append(self._current_element)
                self._current_list_items = []
                
            # Look for complete list items within the current section
            if self._current_element == "topic-section":
                # Try to find a complete list item
                item_start = self._html_buffer.find("<li class=\"insight-item\">")
                if item_start != -1:
                    item_end = self._html_buffer.find("</li>", item_start)
                    if item_end != -1:
                        # Extract the complete list item
                        item = self._html_buffer[item_start:item_end + 5]
                        self._current_list_items.append(item)
                        # Remove the processed item from buffer
                        self._html_buffer = self._html_buffer[:item_start] + self._html_buffer[item_end + 5:]
                        
                        # Return the current section with updated list items
                        section = f"""<div class="topic-section">
    <h2 class="topic-title">Follow-up Questions</h2>
    <div class="insight-block">
        <ul class="insight-list">
            {chr(10).join(self._current_list_items)}
        </ul>
    </div>
</div>"""
                        return section
                
                # Check if the section is complete
                end_idx = self._html_buffer.find("</div>", self._html_buffer.find("</div>") + 1)
                if end_idx != -1:
                    # Section is complete, reset state
                    complete_element = self._html_buffer[:end_idx + 6]
                    self._html_buffer = self._html_buffer[end_idx + 6:]
                    self._current_element = None
                    self._element_stack.pop()
                    self._current_list_items = []
                    return complete_element
                    
            break  # No complete elements found
            
        return None

    @pyqtSlot(str)
    def on_stream_update(self, text):
        """Handle streaming updates in a thread-safe way"""
        # Skip status messages
        if text.startswith("Generating insights") or text.startswith("Processing topic"):
            return
            
        # Process the HTML chunk
        complete_element = self._process_html_chunk(text)
        
        if complete_element:
            # If this is the first update, set the output
            if self._is_first_update:
                self.output_panel.set_output(complete_element)
                self._is_first_update = False
            else:
                # Append subsequent elements
                self.output_panel.append_output(complete_element)
                
    @pyqtSlot(str)
    def on_progress_update(self, message):
        """Handle progress updates in a thread-safe way"""
        self.output_panel.set_status(message)

    def clear_output(self):
        """Clear the output panel and reset HTML streaming state"""
        self.output_panel.set_output("")
        self.current_transcript = ""
        self._html_buffer = ""
        self._current_element = None
        self._element_stack = []
        self._is_first_update = True
        self._current_list_items = []

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