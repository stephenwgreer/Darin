import soundcard as sc
import soundfile as sf
import numpy as np
import threading
import time
import keyboard
import os
import io
import speech_recognition as sr
import wave
from datetime import datetime

class ContinuousRecorder:
    def __init__(self, buffer_minutes=5, sample_rate=48000, chunk_seconds=1):
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
            print("Already recording!")
            return
        
        self.is_recording = True
        self.record_thread = threading.Thread(target=self._record_loop)
        self.record_thread.daemon = True
        self.record_thread.start()
        print("Recording started. Press Enter to save the current buffer.")
    
    def stop_recording(self):
        """Stop the recording process"""
        self.is_recording = False
        if self.record_thread:
            self.record_thread.join()
        print("Recording stopped.")
    
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
    
    def save_buffer(self, filename="recording.wav", transcribe=False):
        """Save the current audio buffer to a file and optionally transcribe"""
        
        with self.buffer_lock:
            if not self.audio_buffer:
                print("No audio to save!")
                return
            
            # Combine all chunks in the buffer
            combined_data = np.concatenate(self.audio_buffer, axis=0)
            
            # Get mono audio (first channel)
            mono_data = combined_data[:, 0]
            
            # Save to file
            sf.write(file=filename, data=mono_data, samplerate=self.sample_rate)
            print(f"Audio saved to {filename}")
            
            # Transcribe if requested
            if transcribe:
                text = self.transcribe_buffer(mono_data)
                return text
                
    def transcribe_buffer(self, audio_data):
        """Transcribe audio data using Google Speech Recognition"""
        # Create a recognizer
        recognizer = sr.Recognizer()
        
        # Convert numpy array to WAV file in memory
        byte_io = io.BytesIO()
        with wave.open(byte_io, 'wb') as wave_file:
            wave_file.setnchannels(1)
            wave_file.setsampwidth(2)  # 16-bit audio
            wave_file.setframerate(self.sample_rate)
            wave_file.writeframes((audio_data * 32767).astype(np.int16).tobytes())
        
        # Create AudioData object from WAV bytes
        byte_io.seek(0)
        with sr.AudioFile(byte_io) as source:
            audio = recognizer.record(source)
            
        text = ""
        try:
            # Recognize speech using Google Web Speech API
            text = recognizer.recognize_google(audio)
            print("Transcription: ", text)
        except sr.UnknownValueError:
            print("Google Web Speech API could not understand the audio")
        except sr.RequestError as e:
            print(f"Could not request results from Google Web Speech API; {e}")
            
        return text

def main():
    # Create recorder with 5-minute buffer
    recorder = ContinuousRecorder(buffer_minutes=5)
    
    # Start recording
    recorder.start_recording()
    
    # Setup keyboard listener for Enter key
    def on_enter_pressed(event):
        if event.name == 'enter':
            text = recorder.save_buffer(transcribe=True)
            print(f"Captured text: {text}")
    
    keyboard.on_press(on_enter_pressed)
    
    try:
        print("Recording audio (last 5 minutes kept in buffer)")
        print("Press Enter to save the current buffer and transcribe")
        print("Press Ctrl+C to exit")
        
        # Keep the main thread alive
        while recorder.is_recording:
            time.sleep(1)
    
    except KeyboardInterrupt:
        print("\nStopping recording...")
    finally:
        recorder.stop_recording()
        keyboard.unhook_all()

if __name__ == "__main__":
    main()