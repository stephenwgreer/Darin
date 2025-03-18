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
from prompts.templates import *

class MainWindow(QMainWindow):
    # Custom signals
    recording_started = pyqtSignal()
    recording_stopped = pyqtSignal()
    transcription_complete = pyqtSignal(str)
    processing_complete = pyqtSignal(dict)
    buffer_updated = pyqtSignal(float)
    progress_update = pyqtSignal(str)  # Signal for thread-safe progress updates
    
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Darin Audio Assistant")
        self.setGeometry(100, 100, 1000, 700)

        # Set application icon
        app_icon = QIcon("assets/Darin_ICON.png")
        self.setWindowIcon(app_icon)
            
        # Initialize components
        self.recorder = ContinuousRecorder(buffer_minutes=5)
        self.api_client = ApiClient()
        self.current_transcript = ""
        self.is_processing = False  # Track if we're currently processing
        
        # Setup UI
        self.setup_ui()
        
        # Connect signals to slots
        self.setup_connections()
        
        # Start buffer update timer
        self.buffer_timer = QTimer(self)
        self.buffer_timer.timeout.connect(self.update_buffer_info)
        self.buffer_timer.start(1000)  # Update every second
    
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
        
        # App title
        app_title = QLabel("Welcome to Darin, your intern")
        app_title.setFont(QFont("Arial", 18, QFont.Weight.Bold))
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
        self.controls_panel.save_clicked.connect(self.save_audio_buffer)
        self.controls_panel.transcribe_clicked.connect(self.transcribe_buffer)
        
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
        self.buffer_updated.connect(self.on_buffer_updated)
        self.progress_update.connect(self.on_progress_update)
    
    def toggle_recording(self):
        if not self.recorder.is_recording:
            # Start recording
            if self.recorder.start_recording():
                self.recording_started.emit()
        else:
            # Stop recording
            if self.recorder.stop_recording():
                self.recording_stopped.emit()
    
    def save_audio_buffer(self):
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"recording_{timestamp}.wav"
        
        audio_data = self.recorder.save_buffer(filename)
        if audio_data is not None:
            QMessageBox.information(self, "Save Complete", f"Audio saved to {filename}")
    
    def transcribe_buffer(self):
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
            
            # Get client from API wrapper
            import anthropic
            client = anthropic.Anthropic(api_key=self.api_client.anthropic_api_key)
            
            # Import processing function
            from api.anthropic_utils import process_with_template
            
            # Process with the template
            result = process_with_template(client, transcript, prompt_template)
            
            # Try to parse as JSON for display
            try:
                parsed_result = json.loads(result)
                formatted_result = json.dumps(parsed_result, indent=2)
            except:
                # If not valid JSON, just use the text result
                formatted_result = result
                
            # Update UI with result
            self.processing_complete.emit({"result": formatted_result})
        except Exception as e:
            self.processing_complete.emit({"error": str(e)})
        finally:
            self.is_processing = False
    
    def _run_practitioner_insights(self, transcript):
        """Process transcript to get banking practitioner insights"""
        try:
            # Get client from API wrapper
            import anthropic
            client = anthropic.Anthropic(api_key=self.api_client.anthropic_api_key)
            
            # Import processing function
            from api.anthropic_utils import process_with_template
            
            # Extract topics first
            self.progress_update.emit("Extracting main topics...")
            topics_result = process_with_template(client, transcript, DEFAULT_TOPIC_EXTRACTION_PROMPT)
            
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
            
            # Prepare accumulating output text
            accumulated_output = "Generating insights...\n\n"
            self.progress_update.emit(accumulated_output)
            
            # For each topic, get practitioner insights and update UI through signals
            for key, topic in topics_data.items():
                # Update UI to show which topic we're processing
                status_update = f"{accumulated_output}Processing {key}: {topic}...\n"
                self.progress_update.emit(status_update)
                
                # Get insights for this topic
                insight = process_with_template(
                    client, 
                    transcript, 
                    PRACTITIONER_INSIGHTS_PROMPT, 
                    topic=topic
                )
                
                # Add to accumulated output
                accumulated_output = f"{status_update}\n{key}: {topic}\n{insight}\n\n"
            
            # Final result when complete
            self.processing_complete.emit({"result": accumulated_output})
            
        except Exception as e:
            import traceback
            error_details = traceback.format_exc()
            self.processing_complete.emit({"error": f"Error processing insights: {str(e)}\n\n{error_details}"})
        finally:
            self.is_processing = False
    
    def update_buffer_info(self):
        """Update the buffer information display"""
        if self.recorder.is_recording:
            buffer_seconds = self.recorder.get_buffer_seconds()
            max_minutes = self.recorder.buffer_minutes
            
            self.buffer_updated.emit(buffer_seconds)
    
    def show_settings(self):
        """Show settings dialog"""
        api_key = self.api_client.anthropic_api_key or ""
        new_key, ok = QInputDialog.getText(
            self, "API Settings", "Anthropic API Key:", 
            QLineEdit.EchoMode.Password, api_key
        )
        
        if ok and new_key:
            self.api_client.anthropic_api_key = new_key
    
    # Slots for custom signals
    @pyqtSlot()
    def on_recording_started(self):
        self.controls_panel.set_recording_active(True)
        
        # Now we also enable the prompt buttons when recording starts
        self.controls_panel.set_prompt_buttons_enabled(True)
    
    @pyqtSlot()
    def on_recording_stopped(self):
        self.controls_panel.set_recording_active(False)
        
        # Keep buttons enabled even when recording stops
        # as long as we have buffer data
        if self.recorder.get_buffer_seconds() > 0:
            self.controls_panel.save_button.setEnabled(True)
            self.controls_panel.transcribe_button.setEnabled(True)
            self.controls_panel.set_prompt_buttons_enabled(True)
    
    @pyqtSlot(str)
    def on_transcription_complete(self, text):
        self.output_panel.set_transcript(text)
        self.controls_panel.transcribe_button.setText("Transcribe Buffer")
        self.controls_panel.transcribe_button.setEnabled(True)
        
        # Enable all prompt buttons when we have a transcript
        self.controls_panel.set_prompt_buttons_enabled(True)
    
    @pyqtSlot(dict)
    def on_processing_complete(self, result):
        if "error" in result:
            # Show error
            self.output_panel.set_output(f"Error: {result['error']}")
        elif "result" in result:
            # Show result text
            self.output_panel.set_output(result["result"])
        else:
            # Format the entire result as pretty JSON
            self.output_panel.set_output_json(result)
        
        # Re-enable prompt buttons
        self.controls_panel.set_prompt_buttons_enabled(True)
    
    @pyqtSlot(str)
    def on_progress_update(self, message):
        """Handle progress updates in a thread-safe way"""
        self.output_panel.set_output(message)
    
    @pyqtSlot(float)
    def on_buffer_updated(self, buffer_seconds):
        max_minutes = self.recorder.buffer_minutes
        self.controls_panel.update_buffer_info(buffer_seconds, max_minutes)
        
        # Enable buttons if we have buffer data
        if buffer_seconds > 0:
            self.controls_panel.save_button.setEnabled(True)
            self.controls_panel.transcribe_button.setEnabled(True)
            self.controls_panel.set_prompt_buttons_enabled(True)