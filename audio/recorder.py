import threading
from collections import deque

import numpy as np
import soundcard as sc
import soundfile as sf


class ContinuousRecorder:
    def __init__(self, buffer_minutes=3, sample_rate=48000, chunk_seconds=1):
        self.sample_rate = sample_rate
        self.chunk_seconds = chunk_seconds
        self.chunk_frames = chunk_seconds * sample_rate
        self.buffer_minutes = buffer_minutes
        self.buffer_chunks = int(buffer_minutes * 60 // chunk_seconds)

        # Create a circular buffer to store audio (deque for O(1) operations)
        self.audio_buffer = deque(maxlen=self.buffer_chunks)
        self.buffer_lock = threading.Lock()

        # Recording control - using private variable with lock for thread safety
        self._is_recording = False
        self._recording_lock = threading.Lock()
        self.record_thread = None

        # Setup microphone
        self.mic = sc.get_microphone(id=str(sc.default_speaker().name), include_loopback=True)

    @property
    def is_recording(self):
        """Thread-safe property for recording state"""
        with self._recording_lock:
            return self._is_recording

    @is_recording.setter
    def is_recording(self, value):
        """Thread-safe setter for recording state"""
        with self._recording_lock:
            self._is_recording = value

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
            while True:
                # Check recording state with lock
                with self._recording_lock:
                    if not self._is_recording:
                        break

                # Record a chunk of audio
                data = recorder.record(numframes=self.chunk_frames)

                # Add to the circular buffer
                with self.buffer_lock:
                    # deque with maxlen automatically drops oldest when full
                    self.audio_buffer.append(data)

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
            output_file = filename or "BSGPT_REC.wav"
            sf.write(file=output_file, data=mono_data, samplerate=self.sample_rate)
            print(f"Audio saved to {output_file}")

            return mono_data

    def get_buffer_seconds(self):
        """Get the current buffer length in seconds"""
        with self.buffer_lock:
            return len(self.audio_buffer) * self.chunk_seconds

    def get_last_n_seconds(self, seconds):
        """Get the last N seconds of audio from the buffer"""
        with self.buffer_lock:
            if not self.audio_buffer:
                return None

            # Calculate how many chunks we need
            chunks_needed = int(seconds // self.chunk_seconds)
            if chunks_needed == 0:
                chunks_needed = 1  # At least get one chunk

            # Get the last N chunks (convert deque to list for slicing)
            buffer_list = list(self.audio_buffer)
            chunks = buffer_list[-chunks_needed:]

            # Combine chunks into one array
            if len(chunks) > 1:
                combined_data = np.concatenate(chunks, axis=0)
            else:
                combined_data = chunks[0]

            # Get mono audio (first channel)
            mono_data = combined_data[:, 0]

            return mono_data
