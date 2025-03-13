import sys
import threading
import time
import io
import wave
import json
import os
from datetime import datetime
from dotenv import load_dotenv

load_dotenv()

# PyQt imports
from PyQt6.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout, 
    QHBoxLayout, QPushButton, QLabel, QTextEdit, 
    QProgressBar, QMessageBox, QSplitter)
from PyQt6.QtCore import Qt, QTimer, pyqtSignal, pyqtSlot
from PyQt6.QtGui import QFont, QIcon

# Audio processing imports
import soundcard as sc
import soundfile as sf
import numpy as np
import speech_recognition as sr

# Optional: For Anthropic API
import requests
import anthropic

# Get the API key from environment variables
DEEPGRAM_API_KEY = os.getenv("DEEPGRAM_API_KEY")
if not DEEPGRAM_API_KEY:
    raise ValueError("DEEPGRAM_API_KEY not found in .env file")

class ContinuousRecorder:
    def __init__(self, buffer_minutes=3, sample_rate=48000, chunk_seconds=1):
        self.sample_rate = sample_rate
        self.chunk_seconds = chunk_seconds
        self.chunk_frames = chunk_seconds * sample_rate
        self.buffer_minutes = buffer_minutes
        self.buffer_chunks = buffer_minutes * 60 // chunk_seconds
        
        # Create a circular buffer to store audio
        self.audio_buffer = []
        self.buffer_lock = threading.Lock()
        
        # Recording control
        self.is_recording = False
        self.record_thread = None
        
        # Setup microphone
        self.mic = sc.get_microphone(id=str(sc.default_speaker().name), include_loopback=True)
    
    def start_recording(self):
        """Start the recording process in a separate thread"""
        if self.is_recording:
            return False
        
        self.is_recording = True
        self.record_thread = threading.Thread(target=self._record_loop)
        self.record_thread.daemon = True
        self.record_thread.start()
        return True
    
    def stop_recording(self):
        """Stop the recording process"""
        self.is_recording = False
        if self.record_thread:
            self.record_thread.join(timeout=2.0)
        return True
    
    def _record_loop(self):
        """Main recording loop that continuously captures audio in chunks"""
        with self.mic.recorder(samplerate=self.sample_rate) as recorder:
            while self.is_recording:
                # Record a chunk of audio
                data = recorder.record(numframes=self.chunk_frames)
                
                # Add to the circular buffer
                with self.buffer_lock:
                    self.audio_buffer.append(data)
                    # Keep only the most recent chunks to maintain our time limit
                    if len(self.audio_buffer) > self.buffer_chunks:
                        self.audio_buffer.pop(0)
    
    def save_buffer(self, filename=None):
        """Save the current audio buffer to a file and return mono data"""
        
        with self.buffer_lock:
            if not self.audio_buffer:
                print("No audio to save!")
                return
            
            # Combine all chunks in the buffer
            combined_data = np.concatenate(self.audio_buffer, axis=0)
            
            # Get mono audio (first channel)
            mono_data = combined_data[:, 0]
            
            # Save to file
            sf.write(file="BSGPT_REC.wav", data=mono_data, samplerate=self.sample_rate)
            print(f"Audio saved to {filename}")
            
            return mono_data
    
    def get_buffer_seconds(self):
        """Get the current buffer length in seconds"""
        with self.buffer_lock:
            return len(self.audio_buffer) * self.chunk_seconds


class ApiClient:
    def __init__(self, anthropic_api_key=None):
        self.anthropic_api_key = anthropic_api_key or os.environ.get("ANTHROPIC_API_KEY")
        
    def process_with_anthropic(self, transcript_text):
        """Process transcript with Anthropic API and return JSON response"""
        if not self.anthropic_api_key:
            return {"error": "Anthropic API key not set"}
        
        try:
            client = anthropic.Anthropic(api_key=self.anthropic_api_key)
            
            PROMPT = f"""
            Analyze the following block of text and summarize the topic three topics discussed in the transcription.

            The first topic should be the strongest one, the second topic should be the second strongest, and the third topic should be the third strongest.

            Return the list of topics in JSON format which can be passed on to other applications where the keys are topic 1, topic 2, and topic 3.
            And the values are each of the topics.

            Return nothing other than this requested output.

            Text to analyze:
            {transcript_text}
            """
            
            message = client.messages.create(
                model="claude-3-7-sonnet-20250219",
                max_tokens=1024,
                temperature=0,
                system="You analyze transcripts and extract key information as JSON.",
                messages=[
                    {"role": "user", "content": PROMPT}
                ]
            )
            
            # Extract the JSON from the response
            response_text = message.content[0].text
            try:
                # Parse the response as JSON
                json_result = json.loads(response_text)
                return json_result  # Return the parsed JSON as a dictionary
            except json.JSONDecodeError:
                # If not valid JSON, return the raw text as a dictionary
                return {"error": "Invalid JSON response", "raw_text": response_text}
                
        except Exception as e:
            return {"error": str(e)}
    
    def transcribe_with_deepgram(self, audio_data, sample_rate):
        """
        Transcribe audio using Deepgram API
        """
        file = "BSGPT_REC.wav"
        print("Transcribing audio...")

        # Deepgram API endpoint
        url = "https://api.deepgram.com/v1/listen"

        # Request headers
        headers = {
            "Authorization": f"Token {DEEPGRAM_API_KEY}"
        }
        
        # Parameters for the transcription
        params = {
            "punctuate": "true",
            "model": "general",
            "language": "en-US"
        }
        
        with open(file, "rb") as audio:
            # Send the request to Deepgram
            response = requests.post(
                url,
                headers=headers,
                params=params,
                data=audio
            )
        
        if response.status_code == 200:
            print("response 200")
            response_json = response.json()
            
            # Debug: Print the whole response structure
            print("Full response structure:")
            print(json.dumps(response_json, indent=2))
            
            # The correct path to the transcript is likely different
            # Try the standard Deepgram response structure
            try:
                transcript = response_json["results"]["channels"][0]["alternatives"][0]["transcript"]
                print(f"Found transcript: {transcript}")
                return transcript
            except KeyError:
                # If that fails, try to locate the transcript by exploring the response
                print("Standard path not found, examining response structure...")
                
                # If you can identify the correct structure from the debug output,
                # update this code accordingly
                return "Error: Could not locate transcript in response. Check console output for structure."
        else:
            print(f"Error: {response.status_code}")
            print(response.text)
            return f"Error: {response.status_code} - {response.text}"

class MainWindow(QMainWindow):
    # Custom signals
    recording_started = pyqtSignal()
    recording_stopped = pyqtSignal()
    transcription_complete = pyqtSignal(str)
    processing_complete = pyqtSignal(dict)
    buffer_updated = pyqtSignal(float)
    
    def __init__(self):
        super().__init__()
        self.setWindowTitle("BS GPT")
        self.setGeometry(100, 100, 1000, 700)
        
        # Initialize components
        self.recorder = ContinuousRecorder(buffer_minutes=5)
        self.api_client = ApiClient()
        self.current_transcript = ""
        
        # Create UI
        self.setup_ui()
        
        # Start buffer update timer
        self.buffer_timer = QTimer(self)
        self.buffer_timer.timeout.connect(self.update_buffer_info)
        self.buffer_timer.start(1000)  # Update every second
        
        # Connect custom signals
        self.recording_started.connect(self.on_recording_started)
        self.recording_stopped.connect(self.on_recording_stopped)
        self.transcription_complete.connect(self.on_transcription_complete)
        self.processing_complete.connect(self.on_processing_complete)
        self.buffer_updated.connect(self.on_buffer_updated)
    
    def setup_ui(self):
        # Main widget and layout
        main_widget = QWidget()
        self.setCentralWidget(main_widget)
        main_layout = QVBoxLayout(main_widget)  
        
        # Header section
        header_widget = QWidget()
        header_layout = QHBoxLayout(header_widget)
        
        app_title = QLabel("Welcome to BSGPT, your second brain")
        app_title.setFont(QFont("Arial", 18, QFont.Weight.Bold))
        header_layout.addWidget(app_title)
        
        header_layout.addStretch()
        
        self.settings_button = QPushButton("Settings")
        self.settings_button.clicked.connect(self.show_settings)
        header_layout.addWidget(self.settings_button)
        
        main_layout.addWidget(header_widget)
        
        # Content section with splitter
        content_splitter = QSplitter(Qt.Orientation.Horizontal)
        
        # Left panel (controls)
        left_panel = QWidget()
        left_layout = QVBoxLayout(left_panel)
        
        # Recording controls
        controls_label = QLabel("Recording Controls")
        controls_label.setFont(QFont("Arial", 14))
        left_layout.addWidget(controls_label)
        
        # Start/Stop recording
        self.record_button = QPushButton("Start Recording")
        self.record_button.setFont(QFont("Arial", 12))
        self.record_button.clicked.connect(self.toggle_recording)
        left_layout.addWidget(self.record_button)
        
        # Save current buffer
        self.save_button = QPushButton("Save Current Buffer")
        self.save_button.setFont(QFont("Arial", 12))
        self.save_button.clicked.connect(self.save_audio_buffer)
        self.save_button.setEnabled(False)
        left_layout.addWidget(self.save_button)
        
        # Transcribe buffer
        self.transcribe_button = QPushButton("Transcribe Buffer")
        self.transcribe_button.setFont(QFont("Arial", 12))
        self.transcribe_button.clicked.connect(self.transcribe_buffer)
        self.transcribe_button.setEnabled(False)
        left_layout.addWidget(self.transcribe_button)
        
        # Process transcript
        self.process_button = QPushButton("Process with Claude")
        self.process_button.setFont(QFont("Arial", 12))
        self.process_button.clicked.connect(self.process_transcript)
        self.process_button.setEnabled(False)
        left_layout.addWidget(self.process_button)
        
        # Buffer status
        buffer_status_label = QLabel("Buffer Status")
        buffer_status_label.setFont(QFont("Arial", 14))
        left_layout.addWidget(buffer_status_label)
        
        self.buffer_progress = QProgressBar()
        self.buffer_progress.setRange(0, 100)
        self.buffer_progress.setValue(0)
        left_layout.addWidget(self.buffer_progress)
        
        self.buffer_info = QLabel("Buffer: 0 seconds / 0 minutes")
        left_layout.addWidget(self.buffer_info)
        
        left_layout.addStretch()
        
        # Right panel (output)
        right_panel = QWidget()
        right_layout = QVBoxLayout(right_panel)
        
        # Transcript area
        transcript_label = QLabel("Transcript (Deepgram)")
        transcript_label.setFont(QFont("Arial", 14))
        right_layout.addWidget(transcript_label)
        
        self.transcript_text = QTextEdit()
        self.transcript_text.setReadOnly(True)
        self.transcript_text.setMinimumHeight(200)
        right_layout.addWidget(self.transcript_text)
        
        # Processed output
        processed_label = QLabel("Processed Output (Claude)")
        processed_label.setFont(QFont("Arial", 14))
        right_layout.addWidget(processed_label)
        
        self.processed_text = QTextEdit()
        self.processed_text.setReadOnly(True)
        right_layout.addWidget(self.processed_text)
        
        # Add panels to splitter
        content_splitter.addWidget(left_panel)
        content_splitter.addWidget(right_panel)
        content_splitter.setStretchFactor(0, 1)
        content_splitter.setStretchFactor(1, 2)
        
        main_layout.addWidget(content_splitter)
        
        # Footer
        footer = QLabel("© 2025 Audio Recorder and Analyzer")
        footer.setAlignment(Qt.AlignmentFlag.AlignCenter)
        main_layout.addWidget(footer)
    
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
        # Disable the button to prevent multiple clicks
        self.transcribe_button.setEnabled(False)
        self.transcribe_button.setText("Transcribing...")
        
        # Get audio data from buffer without saving to file
        audio_data = self.recorder.save_buffer()
        
        if audio_data is None:
            self.transcribe_button.setText("Transcribe Buffer")
            self.transcribe_button.setEnabled(True)
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
    
    def process_transcript(self):
        # Disable the button to prevent multiple clicks
        self.process_button.setEnabled(False)
        self.process_button.setText("Processing...")
        
        # Get the current transcript
        transcript = self.current_transcript
        
        if not transcript:
            self.process_button.setText("Process with Claude")
            self.process_button.setEnabled(True)
            QMessageBox.warning(self, "Processing Error", "No transcript to process")
            return
        
        # Start processing in a separate thread
        threading.Thread(target=self._process_thread, args=(transcript,)).start()
    
    def _process_thread(self, transcript):
        """Background thread for API processing"""
        try:
            result = self.api_client.process_with_anthropic(transcript)
            self.processing_complete.emit(result)
        except Exception as e:
            self.processing_complete.emit({"error": str(e)})
    
    def update_buffer_info(self):
        """Update the buffer information display"""
        if self.recorder.is_recording:
            buffer_seconds = self.recorder.get_buffer_seconds()
            buffer_minutes = buffer_seconds / 60
            max_minutes = self.recorder.buffer_minutes
            
            # Update progress bar
            progress_percent = min(100, int((buffer_seconds / (max_minutes * 60)) * 100))
            
            self.buffer_updated.emit(buffer_seconds)
    
    def show_settings(self):
        """Show settings dialog"""
        # Simple implementation - could be expanded
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
        self.record_button.setText("Stop Recording")
        self.save_button.setEnabled(True)
        self.transcribe_button.setEnabled(True)
    
    @pyqtSlot()
    def on_recording_stopped(self):
        self.record_button.setText("Start Recording")
    
    @pyqtSlot(str)
    def on_transcription_complete(self, text):
        self.transcript_text.setPlainText(text)
        self.transcribe_button.setText("Transcribe Buffer")
        self.transcribe_button.setEnabled(True)
        self.process_button.setEnabled(True)
    
    @pyqtSlot(dict)
    def on_processing_complete(self, result):
        # Format the result as pretty JSON
        formatted_json = json.dumps(result, indent=2)
        self.processed_text.setPlainText(formatted_json)
        self.process_button.setText("Process with Claude")
        self.process_button.setEnabled(True)
    
    @pyqtSlot(float)
    def on_buffer_updated(self, buffer_seconds):
        buffer_minutes = buffer_seconds / 60
        max_minutes = self.recorder.buffer_minutes
        
        # Update progress bar
        progress_percent = min(100, int((buffer_seconds / (max_minutes * 60)) * 100))
        self.buffer_progress.setValue(progress_percent)
        
        # Update text
        self.buffer_info.setText(f"Buffer: {buffer_seconds:.1f} seconds / {buffer_minutes:.2f} minutes")


if __name__ == "__main__":
    # Add QInputDialog import at the top if not already imported
    from PyQt6.QtWidgets import QInputDialog
    
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(app.exec())